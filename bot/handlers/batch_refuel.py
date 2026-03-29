"""
Batch refuel upload - handle multiple photos at once
"""
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select

from bot.keyboards.inline import get_confirm_keyboard
from bot.keyboards.menu import get_main_menu, get_back_to_menu_button
from bot.states.refuel_states import BatchRefuelStates
from bot.utils.user_helpers import get_user_id_by_telegram_id
from models.database import async_session, User, Refuel
from models.schemas import RefuelCreate
from services.ai_vision.gemini import recognize_smart
from services.currency.exchange_rate import get_exchange_rate_service
from services.image.exif_extractor import extract_datetime_taken
from sqlalchemy import and_

router = Router()
logger = logging.getLogger(__name__)


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


@router.message(Command("batch"))
async def cmd_batch_refuel(message: Message, state: FSMContext):
    """Start batch refuel upload"""
    await state.clear()

    text = (
        "📤 <b>Масова завантаження заправок</b>\n\n"
        "Відправте <b>всі фото одразу</b> (як альбом або окремо):\n"
        "• Фото чеків\n"
        "• Фото одометрів\n\n"
        "Я автоматично розпізнаю та розподілю їх по парам.\n\n"
        "💡 <b>Порада:</b> Найкраще відправляти в такому порядку:\n"
        "чек 1 → одометр 1 → чек 2 → одометр 2 ...\n\n"
        "Коли завантажите всі фото, натисніть /done"
    )

    await message.answer(text, parse_mode="HTML", reply_markup=get_back_to_menu_button())
    await state.set_state(BatchRefuelStates.collecting_photos)
    await state.update_data(photos=[])
    logger.info(f"User {message.from_user.id} started batch refuel upload")


@router.message(BatchRefuelStates.collecting_photos, F.photo | F.document)
async def collect_photos(message: Message, state: FSMContext):
    """Collect photos from user"""
    data = await state.get_data()
    photos = data.get('photos', [])

    # Get file info
    if message.photo:
        photo = message.photo[-1]
        file_id = photo.file_id
        file_type = "compressed"
        # For compressed photos, use message.date (Telegram strips EXIF)
        # Convert to naive datetime (remove timezone info)
        photo_datetime = message.date.replace(tzinfo=None) if message.date.tzinfo else message.date
    elif message.document:
        if not message.document.mime_type or not message.document.mime_type.startswith('image/'):
            await message.answer("⚠️ Будь ласка, надсилайте тільки фото")
            return
        file_id = message.document.file_id
        file_type = "document"
        # For documents, we'll extract EXIF later
        photo_datetime = None
    else:
        return

    # Download photo
    file = await message.bot.get_file(file_id)
    image_bytes = BytesIO()
    await message.bot.download_file(file.file_path, image_bytes)

    photos.append({
        'file_id': file_id,
        'file_type': file_type,
        'image_bytes': image_bytes.getvalue(),
        'message_id': message.message_id,
        'message_date': photo_datetime  # Add message date
    })

    await state.update_data(photos=photos)

    # Show progress
    await message.answer(
        f"✅ Фото {len(photos)} додано\n"
        f"Продовжуйте відправляти фото або натисніть /done для обробки"
    )


