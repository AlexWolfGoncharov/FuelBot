"""
Gemini Vision API integration for image recognition
"""
import json
import logging
from io import BytesIO
from typing import Optional

from google import genai
from google.genai.types import GenerateContentConfig, GoogleSearch
from PIL import Image
from pillow_heif import register_heif_opener

# Register HEIF opener to support HEIC files
register_heif_opener()

from config.settings import settings
from models.schemas import ReceiptData, OdometerData
from services.ai_vision.prompts import RECEIPT_RECOGNITION_PROMPT, ODOMETER_RECOGNITION_PROMPT
from services.ai_vision.receipt_normalize import normalize_receipt_fields

logger = logging.getLogger(__name__)

# Configure Gemini API client
client = genai.Client(api_key=settings.gemini_api_key)


SMART_RECOGNITION_PROMPT = """Проаналізуй це зображення і визнач, що на ньому: чек з АЗС чи одометр авто.

ВАЖЛИВО: Поверни JSON у ТОЧНО такому форматі:

{
  "type": "receipt" або "odometer" або "unknown",
  "data": {...дані чека або одометра...}
}

Якщо це ЧЕК З АЗС, type="receipt" і data містить:
{
  "station": "КОНКРЕТНИЙ НОМЕР АЗС (наприклад: АЗК № 104, АЗС-магазин №60, WOG, OKKO) - НЕ назву компанії!",
  "liters": число літрів,
  "price_per_liter": ціна за літр,
  "total_cost": загальна вартість,
  "fuel_type": "тип палива",
  "date": "YYYY-MM-DD",
  "time": "HH:MM",
  "confidence": відсоток впевненості (0-100)
}

**КРИТИЧНО ДЛЯ STATION**: Шукай НОМЕР конкретної заправки (АЗК №104, АЗС №60), а НЕ просто назву компанії (НЕ "Укрпалетсистем")!

**ДАТА/ЧАС**: Бери з рядків **ДАТА/ЧАС** або фіскального чека (DD.MM.YYYY → date YYYY-MM-DD, час HH:MM:SS → time HH:MM). Не плутай з акціями/купонами.

**ВАЖЛИВО ДЛЯ ЛІТРІВ**:
- Об'єм баку автомобіля: 53 літри (МАКСИМУМ!)
- Якщо бачиш число >53л - це помилка, перевір ще раз
- Типові заправки: 40-53 літри
- Ціна за літр зараз: ~60-65 грн/л для дизеля
- Загальна сума зазвичай: 2400-3400 грн
- НІКОЛИ не плутай ціну за літр (60-65 грн) з кількістю літрів!

Якщо це ОДОМЕТР, type="odometer" і data містить:
{
  "odometer": ЗАГАЛЬНИЙ пробіг в км (великі цифри внизу, не trip, не швидкість),
  "confidence": відсоток впевненості (0-100)
}

Якщо не можеш розпізнати - поверни type="unknown"."""


async def recognize_receipt(image_bytes: bytes) -> ReceiptData:
    """
    Recognize receipt data from image using Gemini Vision

    Args:
        image_bytes: Image file bytes

    Returns:
        ReceiptData: Parsed receipt data

    Raises:
        ValueError: If recognition fails or data is invalid
    """
    try:
        # Load image
        image = Image.open(BytesIO(image_bytes))
        logger.info(f"Processing receipt image, size: {image.size}")

        # Generation config for better JSON extraction
        config = GenerateContentConfig(
            temperature=0.1,
            top_p=0.95,
            top_k=40,
        )

        # Generate content
        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=[RECEIPT_RECOGNITION_PROMPT, image],
            config=config
        )

        # Parse response
        text = response.text.strip()
        logger.info(f"Gemini raw response length: {len(text)} chars")
        logger.info(f"Gemini response: {text[:500]}...")  # Show first 500 chars

        # Clean markdown formatting if present
        if text.startswith('```'):
            # Remove markdown code blocks
            lines = text.split('\n')
            text = '\n'.join(lines[1:-1]) if len(lines) > 2 else text
            if text.startswith('json'):
                text = text[4:].strip()

        # Parse JSON
        data = json.loads(text)
        data = normalize_receipt_fields(data)
        logger.info(f"Parsed JSON data: {data}")

        # Validate and create schema
        receipt_data = ReceiptData(**data)

        # Validate critical fields
        missing_fields = []
        if not receipt_data.liters or receipt_data.liters <= 0:
            missing_fields.append("кількість літрів")
        if not receipt_data.total_cost or receipt_data.total_cost <= 0:
            missing_fields.append("загальна сума")
        if not receipt_data.fuel_type or len(receipt_data.fuel_type.strip()) == 0:
            missing_fields.append("тип палива")

        # Calculate price_per_liter if not provided
        if not receipt_data.price_per_liter:
            if receipt_data.liters > 0 and receipt_data.total_cost > 0:
                receipt_data.price_per_liter = receipt_data.total_cost / receipt_data.liters
                logger.info(f"Calculated price_per_liter: {receipt_data.price_per_liter:.2f}")
            else:
                missing_fields.append("ціна за літр")

        if missing_fields:
            error_msg = f"Не вдалося розпізнати критичні поля: {', '.join(missing_fields)}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info(
            f"Receipt recognized successfully: {receipt_data.liters}L, "
            f"{receipt_data.total_cost}₽, confidence: {receipt_data.confidence}%"
        )

        return receipt_data

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON from Gemini response: {e}")
        logger.error(f"Response text: {text if 'text' in locals() else 'N/A'}")
        raise ValueError(f"AI не вернул валидный JSON: {e}")

    except Exception as e:
        logger.error(f"Error recognizing receipt: {e}", exc_info=True)
        raise ValueError(f"Ошибка распознавания чека: {str(e)}")


