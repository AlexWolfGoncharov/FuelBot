"""
Smart photo handler - automatically detects photo type and suggests actions
"""
import asyncio
import logging
from io import BytesIO

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.states.refuel_states import RefuelStates, BatchRefuelStates, SmartPhotoStates
from bot.utils.user_helpers import get_user_id_for_refuels
from bot.handlers.refuel import _telegram_message_naive_utc
from bot.keyboards.inline import get_full_tank_keyboard
from models.schemas import ReceiptData, OdometerData
from services.image import extract_gps_coordinates, extract_datetime_taken
from services.ai_vision.gemini import recognize_smart
from models.database import async_session, Refuel
from sqlalchemy import select, and_
from datetime import datetime, timedelta

router = Router()
logger = logging.getLogger(__name__)

# Storage for media group processing
media_group_storage = {}
media_group_timers = {}

SMART_PAIR_KEYS = (
    "smart_receipt",
    "smart_receipt_file_id",
    "smart_receipt_photo_datetime",
    "smart_receipt_telegram_date",
    "smart_receipt_latitude",
    "smart_receipt_longitude",
    "smart_odometer",
    "smart_odometer_file_id",
)


def _receipt_meta_from_message(message: Message, image_data: bytes) -> dict:
    lat, lon = extract_gps_coordinates(image_data)
    return {
        "photo_datetime": extract_datetime_taken(image_data),
        "telegram_message_date": _telegram_message_naive_utc(message),
        "latitude": float(lat) if lat is not None else None,
        "longitude": float(lon) if lon is not None else None,
    }


async def _strip_stale_smart_without_state(state: FSMContext) -> None:
    """Якщо лишились smart_* без стану waiting_pair — прибрати (сирота після збою)."""
    data = await state.get_data()
    if not any(k in data for k in SMART_PAIR_KEYS):
        return
    st = await state.get_state()
    # get_state() повертає рядок; порівнювати з .state, не з об'єктом State
    if st == SmartPhotoStates.waiting_pair.state:
        return
    cleaned = {k: v for k, v in data.items() if k not in SMART_PAIR_KEYS}
    await state.set_data(cleaned)


async def _merge_smart_pair_go_full_tank(
    message: Message,
    state: FSMContext,
    receipt: ReceiptData,
    odometer: OdometerData,
    receipt_file_id: str,
    odometer_file_id: str,
    photo_datetime,
    telegram_message_date,
    latitude,
    longitude,
) -> None:
    data = await state.get_data()
    for k in SMART_PAIR_KEYS:
        data.pop(k, None)
    data.update(
        {
            "receipt": receipt.model_dump(),
            "receipt_file_id": receipt_file_id,
            "odometer": odometer.model_dump(),
            "odometer_file_id": odometer_file_id,
            "photo_datetime": photo_datetime,
            "telegram_message_date": telegram_message_date,
            "latitude": latitude,
            "longitude": longitude,
        }
    )
    await state.set_data(data)
    await state.set_state(RefuelStates.asking_full_tank)
    await message.answer(
        "✅ <b>Чек і одометр зібрано в одну заправку</b>\n\n"
        f"📍 <b>{receipt.station}</b> · {receipt.liters} л · {receipt.total_cost} грн\n"
        f"🔢 Одометр: <b>{odometer.odometer} км</b>\n\n"
        "⛽ Чи заправили ви бак до повного?\n\n"
        "💡 <b>Це важливо для точного розрахунку витрати палива</b>\n"
        "Витрата розраховується тільки між заправками до повного бака",
        parse_mode="HTML",
        reply_markup=get_full_tank_keyboard(),
    )


