"""
Refuel handling - main handler for adding fuel records
"""
import logging
from datetime import datetime
from decimal import Decimal
from io import BytesIO

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from bot.keyboards.inline import get_confirm_keyboard, get_full_tank_keyboard
from bot.keyboards.menu import get_main_menu, get_back_to_menu_button
from bot.states.refuel_states import RefuelStates
from models.schemas import RefuelCreate
from services.ai_vision.gemini import recognize_receipt, recognize_odometer
from services.currency.exchange_rate import get_exchange_rate_service
from sqlalchemy import select
from models.database import async_session, User, Refuel

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "add_refuel")
async def start_add_refuel_callback(callback: CallbackQuery, state: FSMContext):
    """Start adding refuel from menu button"""
    await callback.answer()
    await cmd_add_refuel(callback.message, state)


@router.message(Command("add"))
async def cmd_add_refuel(message: Message, state: FSMContext):
    """Start the refuel adding process"""
    await state.clear()

    await message.answer(
        "🔵 Надішліть фото чека з АЗС\n\n"
        "💡 <b>Поради для кращого розпізнавання:</b>\n"
        "• Добре освітлення\n"
        "• Чек розгорнутий рівно\n"
        "• Текст чітко читається\n"
        "• Уникайте відблисків\n\n"
        "📎 <b>Порада:</b> Надсилайте фото <b>як документ/файл</b>, щоб зберегти дату та GPS.\n"
        "Telegram стискає звичайні фото і може видаляти метадані.\n\n"
        "Або натисніть /cancel для скасування",
        parse_mode="HTML",
        reply_markup=get_back_to_menu_button()
    )
    await state.set_state(RefuelStates.waiting_for_receipt)
    logger.info(f"User {message.from_user.id} started adding refuel")