async def recognize_odometer(image_bytes: bytes) -> OdometerData:
    """
    Recognize odometer reading from image using Gemini Vision

    Args:
        image_bytes: Image file bytes

    Returns:
        OdometerData: Parsed odometer data

    Raises:
        ValueError: If recognition fails or data is invalid
    """
    try:
        # Load image
        image = Image.open(BytesIO(image_bytes))
        logger.info(f"Processing odometer image, size: {image.size}")

        # Generate content
        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=[ODOMETER_RECOGNITION_PROMPT, image],
            config=GenerateContentConfig(temperature=0.1, top_p=0.95, top_k=40),
        )

        # Parse response
        text = response.text.strip()
        logger.debug(f"Gemini response: {text}")

        # Clean markdown formatting if present
        if text.startswith('```'):
            lines = text.split('\n')
            text = '\n'.join(lines[1:-1]) if len(lines) > 2 else text
            if text.startswith('json'):
                text = text[4:].strip()

        # Parse JSON
        data = json.loads(text)

        # Validate and create schema
        odometer_data = OdometerData(**data)

        logger.info(
            f"Odometer recognized successfully: {odometer_data.odometer} km, "
            f"confidence: {odometer_data.confidence}%"
        )

        return odometer_data

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON from Gemini response: {e}")
        logger.error(f"Response text: {text if 'text' in locals() else 'N/A'}")
        raise ValueError(f"AI не вернул валидный JSON: {e}")

    except Exception as e:
        logger.error(f"Error recognizing odometer: {e}", exc_info=True)
        raise ValueError(f"Ошибка распознавания одометра: {str(e)}")


def normalize_gemini_chat_history(history: list) -> list:
    """
    Gemini chat sessions require history to start with a user turn. DB or legacy rows
    may begin with a model message — strip leading turns until the first user.
    If the last turn is an orphan user (incomplete pair), drop it so history ends
    on model before send_message(current question).
    """
    if not history:
        return []

    h = list(history)
    while h and getattr(h[0], "role", None) != "user":
        h.pop(0)

    if h and getattr(h[-1], "role", None) == "user" and len(h) % 2 == 1:
        h.pop()

    return h


async def get_gemini_ai_response(prompt: str, chat_history: list = None, system_instruction: str = None) -> str:
    """
    Legacy: простий чат без інструментів. Для Telegram-асистента використовуй services.ai_fuel_agent.run_fuel_agent.

    Get AI response from Gemini for general questions (chat assistant)

    Args:
        prompt: User's question
        chat_history: List of previous messages [{"role": "user"/"model", "parts": [text]}]
        system_instruction: System instruction that persists across the conversation

    Returns:
        str: AI response text

    Raises:
        ValueError: If AI fails to respond
    """
    try:
        config = GenerateContentConfig(
            temperature=0.7,  # Medium temperature for natural conversation
            top_p=0.95,
            top_k=40,
            system_instruction=system_instruction
        )

        chat_history = normalize_gemini_chat_history(chat_history or [])

        # Chat with history (create() повертає AsyncChat синхронно — без await)
        if chat_history:
            chat = client.aio.chats.create(
                model=settings.gemini_model,
                config=config,
                history=chat_history,
            )
            message = await chat.send_message(prompt)
            text = message.text.strip()
        else:
            # Single message without history
            response = await client.aio.models.generate_content(
                model=settings.gemini_model,
                contents=prompt,
                config=config
            )
            text = response.text.strip()

        logger.info(f"AI chat response length: {len(text)} chars")

        return text

    except Exception as e:
        logger.error(f"Error getting AI chat response: {e}", exc_info=True)
        raise ValueError(f"Помилка отримання відповіді від AI: {str(e)}")