@router.message(BatchRefuelStates.collecting_photos, Command("done"))
async def process_batch(message: Message, state: FSMContext):
    """Process collected photos"""
    data = await state.get_data()
    photos = data.get('photos', [])

    if len(photos) < 2:
        await message.answer(
            "⚠️ Потрібно мінімум 2 фото (чек + одометр)\n"
            "Продовжуйте відправляти фото або натисніть /cancel",
            reply_markup=get_back_to_menu_button()
        )
        return

    # Get internal user_id from telegram_id
    user_id = await get_user_id_by_telegram_id(message.from_user.id)

    processing_msg = await message.answer(
        f"⏳ Обробляю {len(photos)} фото...\n"
        f"Це може зайняти деякий час"
    )

    try:
        # STEP 1: Collect all photos with timestamps (before OCR)
        await processing_msg.edit_text("⏳ Збираю timestamp фото...")

        photos_with_time = []
        for i, photo in enumerate(photos, 1):
            # Get datetime: EXIF for documents, message.date for compressed
            photo_datetime = None
            if photo.get('message_date'):
                # Compressed photo - use Telegram message date
                photo_datetime = photo['message_date']
                logger.info(f"DEBUG Photo {i}: Compressed, message_date = {photo_datetime}")
            else:
                # Document - try EXIF
                exif_datetime = extract_datetime_taken(photo['image_bytes'])
                if exif_datetime:
                    photo_datetime = exif_datetime
                    logger.info(f"DEBUG Photo {i}: Document, EXIF datetime = {photo_datetime}")
                else:
                    logger.warning(f"DEBUG Photo {i}: No EXIF datetime found")
                    photo_datetime = datetime.now()  # Fallback

            photos_with_time.append({
                'file_id': photo['file_id'],
                'image_bytes': photo['image_bytes'],
                'photo_datetime': photo_datetime
            })

        # STEP 2: Sort by timestamp
        photos_with_time.sort(key=lambda x: x['photo_datetime'])
        logger.info(f"DEBUG batch: Sorted {len(photos_with_time)} photos by timestamp")

        # STEP 3: Pair adjacent photos (1-2, 3-4, 5-6...)
        candidate_pairs = []
        for i in range(0, len(photos_with_time) - 1, 2):
            pair = [photos_with_time[i], photos_with_time[i+1]]
            time_diff = abs(pair[1]['photo_datetime'] - pair[0]['photo_datetime'])
            logger.info(f"DEBUG batch: Candidate pair {i//2 + 1}: {pair[0]['photo_datetime']} <-> {pair[1]['photo_datetime']}, diff={time_diff}")
            candidate_pairs.append(pair)

        # Handle odd number of photos
        unpaired_photos = []
        if len(photos_with_time) % 2 == 1:
            unpaired_photos.append(photos_with_time[-1])
            logger.warning(f"DEBUG batch: Odd number of photos, last one unpaired")

        # STEP 4: OCR each pair and verify one is receipt, other is odometer
        receipts_count = 0
        odometers_count = 0
        unknown_count = 0
        pairs = []
        duplicates = []
        invalid_pairs = []

        # Get user context from recent refuels (for better OCR accuracy)
        from services.ai_vision.gemini import get_user_refuel_context
        user_context = await get_user_refuel_context(user_id)

        for pair_idx, pair in enumerate(candidate_pairs, 1):
            await processing_msg.edit_text(f"⏳ Обробка пари {pair_idx}/{len(candidate_pairs)}...")

            # OCR both photos in pair
            results_in_pair = []
            for photo in pair:
                result = await recognize_smart(photo['image_bytes'], user_context)
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
                is_duplicate = await check_duplicate_refuel(
                    user_id,
                    receipt_item['data'],
                    odometer_item['data'],
                    receipt_item['photo_datetime']
                )

                if is_duplicate:
                    duplicates.append({'receipt': receipt_item, 'odometer': odometer_item})
                else:
                    pairs.append({'receipt': receipt_item, 'odometer': odometer_item})
            else:
                logger.warning(f"⚠️ Pair {pair_idx} is not valid: {results_in_pair[0]['type']} + {results_in_pair[1]['type']}")
                invalid_pairs.extend(results_in_pair)

        # Build summary
        summary = (
            f"📊 <b>Результати розпізнавання:</b>\n\n"
            f"✅ Чеків: {receipts_count}\n"
            f"✅ Одометрів: {odometers_count}\n"
        )

        if unknown_count:
            summary += f"❓ Нерозпізнано: {unknown_count}\n"

        summary += f"\n"

        if duplicates:
            summary += f"⚠️ Дублікатів: {len(duplicates)} (вже в базі)\n"
        if pairs:
            summary += f"✅ Сформовано {len(pairs)} нових пар(и)\n\n"
        elif duplicates:
            summary += f"❌ Всі заправки вже є в базі\n\n"

        # Check if nothing was successfully paired
        if not pairs and not duplicates:
            await processing_msg.edit_text(
                summary + "\n❌ Не вдалося створити жодної валідної пари (чек + одометр)",
                parse_mode="HTML",
                reply_markup=get_back_to_menu_button()
            )
            await state.clear()
            return

        # Show pairs for confirmation
        if pairs:
            summary += "<b>📋 Готові до збереження:</b>\n\n"
            for i, pair in enumerate(pairs, 1):
                receipt = pair['receipt']['data']
                odometer = pair['odometer']['data']

                summary += (
                    f"<b>{i}. Заправка</b>\n"
                    f"📍 {receipt.station}\n"
                    f"⛽ {receipt.fuel_type}: {receipt.liters}л × {receipt.price_per_liter}грн = {receipt.total_cost}грн\n"
                    f"🔢 Одометр: {odometer.odometer} км\n"
                    f"📅 {receipt.date} {receipt.time}\n\n"
                )

        # Show invalid pairs (not receipt+odometer combination)
        if invalid_pairs:
            summary += f"<b>⚠️ Невалідні пари ({len(invalid_pairs)//2}):</b> фото що не утворили пару чек+одометр\n\n"

        # Check if any pairs have missing dates
        pairs_without_date = []
        if pairs:
            for i, pair in enumerate(pairs):
                receipt = pair['receipt']
                photo_dt = receipt.get('photo_datetime')
                receipt_date = receipt['data'].date if hasattr(receipt['data'], 'date') else None

                if not photo_dt and not receipt_date:
                    pairs_without_date.append(i)
                    logger.warning(f"Pair {i} has no date: receipt={receipt['data'].station}, odo={pair['odometer']['data'].odometer}")

        # If there are pairs without dates, ask user what to do
        if pairs_without_date:
            await processing_msg.edit_text(
                f"⚠️ <b>Не вдалося розпізнати дату</b> для {len(pairs_without_date)} заправок.\n\n"
                f"Що використати як дату заправки?",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📅 Використати поточну дату", callback_data="batch_date_use_current")],
                    [InlineKeyboardButton(text="✏️ Ввести дату вручну", callback_data="batch_date_enter_manually")],
                    [InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel")]
                ])
            )
            await state.update_data(pairs=pairs)
            return

        if pairs:
            summary += f"Зберегти {len(pairs)} заправок?"
        else:
            summary += "❌ Немає повних пар для збереження"

        await processing_msg.edit_text(
            summary,
            parse_mode="HTML",
            reply_markup=get_confirm_keyboard() if pairs else get_back_to_menu_button()
        )

        if pairs:
            await state.update_data(pairs=pairs)
            await state.set_state(BatchRefuelStates.confirming_batch)
        else:
            await state.clear()

    except Exception as e:
        logger.error(f"Error processing batch: {e}", exc_info=True)
        await processing_msg.edit_text(
            f"❌ Помилка обробки: {str(e)}",
            reply_markup=get_back_to_menu_button()
        )
        await state.clear()