@router.message(RefuelStates.waiting_for_receipt, F.photo | F.document)
async def process_receipt(message: Message, state: FSMContext):
    """Process receipt photo or document"""

    processing_msg = await message.answer("⏳ Анализирую чек...")

    try:
        # Get photo or document
        if message.photo:
            # Photo sent as compressed image
            photo = message.photo[-1]
            file = await message.bot.get_file(photo.file_id)
            file_id = photo.file_id
            logger.info(f"Processing receipt as photo (compressed, EXIF may be stripped)")
        elif message.document:
            # Document sent as file (original quality, EXIF preserved)
            document = message.document
            # Check if it's an image file
            if not document.mime_type or not document.mime_type.startswith('image/'):
                await processing_msg.delete()
                await message.answer(
                    "⚠️ Будь ласка, надішліть <b>фото чека</b> (не документ)\n\n"
                    "Або натисніть /cancel для скасування",
                    parse_mode="HTML",
                    reply_markup=get_back_to_menu_button()
                )
                return
            file = await message.bot.get_file(document.file_id)
            file_id = document.file_id
            logger.info(f"Processing receipt as document (uncompressed, EXIF preserved)")
        else:
            await processing_msg.delete()
            await message.answer(
                "⚠️ Будь ласка, надішліть <b>фото чека</b>\n\n"
                "Або натисніть /cancel для скасування",
                parse_mode="HTML",
                reply_markup=get_back_to_menu_button()
            )
            return

        # Download file as BytesIO
        image_bytes = BytesIO()
        await message.bot.download_file(file.file_path, image_bytes)

        # Get image bytes
        image_data = image_bytes.getvalue()

        # Recognize receipt
        receipt_data = await recognize_receipt(image_data)

        # Extract GPS coordinates and datetime from image EXIF
        from services.image import extract_gps_coordinates, extract_datetime_taken
        latitude, longitude = extract_gps_coordinates(image_data)
        photo_datetime = extract_datetime_taken(image_data)

        # Save to state
        await state.update_data(
            receipt=receipt_data.model_dump(),
            receipt_file_id=file_id,
            latitude=float(latitude) if latitude else None,
            longitude=float(longitude) if longitude else None,
            photo_datetime=photo_datetime
        )

        # Get USD rate and convert
        exchange_service = get_exchange_rate_service()
        usd_rate = await exchange_service.get_usd_rate()

        usd_text = ""
        if usd_rate:
            total_usd = Decimal(str(receipt_data.total_cost)) / usd_rate
            usd_text = f"💵 Сума: <b>{receipt_data.total_cost} грн</b> (~${total_usd:.2f})\n"
            await state.update_data(usd_rate=float(usd_rate))
        else:
            usd_text = f"💵 Сума: <b>{receipt_data.total_cost} грн</b>\n"

        # Format message with recognized data
        date_time_text = ""
        if receipt_data.date and receipt_data.time:
            date_time_text = f"📅 Дата: <b>{receipt_data.date} {receipt_data.time}</b>\n"
        elif photo_datetime:
            date_time_text = f"📅 Дата: <b>{photo_datetime.strftime('%Y-%m-%d %H:%M')}</b> (з EXIF фото)\n"
        else:
            now = datetime.now()
            date_time_text = f"📅 Дата: <b>{now.strftime('%Y-%m-%d %H:%M')}</b> (поточний час)\n"

        text = (
            f"✅ <b>Чек розпізнано</b> (впевненість: {receipt_data.confidence}%)\n\n"
            f"📍 АЗС: <b>{receipt_data.station}</b>\n"
            f"⛽ Паливо: <b>{receipt_data.fuel_type}</b>\n"
            f"📊 Літри: <b>{receipt_data.liters} л</b>\n"
            f"💰 Ціна: <b>{receipt_data.price_per_liter} грн/л</b>\n"
            f"{usd_text}"
            f"{date_time_text}\n"
            f"Все вірно?"
        )

        await processing_msg.delete()
        await message.answer(
            text,
            reply_markup=get_confirm_keyboard(),
            parse_mode="HTML"
        )
        await state.set_state(RefuelStates.confirm_receipt)

        logger.info(
            f"Receipt recognized for user {message.from_user.id}: "
            f"{receipt_data.liters}L, {receipt_data.total_cost}₽"
        )

    except ValueError as e:
        # Handle validation errors (missing critical fields)
        logger.error(f"Validation error recognizing receipt: {e}")
        await processing_msg.delete()
        await message.answer(
            f"❌ {str(e)}\n\n"
            f"💡 <b>Рекомендації:</b>\n"
            f"• Переконайтеся, що чек повністю видно\n"
            f"• Перевірте освітлення та чіткість\n"
            f"• Спробуйте сфотографувати чек ще раз\n\n"
            f"Надішліть нове фото чека або /cancel для скасування",
            parse_mode="HTML",
            reply_markup=get_back_to_menu_button()
        )
    except Exception as e:
        logger.error(f"Error recognizing receipt: {e}", exc_info=True)
        await processing_msg.delete()
        await message.answer(
            f"❌ Не вдалося розпізнати чек: {str(e)}\n\n"
            f"Спробуйте інше фото або /cancel",
            reply_markup=get_back_to_menu_button()
        )


@router.message(RefuelStates.waiting_for_receipt)
async def invalid_receipt_input(message: Message):
    """Handle invalid input when waiting for receipt"""
    await message.answer(
        "⚠️ Будь ласка, надішліть <b>фото чека</b> або натисніть /cancel для скасування",
        parse_mode="HTML",
        reply_markup=get_back_to_menu_button()
    )


@router.callback_query(RefuelStates.confirm_receipt, F.data == "confirm")
async def receipt_confirmed(callback: CallbackQuery, state: FSMContext):
    """Handle receipt confirmation"""
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "⛽ Чи заправили ви бак до повного?\n\n"
        "💡 <b>Це важливо для точного розрахунку витрати палива</b>\n"
        "Витрата розраховується тільки між заправками до повного бака",
        reply_markup=get_full_tank_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(RefuelStates.asking_full_tank)
    await callback.answer()
    logger.info(f"User {callback.from_user.id} confirmed receipt")