async def check_duplicate_refuel(user_id: int, receipt_data, odometer_data, photo_datetime=None) -> bool:
    """Check if refuel already exists in database - ignores date/time"""
    try:
        logger.info(f"DEBUG check_duplicate_refuel: Looking for liters={receipt_data.liters}, cost={receipt_data.total_cost}, odo={odometer_data.odometer}")

        async with async_session() as session:
            # Check for duplicate by exact match on liters, cost, and odometer (ignore date)
            result = await session.execute(
                select(Refuel).where(
                    and_(
                        Refuel.user_id == user_id,
                        Refuel.liters == float(receipt_data.liters),
                        Refuel.total_cost == float(receipt_data.total_cost),
                        Refuel.odometer == odometer_data.odometer
                    )
                )
            )
            existing = result.first()
            if existing:
                logger.info(f"✅ Duplicate found: {receipt_data.liters}L, {receipt_data.total_cost}грн, {odometer_data.odometer}km")
            else:
                logger.info(f"❌ NO duplicate found for: {receipt_data.liters}L, {receipt_data.total_cost}грн, {odometer_data.odometer}km")
            return existing is not None
    except Exception as e:
        logger.error(f"Error checking duplicate: {e}")
        return False


async def process_media_group(user_id: int, media_group_id: str, message: Message, state: FSMContext):
    """Process collected media group after timeout"""
    if media_group_id not in media_group_storage:
        return

    messages = media_group_storage[media_group_id]
    del media_group_storage[media_group_id]

    if media_group_id in media_group_timers:
        del media_group_timers[media_group_id]

    processing_msg = await message.answer(f"🔍 Аналізую {len(messages)} фото...")

    try:
        # STEP 1: Collect all photos with timestamps (before OCR)
        photos_with_time = []

        for msg in messages:
            if msg.photo:
                photo = msg.photo[-1]
                file_id = photo.file_id
                file = await msg.bot.get_file(photo.file_id)
                # For compressed photos, use message date (Telegram strips EXIF)
                # Convert to naive datetime (remove timezone info)
                photo_datetime = msg.date.replace(tzinfo=None) if msg.date.tzinfo else msg.date
                logger.info(f"DEBUG smart_photo: Compressed photo, message.date = {photo_datetime}")
            elif msg.document:
                file_id = msg.document.file_id
                file = await msg.bot.get_file(msg.document.file_id)
                photo_datetime = None  # Will extract EXIF later
            else:
                continue

            image_bytes = BytesIO()
            await msg.bot.download_file(file.file_path, image_bytes)
            image_data = image_bytes.getvalue()

            # For documents, try to extract EXIF datetime
            if photo_datetime is None:
                from services.image.exif_extractor import extract_datetime_taken
                exif_datetime = extract_datetime_taken(image_data)
                if exif_datetime:
                    photo_datetime = exif_datetime
                    logger.info(f"DEBUG smart_photo: Document photo, EXIF datetime = {photo_datetime}")
                else:
                    logger.warning(f"DEBUG smart_photo: No EXIF datetime, using message.date")
                    # Convert to naive datetime (remove timezone info)
                    photo_datetime = msg.date.replace(tzinfo=None) if msg.date.tzinfo else msg.date

            photos_with_time.append({
                'file_id': file_id,
                'image_data': image_data,
                'photo_datetime': photo_datetime,
                'telegram_message_date': _telegram_message_naive_utc(msg),
                'message': msg
            })

        # STEP 2: Sort by timestamp
        photos_with_time.sort(key=lambda x: x['photo_datetime'])
        logger.info(f"DEBUG smart_photo: Sorted {len(photos_with_time)} photos by timestamp")

        # STEP 3: Pair adjacent photos (1-2, 3-4, 5-6...)
        candidate_pairs = []
        for i in range(0, len(photos_with_time) - 1, 2):
            pair = [photos_with_time[i], photos_with_time[i+1]]
            time_diff = abs(pair[1]['photo_datetime'] - pair[0]['photo_datetime'])
            logger.info(f"DEBUG smart_photo: Candidate pair {i//2 + 1}: {pair[0]['photo_datetime']} <-> {pair[1]['photo_datetime']}, diff={time_diff}")
            candidate_pairs.append(pair)

        # Handle odd number of photos
        unpaired_photo = None
        if len(photos_with_time) % 2 == 1:
            unpaired_photo = photos_with_time[-1]
            logger.warning(f"DEBUG smart_photo: Odd number of photos, last one unpaired")

        # STEP 4: OCR each pair and verify one is receipt, other is odometer
        receipts_count = 0
        odometers_count = 0
        unknown_count = 0
        duplicates = []
        unique_pairs = []

        # Get user context from recent refuels (for better OCR accuracy)
        from services.ai_vision.gemini import get_user_refuel_context
        user_context = await get_user_refuel_context(user_id)

        for pair_idx, pair in enumerate(candidate_pairs, 1):
            await processing_msg.edit_text(f"🔍 Обробка пари {pair_idx}/{len(candidate_pairs)}...")

            # OCR both photos in pair
            results_in_pair = []
            for photo in pair:
                result = await recognize_smart(photo['image_data'], user_context)
                results_in_pair.append({
                    **result,
                    'file_id': photo['file_id'],
                    'photo_datetime': photo['photo_datetime'],
                    'telegram_message_date': photo.get('telegram_message_date'),
                })
                if result['type'] == 'receipt':
                    receipts_count += 1
                elif result['type'] == 'odometer':
                    odometers_count += 1
                elif result['type'] == 'unknown':
                    unknown_count += 1

            # Check if we have exactly one receipt and one odometer
            receipt_item = next((r for r in results_in_pair if r['type'] == 'receipt'), None)
            odometer_item = next((r for r in results_in_pair if r['type'] == 'odometer'), None)

            if receipt_item and odometer_item:
                # Valid pair! Check for duplicate
                logger.info(f"✅ Valid pair {pair_idx}: receipt + odometer")
                is_duplicate = await check_duplicate_refuel(user_id, receipt_item['data'], odometer_item['data'], receipt_item['photo_datetime'])

                if is_duplicate:
                    duplicates.append({'receipt': receipt_item, 'odometer': odometer_item})
                else:
                    unique_pairs.append({'receipt': receipt_item, 'odometer': odometer_item})
            else:
                logger.warning(f"⚠️ Pair {pair_idx} is not valid: {results_in_pair[0]['type']} + {results_in_pair[1]['type']}")

        text = (
            f"📊 <b>Результати розпізнавання {len(messages)} фото:</b>\n\n"
            f"✅ Чеків: {receipts_count}\n"
            f"✅ Одометрів: {odometers_count}\n"
        )

        if unknown_count:
            text += f"❓ Нерозпізнано: {unknown_count}\n"

        text += "\n"

        # Suggest actions based on what was recognized
        keyboard_buttons = []

        if duplicates:
            text += f"⚠️ Дублікатів: {len(duplicates)} (вже в базі)\n"

        if unique_pairs:
            text += f"✅ Можна створити {len(unique_pairs)} нових заправок!\n"
            keyboard_buttons.append([
                InlineKeyboardButton(text=f"✅ Зберегти {len(unique_pairs)} заправок", callback_data="smart_save_album")
            ])
        elif duplicates:
            # All pairs are duplicates
            text += "❌ Всі заправки вже є в базі\n"
        elif receipts_count > 0 or odometers_count > 0:
            # Have some receipts/odometers but couldn't form valid pairs
            text += "💡 Додайте ще фото через /batch або /add"
            keyboard_buttons.append([
                InlineKeyboardButton(text="📤 Продовжити в batch режимі", callback_data="smart_continue_batch")
            ])

        keyboard_buttons.append([
            InlineKeyboardButton(text="🏠 Головне меню", callback_data="main_menu")
        ])

        # Save results to state (only unique pairs)
        await state.update_data(
            unique_pairs=unique_pairs,
            duplicates=duplicates
        )

        await processing_msg.delete()
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        )

    except Exception as e:
        logger.error(f"Error processing media group: {e}", exc_info=True)
        await processing_msg.delete()
        await message.answer(f"❌ Помилка обробки альбому: {str(e)}")