@router.callback_query(BatchRefuelStates.confirming_batch, F.data == "confirm")
async def save_batch(callback: CallbackQuery, state: FSMContext):
    """Save all paired refuels"""
    await callback.message.edit_reply_markup(reply_markup=None)

    saving_msg = await callback.message.answer("💾 Зберігаю заправки...")

    try:
        data = await state.get_data()
        pairs = data.get('pairs', [])

        # Get internal user_id from telegram_id
        telegram_id = callback.from_user.id

        # Ensure user exists
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()

            if not user:
                user = User(
                    telegram_id=telegram_id,
                    username=callback.from_user.username,
                    first_name=callback.from_user.first_name
                )
                session.add(user)
                await session.commit()

            # Get internal user_id
            user_id = user.id

        # Get exchange service
        exchange_service = get_exchange_rate_service()

        saved_count = 0

        for pair in pairs:
            receipt = pair['receipt']['data'].model_dump()
            odometer = pair['odometer']['data'].model_dump()

            # Use photo datetime if available (message.date or EXIF), fallback to receipt date
            photo_datetime = pair['receipt'].get('photo_datetime')
            if photo_datetime:
                refuel_datetime = photo_datetime
                logger.info(f"Using photo datetime: {refuel_datetime}")
            elif receipt.get('date'):
                refuel_datetime = datetime.strptime(
                    f"{receipt['date']} {receipt['time']}" if receipt.get('time') else receipt['date'],
                    "%Y-%m-%d %H:%M" if receipt.get('time') else "%Y-%m-%d"
                )
                logger.info(f"Using receipt datetime: {refuel_datetime}")
            else:
                # No date available - use current time
                refuel_datetime = datetime.now()
                logger.warning(f"No datetime available, using current time: {refuel_datetime}")

            # Calculate price_per_liter if not provided
            if not receipt.get('price_per_liter'):
                if receipt['liters'] > 0 and receipt['total_cost'] > 0:
                    receipt['price_per_liter'] = receipt['total_cost'] / receipt['liters']
                    logger.info(f"Calculated price_per_liter: {receipt['price_per_liter']:.2f}")
                else:
                    logger.error(f"Cannot calculate price_per_liter: liters={receipt['liters']}, cost={receipt['total_cost']}")
                    continue  # Skip this pair

            # Get USD rate
            usd_rate = await exchange_service.get_usd_rate(refuel_datetime)
            total_cost_usd = None
            price_per_liter_usd = None

            if usd_rate:
                total_cost_dec = Decimal(str(receipt['total_cost']))
                price_per_liter_dec = Decimal(str(receipt['price_per_liter']))
                total_cost_usd = await exchange_service.convert_uah_to_usd(total_cost_dec)
                price_per_liter_usd = await exchange_service.convert_uah_to_usd(price_per_liter_dec)

            # Create refuel record
            refuel_data = RefuelCreate(
                user_id=user_id,
                date=refuel_datetime,
                station_name=receipt['station'],
                fuel_type=receipt['fuel_type'],
                liters=Decimal(str(receipt['liters'])),
                price_per_liter=Decimal(str(receipt['price_per_liter'])),
                total_cost=Decimal(str(receipt['total_cost'])),
                usd_rate=usd_rate,
                total_cost_usd=total_cost_usd,
                price_per_liter_usd=price_per_liter_usd,
                odometer=odometer['odometer'],
                full_tank=True,  # Assume full tank for batch
                receipt_file_id=pair['receipt']['file_id'],
                odometer_file_id=pair['odometer']['file_id'],
                ai_confidence=min(receipt['confidence'], odometer['confidence'])
            )

            async with async_session() as session:
                refuel = Refuel(**refuel_data.model_dump())
                session.add(refuel)
                await session.commit()

            saved_count += 1

        await saving_msg.delete()
        await callback.message.answer(
            f"✅ <b>Успішно збережено {saved_count} заправок!</b>",
            parse_mode="HTML",
            reply_markup=get_main_menu()
        )

        await state.clear()
        logger.info(f"User {user_id} saved {saved_count} refuels via batch upload")

    except Exception as e:
        logger.error(f"Error saving batch: {e}", exc_info=True)
        await saving_msg.delete()
        await callback.message.answer(
            f"❌ Помилка збереження: {str(e)}",
            reply_markup=get_main_menu()
        )
        await state.clear()