@router.callback_query(RefuelStates.asking_full_tank, F.data == "full_yes")
async def full_tank_yes(callback: CallbackQuery, state: FSMContext):
    """Handle full tank confirmation"""
    await state.update_data(full_tank=True)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "📸 Тепер відправте фото спідометра/одометра\n\n"
        "💡 <b>Важливо:</b>\n"
        "• Показання пробігу мають бути чітко видні\n"
        "• Знімайте загальний пробіг, не добовий\n\n"
        "Або /cancel для скасування",
        parse_mode="HTML"
    )
    await state.set_state(RefuelStates.waiting_for_odometer)
    await callback.answer()
    logger.info(f"User {callback.from_user.id} confirmed full tank")


@router.callback_query(RefuelStates.asking_full_tank, F.data == "full_no")
async def full_tank_no(callback: CallbackQuery, state: FSMContext):
    """Handle partial tank confirmation"""
    await state.update_data(full_tank=False)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "📸 Тепер відправте фото спідометра/одометра\n\n"
        "💡 <b>Важливо:</b>\n"
        "• Показання пробігу мають бути чітко видні\n"
        "• Знімайте загальний пробіг, не добовий\n\n"
        "Або /cancel для скасування",
        parse_mode="HTML"
    )
    await state.set_state(RefuelStates.waiting_for_odometer)
    await callback.answer()
    logger.info(f"User {callback.from_user.id} confirmed partial tank")


@router.callback_query(RefuelStates.confirm_receipt, F.data == "retry")
async def receipt_retry(callback: CallbackQuery, state: FSMContext):
    """Handle receipt retry"""
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "🔄 Гаразд, надішліть нове фото чека\n\n"
        "Або /cancel для скасування",
        reply_markup=get_back_to_menu_button()
    )
    await state.set_state(RefuelStates.waiting_for_receipt)
    await callback.answer()


@router.callback_query(RefuelStates.confirm_receipt, F.data == "edit")
async def receipt_edit(callback: CallbackQuery):
    """Handle receipt edit request"""
    await callback.answer("⚠️ Функція редагування поки не реалізована. Використовуйте 'Повторити'")


@router.message(RefuelStates.waiting_for_odometer, F.photo)
async def process_odometer(message: Message, state: FSMContext):
    """Process odometer photo"""

    processing_msg = await message.answer("⏳ Анализирую одометр...")

    try:
        # Get photo
        photo = message.photo[-1]
        file = await message.bot.get_file(photo.file_id)

        # Download file as BytesIO
        image_bytes = BytesIO()
        await message.bot.download_file(file.file_path, image_bytes)

        # Recognize odometer
        odometer_data = await recognize_odometer(image_bytes.getvalue())

        # Save to state
        await state.update_data(
            odometer=odometer_data.model_dump(),
            odometer_file_id=photo.file_id
        )

        # Get receipt data to know the refuel date
        data = await state.get_data()
        receipt = data.get('receipt', {})

        # Parse refuel datetime from receipt
        refuel_datetime = None
        if receipt.get('date') and receipt.get('time'):
            refuel_datetime = datetime.strptime(
                f"{receipt['date']} {receipt['time']}",
                "%Y-%m-%d %H:%M"
            )
        elif data.get('photo_datetime'):
            refuel_datetime = data['photo_datetime']

        # Get previous FULL TANK refuel BEFORE this refuel's date to calculate distance
        user_id = message.from_user.id
        last_full_refuel = None

        async with async_session() as session:
            query = (
                select(Refuel)
                .where(Refuel.user_id == user_id)
                .where(Refuel.full_tank == True)  # Only full tank refuels
                .order_by(Refuel.date.desc())
            )

            # If we know the refuel date, only get refuels BEFORE this date
            if refuel_datetime:
                query = query.where(Refuel.date < refuel_datetime)

            query = query.limit(1)
            result = await session.execute(query)
            last_full_refuel = result.scalar_one_or_none()

        distance_text = ""
        if last_full_refuel:
            distance = odometer_data.odometer - last_full_refuel.odometer
            if distance > 0:
                distance_text = f"🛣 Пробіг з останньої заправки до повного: <b>{distance} км</b>\n"
                await state.update_data(distance_from_last=distance)

        text = (
            f"✅ <b>Одометр распознан</b> (уверенность: {odometer_data.confidence}%)\n\n"
            f"🔢 Пробег: <b>{odometer_data.odometer} км</b>\n"
            f"{distance_text}\n"
            f"Все верно?"
        )

        await processing_msg.delete()
        await message.answer(
            text,
            reply_markup=get_confirm_keyboard(),
            parse_mode="HTML"
        )
        await state.set_state(RefuelStates.confirm_odometer)

        logger.info(
            f"Odometer recognized for user {message.from_user.id}: "
            f"{odometer_data.odometer} km"
        )

    except Exception as e:
        logger.error(f"Error recognizing odometer: {e}", exc_info=True)
        await processing_msg.delete()
        await message.answer(
            f"❌ Не вдалося розпізнати одометр: {str(e)}\n\n"
            f"Спробуйте інше фото або /cancel",
            reply_markup=get_back_to_menu_button()
        )