@router.message(F.photo | F.document)
async def smart_photo_handler(message: Message, state: FSMContext):
    """
    Smart handler for photos sent without command
    Automatically detects if it's a receipt or odometer
    Handles both single photos and media groups (albums)
    Послідовні фото (чек потім одометр або навпаки) зшиваються в одну заправку.
    """
    current_state = await state.get_state()
    if current_state is not None and current_state != SmartPhotoStates.waiting_pair.state:
        return

    # Get internal user_id from telegram_id
    user_id = await get_user_id_for_refuels(
        message.from_user.id, message.from_user.username, message.from_user.first_name
    )
    telegram_id = message.from_user.id

    # Check if this is part of a media group (album)
    if message.media_group_id:
        media_group_id = message.media_group_id

        # Add to media group storage
        if media_group_id not in media_group_storage:
            media_group_storage[media_group_id] = []

        media_group_storage[media_group_id].append(message)

        # Cancel previous timer if exists
        if media_group_id in media_group_timers:
            media_group_timers[media_group_id].cancel()

        # Set timer to process media group after 1 second (wait for all photos)
        async def delayed_process():
            await asyncio.sleep(1)
            await process_media_group(telegram_id, media_group_id, message, state)

        task = asyncio.create_task(delayed_process())
        media_group_timers[media_group_id] = task

        return

    await _strip_stale_smart_without_state(state)

    # Single photo - process immediately
    processing_msg = await message.answer("🔍 Аналізую фото...")

    try:
        # Get photo or document
        if message.photo:
            photo = message.photo[-1]
            file_id = photo.file_id
            file = await message.bot.get_file(photo.file_id)
        elif message.document:
            if not message.document.mime_type or not message.document.mime_type.startswith('image/'):
                await processing_msg.delete()
                return
            file_id = message.document.file_id
            file = await message.bot.get_file(message.document.file_id)
        else:
            await processing_msg.delete()
            return

        # Download image
        image_bytes = BytesIO()
        await message.bot.download_file(file.file_path, image_bytes)
        image_data = image_bytes.getvalue()

        # Get user context from recent refuels (for better OCR accuracy)
        from services.ai_vision.gemini import get_user_refuel_context
        user_context = await get_user_refuel_context(user_id)

        # Smart recognition - single API call
        result = await recognize_smart(image_data, user_context)

        recognized_type = result["type"]
        recognized_data = result["data"]
        data = await state.get_data()

        # --- Друге фото в режимі пари: зшити або замінити ту саму половину ---
        if current_state == SmartPhotoStates.waiting_pair.state:
            pr = data.get("smart_receipt")
            po = data.get("smart_odometer")

            if recognized_type == "receipt" and po is not None:
                rc: ReceiptData = recognized_data
                od = OdometerData(**po)
                meta = _receipt_meta_from_message(message, image_data)
                await _merge_smart_pair_go_full_tank(
                    message,
                    state,
                    rc,
                    od,
                    receipt_file_id=file_id,
                    odometer_file_id=data["smart_odometer_file_id"],
                    photo_datetime=meta["photo_datetime"],
                    telegram_message_date=meta["telegram_message_date"],
                    latitude=meta["latitude"],
                    longitude=meta["longitude"],
                )
                await processing_msg.delete()
                return

            if recognized_type == "odometer" and pr is not None:
                rc = ReceiptData(**pr)
                od: OdometerData = recognized_data
                await _merge_smart_pair_go_full_tank(
                    message,
                    state,
                    rc,
                    od,
                    receipt_file_id=data["smart_receipt_file_id"],
                    odometer_file_id=file_id,
                    photo_datetime=data.get("smart_receipt_photo_datetime"),
                    telegram_message_date=data.get("smart_receipt_telegram_date"),
                    latitude=data.get("smart_receipt_latitude"),
                    longitude=data.get("smart_receipt_longitude"),
                )
                await processing_msg.delete()
                return

            if recognized_type == "receipt":
                meta = _receipt_meta_from_message(message, image_data)
                nd = {k: v for k, v in data.items() if k not in SMART_PAIR_KEYS}
                nd.update(
                    {
                        "smart_receipt": recognized_data.model_dump(),
                        "smart_receipt_file_id": file_id,
                        "smart_receipt_photo_datetime": meta["photo_datetime"],
                        "smart_receipt_telegram_date": meta["telegram_message_date"],
                        "smart_receipt_latitude": meta["latitude"],
                        "smart_receipt_longitude": meta["longitude"],
                    }
                )
                await state.set_data(nd)
                await state.set_state(SmartPhotoStates.waiting_pair)
                text = (
                    f"✅ <b>Чек оновлено</b> (впевненість: {recognized_data.confidence}%)\n\n"
                    f"📍 {recognized_data.station} · {recognized_data.liters} л\n\n"
                    "📎 <b>Надішліть наступним повідомленням фото одометра</b> "
                    "(або /cancel)"
                )
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="📤 Batch / альбом", callback_data="smart_start_batch"
                            )
                        ],
                        [InlineKeyboardButton(text="❌ Скасувати", callback_data="smart_cancel")],
                    ]
                )
                await processing_msg.delete()
                await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
                return

            if recognized_type == "odometer":
                nd = {k: v for k, v in data.items() if k not in SMART_PAIR_KEYS}
                nd.update(
                    {
                        "smart_odometer": recognized_data.model_dump(),
                        "smart_odometer_file_id": file_id,
                    }
                )
                await state.set_data(nd)
                await state.set_state(SmartPhotoStates.waiting_pair)
                text = (
                    f"✅ <b>Одометр оновлено</b> ({recognized_data.odometer} км)\n\n"
                    "📎 <b>Надішліть наступним повідомленням фото чека</b> "
                    "(або /cancel)"
                )
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="📤 Batch / альбом", callback_data="smart_start_batch"
                            )
                        ],
                        [InlineKeyboardButton(text="❌ Скасувати", callback_data="smart_cancel")],
                    ]
                )
                await processing_msg.delete()
                await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
                return

            await processing_msg.delete()
            await message.answer(
                "❓ Не зрозумів фото. Очікується <b>чек</b> або <b>одометр</b>.\n\n"
                "Спробуйте ще раз або /cancel",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="❌ Скасувати", callback_data="smart_cancel")]
                    ]
                ),
            )
            return

        # --- Перше фото (немає активної пари) ---
        if recognized_type == "receipt":
            meta = _receipt_meta_from_message(message, image_data)
            nd = {k: v for k, v in data.items() if k not in SMART_PAIR_KEYS}
            nd.update(
                {
                    "smart_receipt": recognized_data.model_dump(),
                    "smart_receipt_file_id": file_id,
                    "smart_receipt_photo_datetime": meta["photo_datetime"],
                    "smart_receipt_telegram_date": meta["telegram_message_date"],
                    "smart_receipt_latitude": meta["latitude"],
                    "smart_receipt_longitude": meta["longitude"],
                }
            )
            await state.set_data(nd)
            await state.set_state(SmartPhotoStates.waiting_pair)
            text = (
                f"✅ <b>Розпізнав чек з АЗС</b> (впевненість: {recognized_data.confidence}%)\n\n"
                f"📍 АЗС: <b>{recognized_data.station}</b>\n"
                f"⛽ Паливо: <b>{recognized_data.fuel_type}</b>\n"
            )
            if hasattr(recognized_data, "has_refund") and recognized_data.has_refund:
                text += (
                    f"📊 Літри: <b>{recognized_data.liters} л</b> "
                    f"(залито - повернуто: {recognized_data.refund_liters} л)\n"
                    f"💰 Сума: <b>{recognized_data.total_cost} грн</b>\n"
                )
            else:
                text += (
                    f"📊 Літри: <b>{recognized_data.liters} л</b>\n"
                    f"💰 Сума: <b>{recognized_data.total_cost} грн</b>\n"
                )
            text += (
                f"💵 Ціна: <b>{recognized_data.price_per_liter} грн/л</b>\n"
                f"📅 Дата: <b>{recognized_data.date} {recognized_data.time}</b>\n\n"
                "📎 <b>Надішліть наступним повідомленням фото одометра</b> — "
                "я зберу все в одну заправку.\n\n"
                "<i>Або одразу додайте лише чек кнопкою нижче.</i>"
            )
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="➕ Тільки чек → /add", callback_data="smart_add_receipt")],
                    [InlineKeyboardButton(text="📤 Batch / альбом", callback_data="smart_start_batch")],
                    [InlineKeyboardButton(text="❌ Скасувати", callback_data="smart_cancel")],
                ]
            )
            await processing_msg.delete()
            await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
            return

        if recognized_type == "odometer":
            nd = {k: v for k, v in data.items() if k not in SMART_PAIR_KEYS}
            nd.update(
                {
                    "smart_odometer": recognized_data.model_dump(),
                    "smart_odometer_file_id": file_id,
                }
            )
            await state.set_data(nd)
            await state.set_state(SmartPhotoStates.waiting_pair)
            text = (
                f"✅ <b>Розпізнав одометр</b> (впевненість: {recognized_data.confidence}%)\n\n"
                f"🔢 Пробіг: <b>{recognized_data.odometer} км</b>\n\n"
                "📎 <b>Надішліть наступним повідомленням фото чека</b> — "
                "я зберу все в одну заправку.\n\n"
                "<i>Або почніть з чека через меню.</i>"
            )
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="⛽ Спочатку чек (/add)", callback_data="add_refuel")],
                    [InlineKeyboardButton(text="📤 Batch / альбом", callback_data="smart_start_batch")],
                    [InlineKeyboardButton(text="❌ Скасувати", callback_data="smart_cancel")],
                ]
            )
            await processing_msg.delete()
            await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
            return

        # unknown
        text = (
            "❓ <b>Не вдалося розпізнати фото</b>\n\n"
            "Це може бути чек або одометр?\n"
            "Спробуйте:\n"
            "• Краще освітлення 💡\n"
            "• Чіткіше фото 📸\n"
            "• Розгорнутий документ 📄\n\n"
            "Або почніть вручну:"
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⛽ Додати заправку", callback_data="add_refuel")],
                [InlineKeyboardButton(text="📤 Batch режим", callback_data="smart_start_batch")],
                [InlineKeyboardButton(text="🏠 Головне меню", callback_data="main_menu")],
            ]
        )
        await processing_msg.delete()
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error in smart photo handler: {e}", exc_info=True)
        await processing_msg.delete()
        await message.answer(
            f"❌ Помилка розпізнавання: {str(e)}\n\n"
            f"Спробуйте ще раз або використайте /add"
        )