@router.callback_query(BatchRefuelStates.confirming_batch, F.data == "retry")
async def batch_retry(callback: CallbackQuery, state: FSMContext):
    """Retry batch upload"""
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.clear()
    await cmd_batch_refuel(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "batch_date_use_current")
async def batch_date_use_current(callback: CallbackQuery, state: FSMContext):
    """Use current date/time for pairs without recognized date"""
    data = await state.get_data()
    pairs = data.get('pairs', [])

    # Fill missing dates with current datetime
    for pair in pairs:
        receipt = pair['receipt']
        photo_dt = receipt.get('photo_datetime')
        receipt_date = receipt['data'].date if hasattr(receipt['data'], 'date') else None

        if not photo_dt and not receipt_date:
            # Set current datetime as photo_datetime
            pair['receipt']['photo_datetime'] = datetime.now()
            logger.info(f"Set current datetime for pair with odometer {pair['odometer']['data'].odometer}")

    # Update state with corrected pairs
    await state.update_data(pairs=pairs)
    await state.set_state(BatchRefuelStates.confirming_batch)

    # Call save_batch
    await save_batch(callback, state)


@router.callback_query(F.data == "batch_date_enter_manually")
async def batch_date_enter_manually(callback: CallbackQuery, state: FSMContext):
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
async def batch_receive_manual_date(message: Message, state: FSMContext):
    """Receive manually entered date from user in batch mode"""
    try:
        # Parse user input
        user_input = message.text.strip()
        refuel_datetime = datetime.strptime(user_input, "%Y-%m-%d %H:%M")

        data = await state.get_data()
        pairs = data.get('pairs', [])

        # Fill missing dates with user-provided datetime
        for pair in pairs:
            receipt = pair['receipt']
            photo_dt = receipt.get('photo_datetime')
            receipt_date = receipt['data'].date if hasattr(receipt['data'], 'date') else None

            if not photo_dt and not receipt_date:
                pair['receipt']['photo_datetime'] = refuel_datetime
                logger.info(f"Set manual datetime {refuel_datetime} for pair with odometer {pair['odometer']['data'].odometer}")

        # Update state with corrected pairs
        await state.update_data(pairs=pairs)
        await state.set_state(BatchRefuelStates.confirming_batch)

        # Create a synthetic callback to call save_batch
        msg = await message.answer("✅ Дата встановлена, зберігаю заправки...")

        class SyntheticCallback:
            def __init__(self, msg):
                self.message = msg
                self.from_user = msg.from_user
            async def answer(self, *args, **kwargs):
                pass

        synthetic_callback = SyntheticCallback(msg)
        await save_batch(synthetic_callback, state)

    except ValueError:
        await message.answer(
            "❌ <b>Невірний формат дати</b>\n\n"
            "Використайте формат: <code>YYYY-MM-DD HH:MM</code>\n"
            "Наприклад: <code>2026-01-25 14:30</code>",
            parse_mode="HTML"
        )