@router.message(RefuelStates.waiting_for_odometer)
async def invalid_odometer_input(message: Message):
    """Handle invalid input when waiting for odometer"""
    await message.answer(
        "⚠️ Будь ласка, надішліть <b>фото одометра</b> або натисніть /cancel для скасування",
        parse_mode="HTML",
        reply_markup=get_back_to_menu_button()
    )


@router.callback_query(RefuelStates.confirm_odometer, F.data == "confirm")
async def odometer_confirmed(callback: CallbackQuery, state: FSMContext):
    """Handle odometer confirmation and save refuel record"""
    await callback.message.edit_reply_markup(reply_markup=None)

    saving_msg = await callback.message.answer("💾 Сохраняю данные...")

    try:
        # Get all data from state
        data = await state.get_data()
        receipt = data['receipt']
        odometer = data['odometer']

        user_id = callback.from_user.id

        # Ensure user exists in database
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = result.scalar_one_or_none()

            if not user:
                user = User(
                    telegram_id=user_id,
                    username=callback.from_user.username,
                    first_name=callback.from_user.first_name
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)

        # Calculate consumption ONLY if current refuel is full tank AND we have distance from previous full tank
        consumption = None
        distance_from_last = data.get('distance_from_last')
        full_tank = data.get('full_tank', True)

        if full_tank and distance_from_last and distance_from_last > 0:
            # Only calculate if this is a full tank refuel
            consumption = (Decimal(str(receipt['liters'])) / Decimal(str(distance_from_last))) * 100

        # Parse datetime - prefer receipt date, then photo EXIF, then current time
        if receipt.get('date') and receipt.get('time'):
            refuel_datetime = datetime.strptime(
                f"{receipt['date']} {receipt['time']}",
                "%Y-%m-%d %H:%M"
            )
            logger.info(f"Using date from receipt: {refuel_datetime}")
        elif data.get('photo_datetime'):
            refuel_datetime = data['photo_datetime']
            logger.info(f"Date not found on receipt, using photo EXIF: {refuel_datetime}")
        else:
            # If date/time not found anywhere, use current time
            refuel_datetime = datetime.now()
            logger.warning(f"Date/time not found on receipt or photo EXIF for user {user_id}, using current time: {refuel_datetime}")

        # Get USD exchange rate for the refuel date and convert
        exchange_service = get_exchange_rate_service()
        usd_rate = await exchange_service.get_usd_rate(refuel_datetime)

        total_cost_usd = None
        price_per_liter_usd = None

        if usd_rate:
            total_cost_dec = Decimal(str(receipt['total_cost']))
            price_per_liter_dec = Decimal(str(receipt['price_per_liter']))

            total_cost_usd = await exchange_service.convert_uah_to_usd(total_cost_dec)
            price_per_liter_usd = await exchange_service.convert_uah_to_usd(price_per_liter_dec)

            logger.info(f"Converted to USD: {total_cost_usd} USD (rate: {usd_rate})")

        # Validate refuel and determine full_tank automatically
        from services.refuel_validator import validate_and_determine_full_tank, estimate_refuel_date

        # Validate odometer and determine if tank was full
        validated_full_tank, error_msg = await validate_and_determine_full_tank(
            user_id=user.id,  # Use internal user.id
            odometer=odometer['odometer'],
            liters=float(receipt['liters']),
            refuel_date=refuel_datetime
        )

        if error_msg:
            # Validation failed - reject refuel
            await saving_msg.delete()
            await callback.message.answer(
                error_msg,
                parse_mode="HTML",
                reply_markup=get_back_to_menu_button()
            )
            await state.clear()
            return

        # Override full_tank with validated value
        full_tank = validated_full_tank
        logger.info(f"Full tank validated: {full_tank}")

        # Estimate correct date if needed (based on odometer)
        refuel_datetime = await estimate_refuel_date(
            user_id=user.id,
            odometer=odometer['odometer'],
            recognized_date=refuel_datetime
        )

        # Recalculate consumption with validated full_tank
        consumption = None
        if full_tank and distance_from_last and distance_from_last > 0:
            consumption = (Decimal(str(receipt['liters'])) / Decimal(str(distance_from_last))) * 100

        # Create refuel record
        refuel_data = RefuelCreate(
            user_id=user.id,  # Use internal user.id
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
            distance_from_last=distance_from_last,
            consumption=consumption,
            full_tank=full_tank,
            latitude=Decimal(str(data['latitude'])) if data.get('latitude') else None,
            longitude=Decimal(str(data['longitude'])) if data.get('longitude') else None,
            receipt_file_id=data['receipt_file_id'],
            odometer_file_id=data.get('odometer_file_id'),
            ai_confidence=min(receipt['confidence'], odometer['confidence'])
        )

        # Save to database
        async with async_session() as session:
            refuel = Refuel(**refuel_data.model_dump())
            session.add(refuel)
            await session.commit()
            await session.refresh(refuel)

        # Format success message
        success_text = (
            "✅ <b>Заправку успішно додано!</b>\n\n"
            f"📍 АЗС: {receipt['station']}\n"
            f"⛽ Паливо: {receipt['fuel_type']}\n"
            f"📊 Літри: {receipt['liters']} л\n"
            f"💵 Сума: {receipt['total_cost']} грн\n"
        )

        if total_cost_usd:
            success_text += f"💰 В USD: ${total_cost_usd:.2f} (курс: {usd_rate:.2f})\n"

        success_text += f"🔢 Пробіг: {odometer['odometer']} км\n"

        if distance_from_last:
            success_text += f"🛣 Проїхано: {distance_from_last} км\n"

        if consumption:
            success_text += f"⛽ Витрата: {consumption:.2f} л/100км\n"

        await saving_msg.delete()
        await callback.message.answer(success_text, parse_mode="HTML", reply_markup=get_main_menu())

        # Clear state
        await state.clear()

        logger.info(
            f"Refuel record saved for user {user_id}: "
            f"{refuel.id}, {refuel.liters}L, {refuel.total_cost}₽"
        )

    except Exception as e:
        logger.error(f"Error saving refuel record: {e}", exc_info=True)
        await saving_msg.delete()
        await callback.message.answer(
            f"❌ Помилка при збереженні даних: {str(e)}",
            reply_markup=get_main_menu()
        )
        await state.clear()


@router.callback_query(RefuelStates.confirm_odometer, F.data == "retry")
async def odometer_retry(callback: CallbackQuery, state: FSMContext):
    """Handle odometer retry"""
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "🔄 Гаразд, надішліть нове фото одометра\n\n"
        "Або /cancel для скасування",
        reply_markup=get_back_to_menu_button()
    )
    await state.set_state(RefuelStates.waiting_for_odometer)
    await callback.answer()


@router.callback_query(RefuelStates.confirm_odometer, F.data == "edit")
async def odometer_edit(callback: CallbackQuery):
    """Handle odometer edit request"""
    await callback.answer("⚠️ Функція редагування поки не реалізована. Використовуйте 'Повторити'")