@router.callback_query(F.data == "smart_add_receipt")
async def smart_add_receipt(callback: CallbackQuery, state: FSMContext):
    """Continue adding refuel after receipt was recognized (лише чек, без пари)"""
    data = await state.get_data()
    receipt = data.get("smart_receipt")
    receipt_file_id = data.get("smart_receipt_file_id")

    if not receipt:
        await callback.answer("❌ Дані чека втрачено", show_alert=True)
        return

    nd = {k: v for k, v in data.items() if k not in SMART_PAIR_KEYS}
    nd.update(
        {
            "receipt": receipt,
            "receipt_file_id": receipt_file_id,
            "photo_datetime": data.get("smart_receipt_photo_datetime"),
            "telegram_message_date": data.get("smart_receipt_telegram_date"),
            "latitude": data.get("smart_receipt_latitude"),
            "longitude": data.get("smart_receipt_longitude"),
        }
    )
    await state.set_data(nd)

    await callback.message.edit_text(
        "⛽ Чи заправили ви бак до повного?\n\n"
        "💡 <b>Це важливо для точного розрахунку витрати палива</b>\n"
        "Витрата розраховується тільки між заправками до повного бака",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Так, до повного", callback_data="full_yes"),
                InlineKeyboardButton(text="❌ Ні, частково", callback_data="full_no")
            ]
        ])
    )

    await state.set_state(RefuelStates.asking_full_tank)
    await callback.answer()