async def recognize_smart(image_bytes: bytes, user_context: str = None) -> dict:
    """
    Smart recognition - detects if image is receipt or odometer in one request

    Args:
        image_bytes: Image data
        user_context: Optional context about user's recent refuels (prices, liters range)

    Returns:
        dict with 'type' ('receipt', 'odometer', or 'unknown') and 'data'
    """
    try:
        image = Image.open(BytesIO(image_bytes))
        logger.info(f"Smart recognition for image, size: {image.size}")

        config = GenerateContentConfig(
            temperature=0.1,
            top_p=0.95,
            top_k=40,
        )

        # Build prompt with optional user context
        prompt = SMART_RECOGNITION_PROMPT
        if user_context:
            prompt = f"{user_context}\n\n{prompt}"
            logger.info(f"Added user context to prompt: {user_context}")

        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=[prompt, image],
            config=config
        )
        text = response.text.strip()

        logger.info(f"Smart recognition raw response length: {len(text)} chars")

        # Extract JSON from markdown code blocks if present
        if '```json' in text:
            start = text.find('```json') + 7
            end = text.find('```', start)
            json_str = text[start:end].strip()
        elif '```' in text:
            start = text.find('```') + 3
            end = text.find('```', start)
            json_str = text[start:end].strip()
        else:
            json_str = text

        data = json.loads(json_str)

        result_type = data.get('type', 'unknown')
        result_data = data.get('data', {})
        if isinstance(result_data, dict) and result_type == 'receipt':
            result_data = normalize_receipt_fields(result_data)

        logger.info(f"Smart recognition result: type={result_type}")

        if result_type == 'receipt':
            return {'type': 'receipt', 'data': ReceiptData(**result_data)}
        elif result_type == 'odometer':
            return {'type': 'odometer', 'data': OdometerData(**result_data)}
        else:
            return {'type': 'unknown', 'data': None}

    except Exception as e:
        logger.error(f"Error in smart recognition: {e}", exc_info=True)
        return {'type': 'unknown', 'data': None}


async def get_user_refuel_context(user_id: int) -> str:
    """
    Get context about user's recent refuels for better OCR accuracy

    Args:
        user_id: User ID

    Returns:
        str: Context string with price and liters ranges from recent refuels
    """
    try:
        from models.database import async_session, Refuel
        from sqlalchemy import select, desc

        async with async_session() as session:
            # Get last 10 refuels
            result = await session.execute(
                select(Refuel)
                .where(Refuel.user_id == user_id)
                .order_by(desc(Refuel.date))
                .limit(10)
            )
            refuels = result.scalars().all()

            if not refuels:
                return None

            # Calculate ranges
            prices = [r.price_per_liter for r in refuels if r.price_per_liter]
            liters = [r.liters for r in refuels if r.liters]

            if not prices or not liters:
                return None

            min_price = min(prices)
            max_price = max(prices)
            avg_price = sum(prices) / len(prices)

            min_liters = min(liters)
            max_liters = max(liters)
            avg_liters = sum(liters) / len(liters)

            context = (
                f"**КОНТЕКСТ З ІСТОРІЇ ЗАПРАВОК** (останні 10 записів):\n"
                f"- Ціна за літр: {min_price:.2f}-{max_price:.2f} грн/л (середня: {avg_price:.2f})\n"
                f"- Кількість літрів: {min_liters:.1f}-{max_liters:.1f}л (середня: {avg_liters:.1f})\n"
                f"- Використовуй ці діапазони для перевірки розпізнаних значень!"
            )

            logger.info(f"Generated user context: price {min_price:.2f}-{max_price:.2f}, liters {min_liters:.1f}-{max_liters:.1f}")
            return context

    except Exception as e:
        logger.error(f"Error getting user context: {e}", exc_info=True)
        return None


async def test_gemini_connection() -> bool:
    """
    Test Gemini API connection

    Returns:
        bool: True if connection is successful
    """
    try:
        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents="Hello"
        )
        logger.info("Gemini API connection test successful")
        return True
    except Exception as e:
        logger.error(f"Gemini API connection test failed: {e}")
        return False
