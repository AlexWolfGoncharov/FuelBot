"""
Smart photo handler - automatically detects photo type and suggests actions
"""
import asyncio
import logging
from io import BytesIO

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.states.refuel_states import RefuelStates, BatchRefuelStates
from bot.utils.user_helpers import get_user_id_by_telegram_id
from services.ai_vision.gemini import recognize_smart
from models.database import async_session, Refuel
from sqlalchemy import select, and_
from datetime import datetime, timedelta

router = Router()
logger = logging.getLogger(__name__)

# Storage for media group processing
media_group_storage = {}
media_group_timers = {}


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
                    'photo_datetime': photo['photo_datetime']
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
    """
    # Check if there's an active state - if yes, skip this handler
    current_state = await state.get_state()
    if current_state is not None:
        return

    # Get internal user_id from telegram_id
    user_id = await get_user_id_by_telegram_id(message.from_user.id)
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

        recognized_type = result['type']
        recognized_data = result['data']

        # Build response based on what was recognized
        if recognized_type == 'receipt':
            # Receipt detected
            text = (
                f"✅ <b>Розпізнав чек з АЗС</b> (впевненість: {recognized_data.confidence}%)\n\n"
                f"📍 АЗС: <b>{recognized_data.station}</b>\n"
                f"⛽ Паливо: <b>{recognized_data.fuel_type}</b>\n"
            )

            # Show refund info if present
            if hasattr(recognized_data, 'has_refund') and recognized_data.has_refund:
                text += (
                    f"📊 Літри: <b>{recognized_data.liters} л</b> "
                    f"(залито - повернуто: {recognized_data.refund_liters} л)\n"
                    f"💰 Сума: <b>{recognized_data.total_cost} грн</b> "
                    f"(сплачено - повернуто: {recognized_data.refund_amount} грн)\n"
                )
            else:
                text += (
                    f"📊 Літри: <b>{recognized_data.liters} л</b>\n"
                    f"💰 Сума: <b>{recognized_data.total_cost} грн</b>\n"
                )

            text += (
                f"💵 Ціна: <b>{recognized_data.price_per_liter} грн/л</b>\n"
                f"📅 Дата: <b>{recognized_data.date} {recognized_data.time}</b>\n\n"
                "Що робити далі?"
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Додати цю заправку", callback_data="smart_add_receipt")],
                [InlineKeyboardButton(text="📤 Почати batch режим", callback_data="smart_start_batch")],
                [InlineKeyboardButton(text="❌ Скасувати", callback_data="smart_cancel")]
            ])

            # Save receipt data to state
            await state.update_data(
                smart_receipt=recognized_data.model_dump(),
                smart_receipt_file_id=file_id
            )

        elif recognized_type == 'odometer':
            # Odometer detected
            text = (
                f"✅ <b>Розпізнав одометр</b> (впевненість: {recognized_data.confidence}%)\n\n"
                f"🔢 Пробіг: <b>{recognized_data.odometer} км</b>\n\n"
                "Що робити далі?"
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Додати з цим одометром", callback_data="smart_add_odometer")],
                [InlineKeyboardButton(text="📤 Почати batch режим", callback_data="smart_start_batch")],
                [InlineKeyboardButton(text="❌ Скасувати", callback_data="smart_cancel")]
            ])

            # Save odometer data to state
            await state.update_data(
                smart_odometer=recognized_data.model_dump(),
                smart_odometer_file_id=file_id
            )

        else:
            # Could not recognize
            text = (
                "❓ <b>Не вдалося розпізнати фото</b>\n\n"
                "Це може бути чек або одометр?\n"
                "Спробуйте:\n"
                "• Краще освітлення 💡\n"
                "• Чіткіше фото 📸\n"
                "• Розгорнутий документ 📄\n\n"
                "Або почніть вручну:"
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⛽ Додати заправку", callback_data="add_refuel")],
                [InlineKeyboardButton(text="📤 Batch режим", callback_data="smart_start_batch")],
                [InlineKeyboardButton(text="🏠 Головне меню", callback_data="main_menu")]
            ])

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
    """Continue adding refuel after receipt was recognized"""
    data = await state.get_data()
    receipt = data.get('smart_receipt')
    receipt_file_id = data.get('smart_receipt_file_id')

    if not receipt:
        await callback.answer("❌ Дані чека втрачено", show_alert=True)
        return

    # Save to state in format expected by refuel handler
    await state.update_data(
        receipt=receipt,
        receipt_file_id=receipt_file_id
    )

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