@router.callback_query(F.data == "smart_add_odometer")
async def smart_add_odometer(callback: CallbackQuery, state: FSMContext):
    """User wants to add refuel with this odometer - need receipt first"""
    await callback.message.edit_text(
        "📸 Спочатку надішліть фото <b>чека з АЗС</b>\n\n"
        "Одометр вже збережено, після чека автоматично створю заправку",
        parse_mode="HTML"
    )

    await state.set_state(RefuelStates.waiting_for_receipt)
    await callback.answer()


@router.callback_query(F.data == "smart_start_batch")
async def smart_start_batch(callback: CallbackQuery, state: FSMContext):
    """Start batch mode from smart handler"""
    from bot.handlers.batch_refuel import cmd_batch_refuel

    await callback.answer()
    await callback.message.delete()
    await cmd_batch_refuel(callback.message, state)


@router.callback_query(F.data == "smart_cancel")
async def smart_cancel(callback: CallbackQuery, state: FSMContext):
    """Cancel smart photo action"""
    await state.clear()
    await callback.message.edit_text(
        "❌ Скасовано",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Головне меню", callback_data="main_menu")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "smart_save_album")
async def smart_save_album(callback: CallbackQuery, state: FSMContext):
    """Save all paired refuels from album"""
    from bot.handlers.batch_refuel import save_batch
    from bot.states.refuel_states import BatchRefuelStates

    # Get unique pairs from state
    data = await state.get_data()
    unique_pairs = data.get('unique_pairs', [])

    if not unique_pairs:
        await callback.answer("❌ Немає нових заправок для збереження", show_alert=True)
        return

    # Check if any pairs have missing dates
    pairs_without_date = []
    for i, pair in enumerate(unique_pairs):
        receipt = pair['receipt']
        photo_dt = receipt.get('photo_datetime')
        receipt_date = receipt['data'].date if hasattr(receipt['data'], 'date') else receipt.get('data', {}).get('date')

        if not photo_dt and not receipt_date:
            pairs_without_date.append(i)

    # If there are pairs without dates, ask user what to do
    if pairs_without_date:
        await callback.message.edit_text(
            f"⚠️ <b>Не вдалося розпізнати дату</b> для {len(pairs_without_date)} заправок.\n\n"
            f"Що використати як дату заправки?",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📅 Використати поточну дату", callback_data="date_use_current")],
                [InlineKeyboardButton(text="✏️ Ввести дату вручну", callback_data="date_enter_manually")],
                [InlineKeyboardButton(text="❌ Скасувати", callback_data="smart_cancel")]
            ])
        )
        await callback.answer()
        return

    # Update state with pairs in batch format and set state
    await state.update_data(pairs=unique_pairs)
    await state.set_state(BatchRefuelStates.confirming_batch)

    # Call batch save handler
    await save_batch(callback, state)


@router.callback_query(F.data == "date_use_current")
async def date_use_current(callback: CallbackQuery, state: FSMContext):
    """Use current date/time for pairs without recognized date"""
    from bot.handlers.batch_refuel import save_batch
    from bot.states.refuel_states import BatchRefuelStates

    data = await state.get_data()
    unique_pairs = data.get('unique_pairs', [])

    # Fill missing dates with current datetime
    for pair in unique_pairs:
        receipt = pair['receipt']
        photo_dt = receipt.get('photo_datetime')
        receipt_date = receipt['data'].date if hasattr(receipt['data'], 'date') else receipt.get('data', {}).get('date')

        if not photo_dt and not receipt_date:
            # Set current datetime as photo_datetime
            pair['receipt']['photo_datetime'] = datetime.now()
            logger.info(f"Set current datetime for pair with odometer {pair['odometer']['data'].odometer}")

    # Update state with corrected pairs
    await state.update_data(pairs=unique_pairs)
    await state.set_state(BatchRefuelStates.confirming_batch)

    # Call batch save handler
    await save_batch(callback, state)


@router.callback_query(F.data == "date_enter_manually")
async def date_enter_manually(callback: CallbackQuery, state: FSMContext):
    """Ask user to enter date manually"""
    await callback.message.edit_text(
        "✏️ <b>Введіть дату та час заправки</b>\n\n"
        "Формат: <code>YYYY-MM-DD HH:MM</code>\n"
        "Наприклад: <code>2026-01-25 14:30</code>\n\n"
        "⚠️ Введіть дату та час <b>в вашому локальному часовому поясі</b>",
        parse_mode="HTML"
    )
    await state.set_state(BatchRefuelStates.waiting_manual_date)
    await callback.answer()


@router.message(BatchRefuelStates.waiting_manual_date)
async def receive_manual_date(message: Message, state: FSMContext):
    """Receive manually entered date from user"""
    from bot.handlers.batch_refuel import save_batch

    try:
        # Parse user input
        user_input = message.text.strip()
        refuel_datetime = datetime.strptime(user_input, "%Y-%m-%d %H:%M")

        data = await state.get_data()
        unique_pairs = data.get('unique_pairs', [])

        # Fill missing dates with user-provided datetime
        for pair in unique_pairs:
            receipt = pair['receipt']
            photo_dt = receipt.get('photo_datetime')
            receipt_date = receipt['data'].date if hasattr(receipt['data'], 'date') else receipt.get('data', {}).get('date')

            if not photo_dt and not receipt_date:
                pair['receipt']['photo_datetime'] = refuel_datetime
                logger.info(f"Set manual datetime {refuel_datetime} for pair with odometer {pair['odometer']['data'].odometer}")

        # Update state with corrected pairs
        await state.update_data(pairs=unique_pairs)
        await state.set_state(BatchRefuelStates.confirming_batch)

        # Create a fake callback from message to call save_batch
        # We need to wrap this in a proper flow
        await message.answer("✅ Дата встановлена, зберігаю заправки...")

        # Call save_batch through a synthetic callback
        class SyntheticCallback:
            def __init__(self, msg):
                self.message = msg
                self.from_user = msg.from_user
            async def answer(self, *args, **kwargs):
                pass

        synthetic_callback = SyntheticCallback(message)
        await save_batch(synthetic_callback, state)

    except ValueError:
        await message.answer(
            "❌ <b>Невірний формат дати</b>\n\n"
            "Використайте формат: <code>YYYY-MM-DD HH:MM</code>\n"
            "Наприклад: <code>2026-01-25 14:30</code>",
            parse_mode="HTML"
        )


@router.callback_query(F.data == "smart_continue_batch")
async def smart_continue_batch(callback: CallbackQuery, state: FSMContext):
    """Continue with batch mode using recognized photos"""
    from bot.handlers.batch_refuel import cmd_batch_refuel

    # Get current album results
    data = await state.get_data()
    album_results = data.get('album_results', [])

    # Convert album results to batch photo format
    photos = []
    for result in album_results:
        if result['type'] in ['receipt', 'odometer']:
            photos.append({
                'file_id': result['file_id'],
                'file_type': 'compressed',
                'image_bytes': b'',  # Already processed
                'recognized': True,
                'recognition_result': result
            })

    await callback.answer()
    await callback.message.delete()

    # Start batch mode with existing photos
    await cmd_batch_refuel(callback.message, state)

    # Update with existing photos
    if photos:
        await state.update_data(photos=photos)
