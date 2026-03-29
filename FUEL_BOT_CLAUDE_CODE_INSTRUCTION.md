# 🚗 Инструкция для Claude Code
## Разработка Telegram-бота для учета расхода топлива

---

## 📋 Содержание

1. [Обзор проекта](#обзор-проекта)
2. [Структура проекта](#структура-проекта)
3. [Пошаговая разработка](#пошаговая-разработка)
4. [Интеграции](#интеграции)
5. [Тестирование](#тестирование)
6. [Деплой](#деплой)

---

## 🎯 Обзор проекта

**Цель:** Создать Telegram-бота, который:
- Принимает фото чеков с АЗС и распознает данные
- Принимает фото одометра и извлекает пробег
- Сохраняет все в Google Sheets
- Показывает статистику и графики

**Технологии:**
- Python 3.10+
- aiogram 3.x (Telegram Bot Framework)
- Google Gemini Vision API (распознавание изображений)
- OpenAI GPT-4 Vision (fallback для сложных случаев)
- Google Sheets API
- PostgreSQL (или SQLite для начала)
- Pillow (EXIF данные)

---

## 📁 Структура проекта

```
fuel_tracker_bot/
├── .env                      # Переменные окружения (не коммитить!)
├── .gitignore
├── requirements.txt
├── README.md
├── docker-compose.yml        # Для локальной разработки
├── Dockerfile
│
├── config/
│   ├── __init__.py
│   ├── settings.py           # Настройки из .env
│   └── logging_config.py     # Настройка логирования
│
├── bot/
│   ├── __init__.py
│   ├── main.py               # Точка входа
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── start.py          # Команды /start, /help
│   │   ├── refuel.py         # Процесс добавления заправки
│   │   ├── stats.py          # Статистика и отчеты
│   │   └── admin.py          # Админские команды
│   │
│   ├── middlewares/
│   │   ├── __init__.py
│   │   └── auth.py           # Проверка пользователя
│   │
│   ├── keyboards/
│   │   ├── __init__.py
│   │   └── inline.py         # Inline клавиатуры
│   │
│   └── states/
│       ├── __init__.py
│       └── refuel_states.py  # FSM состояния
│
├── services/
│   ├── __init__.py
│   ├── ai_vision/
│   │   ├── __init__.py
│   │   ├── gemini.py         # Gemini Vision
│   │   ├── openai_vision.py  # GPT-4 Vision
│   │   └── prompts.py        # Промпты для AI
│   │
│   ├── image_processing/
│   │   ├── __init__.py
│   │   └── exif_extractor.py # Извлечение EXIF
│   │
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── database.py       # Работа с БД
│   │   └── google_sheets.py  # Google Sheets API
│   │
│   └── analytics/
│       ├── __init__.py
│       ├── calculator.py     # Расчет расхода
│       └── chart_builder.py  # Построение графиков
│
├── models/
│   ├── __init__.py
│   ├── database.py           # SQLAlchemy модели
│   └── schemas.py            # Pydantic схемы
│
├── utils/
│   ├── __init__.py
│   ├── validators.py         # Валидация данных
│   └── helpers.py            # Вспомогательные функции
│
└── tests/
    ├── __init__.py
    ├── test_ai_vision.py
    ├── test_handlers.py
    └── test_data/
        ├── receipt_samples/   # Примеры чеков
        └── odometer_samples/  # Примеры одометров
```

---

## 🚀 Пошаговая разработка

### Шаг 1: Инициализация проекта

**Задача для Claude Code:**
```
Создай базовую структуру проекта для Telegram-бота учета топлива.

Требования:
1. Создай все директории из структуры выше
2. Инициализируй Python проект с pyproject.toml
3. Создай .gitignore для Python проекта
4. Создай requirements.txt с базовыми зависимостями:
   - aiogram==3.3.0
   - python-dotenv==1.0.0
   - google-generativeai==0.3.2
   - openai==1.7.0
   - gspread==5.12.0
   - oauth2client==4.1.3
   - pillow==10.1.0
   - sqlalchemy==2.0.23
   - aiosqlite==0.19.0
   - pydantic==2.5.0
   - pydantic-settings==2.1.0
   - matplotlib==3.8.2
   - pandas==2.1.4
```

### Шаг 2: Конфигурация (.env и settings.py)

**Задача для Claude Code:**
```
Создай файл config/settings.py с использованием pydantic-settings для загрузки переменных окружения.

Переменные окружения (.env):
- BOT_TOKEN: Telegram Bot Token
- GEMINI_API_KEY: Google Gemini API ключ
- OPENAI_API_KEY: OpenAI API ключ (опционально)
- GOOGLE_SHEETS_CREDENTIALS_FILE: путь к JSON с credentials
- GOOGLE_SHEET_ID: ID Google таблицы
- DATABASE_URL: SQLite или PostgreSQL URL
- ALLOWED_USER_IDS: список разрешенных Telegram ID через запятую
- LOG_LEVEL: уровень логирования (DEBUG/INFO/WARNING/ERROR)

Также создай пример .env.example файла.
```

**Ожидаемый результат:**
```python
# config/settings.py
from pydantic_settings import BaseSettings
from typing import List, Optional

class Settings(BaseSettings):
    # Telegram
    bot_token: str
    allowed_user_ids: List[int] = []
    
    # AI Services
    gemini_api_key: str
    openai_api_key: Optional[str] = None
    
    # Google Sheets
    google_sheets_credentials_file: str
    google_sheet_id: str
    
    # Database
    database_url: str = "sqlite+aiosqlite:///./fuel_tracker.db"
    
    # Logging
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
```

### Шаг 3: Модели данных (Database)

**Задача для Claude Code:**
```
Создай SQLAlchemy модели в models/database.py:

1. User - пользователи бота
   - id (PK)
   - telegram_id (unique)
   - username
   - first_name
   - created_at

2. Refuel - заправки
   - id (PK)
   - user_id (FK)
   - date (дата заправки)
   - station_name (название АЗС)
   - fuel_type (тип топлива)
   - liters (литры, Decimal)
   - price_per_liter (цена за литр, Decimal)
   - total_cost (общая сумма, Decimal)
   - odometer (показания одометра, Integer)
   - latitude (Decimal, nullable)
   - longitude (Decimal, nullable)
   - distance_from_last (пробег с прошлой заправки, Integer, nullable)
   - consumption (расход л/100км, Decimal, nullable)
   - receipt_file_id (Telegram file_id)
   - odometer_file_id (Telegram file_id)
   - ai_confidence (уверенность AI, Integer)
   - created_at
   - updated_at

Используй async SQLAlchemy с aiosqlite.
```

### Шаг 4: AI Vision сервисы

**Задача для Claude Code:**
```
Создай сервисы для распознавания изображений:

1. services/ai_vision/prompts.py - промпты для AI моделей
2. services/ai_vision/gemini.py - интеграция с Gemini Vision
3. services/ai_vision/openai_vision.py - интеграция с GPT-4 Vision (опционально)

Требования к промпту для распознавания чека:
- Извлекать: литры, цена/л, общая сумма, название АЗС, тип топлива, дата, время
- Возвращать JSON
- Валидировать что литры × цена ≈ сумма
- Указывать confidence (0-100)

Требования к промпту для одометра:
- Извлекать показания пробега
- Возвращать JSON
- Указывать confidence

Функции должны быть async и возвращать Pydantic модели (создай в models/schemas.py).
```

**Пример ожидаемого кода:**

```python
# services/ai_vision/gemini.py
import google.generativeai as genai
from config.settings import settings
from models.schemas import ReceiptData
import json

genai.configure(api_key=settings.gemini_api_key)

async def recognize_receipt(image_bytes: bytes) -> ReceiptData:
    """
    Распознает данные с чека АЗС используя Gemini Vision
    """
    model = genai.GenerativeModel('gemini-pro-vision')
    
    # Загрузка изображения
    import PIL.Image
    import io
    image = PIL.Image.open(io.BytesIO(image_bytes))
    
    prompt = """
    Проанализируй чек с АЗС и извлеки данные в JSON формате:
    {
        "liters": float,
        "price_per_liter": float,
        "total_cost": float,
        "station": str,
        "fuel_type": str,
        "date": "YYYY-MM-DD",
        "time": "HH:MM",
        "confidence": int (0-100)
    }
    
    Только JSON без дополнительного текста.
    """
    
    response = await model.generate_content_async([prompt, image])
    
    # Парсинг JSON
    text = response.text.strip()
    # Удаление markdown если есть
    if text.startswith('```'):
        text = text.split('```')[1]
        if text.startswith('json'):
            text = text[4:]
    
    data = json.loads(text)
    
    return ReceiptData(**data)
```

### Шаг 5: EXIF экстрактор

**Задача для Claude Code:**
```
Создай services/image_processing/exif_extractor.py

Функция extract_exif_data(image_bytes: bytes) должна:
1. Извлекать GPS координаты (если есть)
2. Извлекать дату/время съемки
3. Конвертировать GPS в decimal degrees
4. Возвращать Pydantic модель ExifData

Используй библиотеку Pillow.
```

### Шаг 6: Google Sheets интеграция

**Задача для Claude Code:**
```
Создай services/storage/google_sheets.py

Класс GoogleSheetsService должен:
1. Подключаться к Google Sheets через Service Account
2. Метод add_refuel(refuel_data) - добавить строку в таблицу
3. Метод get_user_stats(user_id, period) - получить статистику
4. Форматировать данные в удобочитаемый вид

Структура листа "Заправки":
Колонки: Дата | АЗС | Топливо | Литры | Цена/л | Сумма | Пробег | Пробег с пред. | Расход л/100км | Координаты
```

### Шаг 7: Telegram Bot хендлеры

**Задача для Claude Code:**
```
Создай базовые хендлеры:

1. bot/handlers/start.py
   - /start - приветствие и инструкция
   - /help - справка по командам
   
2. bot/handlers/refuel.py
   - /add - начать процесс добавления заправки
   - FSM машина состояний:
     * WaitingForReceipt - ожидание фото чека
     * ConfirmReceipt - подтверждение данных чека
     * WaitingForOdometer - ожидание фото одометра
     * ConfirmOdometer - подтверждение одометра
     * Saving - сохранение в БД и Google Sheets
   
3. bot/handlers/stats.py
   - /stats - статистика за текущий месяц
   - /history - последние 10 заправок
   - /report - отчет за произвольный период

Используй FSM (Finite State Machine) из aiogram.
Добавь inline клавиатуры для подтверждения/редактирования.
```

**Пример структуры хендлера:**

```python
# bot/handlers/refuel.py
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from services.ai_vision.gemini import recognize_receipt
from bot.keyboards.inline import get_confirm_keyboard
import logging

router = Router()
logger = logging.getLogger(__name__)

class RefuelStates(StatesGroup):
    waiting_for_receipt = State()
    confirm_receipt = State()
    waiting_for_odometer = State()
    confirm_odometer = State()

@router.message(Command("add"))
async def cmd_add_refuel(message: Message, state: FSMContext):
    """Начало процесса добавления заправки"""
    await message.answer(
        "🔵 Отправьте фото чека с АЗС\n\n"
        "💡 Советы для лучшего распознавания:\n"
        "• Хорошее освещение\n"
        "• Чек развернут ровно\n"
        "• Текст читаем"
    )
    await state.set_state(RefuelStates.waiting_for_receipt)

@router.message(RefuelStates.waiting_for_receipt, F.photo)
async def process_receipt(message: Message, state: FSMContext):
    """Обработка фото чека"""
    
    # Показываем что бот работает
    await message.answer("⏳ Анализирую чек...")
    
    # Получаем фото в максимальном качестве
    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    image_bytes = await message.bot.download_file(file.file_path)
    
    try:
        # Распознаем чек
        receipt_data = await recognize_receipt(image_bytes.read())
        
        # Сохраняем в состояние
        await state.update_data(
            receipt=receipt_data.model_dump(),
            receipt_file_id=photo.file_id
        )
        
        # Формируем сообщение с данными
        text = (
            f"✅ Чек распознан (уверенность: {receipt_data.confidence}%)\n\n"
            f"📍 АЗС: {receipt_data.station}\n"
            f"⛽ Топливо: {receipt_data.fuel_type}\n"
            f"📊 Литры: {receipt_data.liters} л\n"
            f"💰 Цена: {receipt_data.price_per_liter} ₽/л\n"
            f"💵 Сумма: {receipt_data.total_cost} ₽\n"
            f"📅 Дата: {receipt_data.date} {receipt_data.time}\n\n"
            f"Все верно?"
        )
        
        await message.answer(
            text,
            reply_markup=get_confirm_keyboard()
        )
        await state.set_state(RefuelStates.confirm_receipt)
        
    except Exception as e:
        logger.error(f"Error recognizing receipt: {e}")
        await message.answer(
            "❌ Не удалось распознать чек. Попробуйте другое фото или /cancel"
        )

@router.callback_query(RefuelStates.confirm_receipt, F.data == "confirm")
async def receipt_confirmed(callback: CallbackQuery, state: FSMContext):
    """Подтверждение данных чека"""
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "📸 Теперь отправьте фото спидометра/одометра\n\n"
        "💡 Показания пробега должны быть четко видны"
    )
    await state.set_state(RefuelStates.waiting_for_odometer)
    await callback.answer()

# ... остальные хендлеры
```

### Шаг 8: Main файл

**Задача для Claude Code:**
```
Создай bot/main.py - точку входа приложения:

1. Инициализация бота и диспетчера
2. Подключение всех роутеров (handlers)
3. Инициализация БД (создание таблиц)
4. Настройка middlewares
5. Запуск polling

Добавь graceful shutdown (корректная остановка бота).
```

**Пример:**

```python
# bot/main.py
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config.settings import settings
from models.database import init_db
from bot.handlers import start, refuel, stats

# Настройка логирования
logging.basicConfig(
    level=settings.log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    """Главная функция запуска бота"""
    
    # Инициализация БД
    await init_db()
    logger.info("Database initialized")
    
    # Создаем бота и диспетчер
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=MemoryStorage())
    
    # Подключаем роутеры
    dp.include_router(start.router)
    dp.include_router(refuel.router)
    dp.include_router(stats.router)
    
    logger.info("Bot started")
    
    try:
        # Запускаем polling
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
```

### Шаг 9: Аналитика и графики

**Задача для Claude Code:**
```
Создай services/analytics/:

1. calculator.py - расчеты:
   - calculate_consumption(liters, distance) -> л/100км
   - calculate_cost_per_km(total_cost, distance) -> ₽/км
   - calculate_avg_price(refuels) -> средняя цена
   
2. chart_builder.py - построение графиков:
   - build_consumption_chart(refuels) -> график расхода
   - build_price_chart(refuels) -> график цен
   - build_cost_chart(refuels) -> график затрат
   
Используй matplotlib для графиков.
Графики должны возвращаться как BytesIO объекты для отправки в Telegram.
```

### Шаг 10: Docker конфигурация

**Задача для Claude Code:**
```
Создай:

1. Dockerfile - многоступенчатая сборка
   - Stage 1: builder - установка зависимостей
   - Stage 2: runtime - минимальный образ
   
2. docker-compose.yml - для локальной разработки
   - Сервис: bot
   - Сервис: postgres (опционально)
   - Volume для БД
   - Env файл
```

**Пример Dockerfile:**

```dockerfile
# Dockerfile
FROM python:3.11-slim as builder

WORKDIR /app

# Установка зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Runtime stage
FROM python:3.11-slim

WORKDIR /app

# Копируем зависимости из builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Копируем код приложения
COPY . .

# Создаем пользователя для безопасности
RUN useradd -m -u 1000 botuser && chown -R botuser:botuser /app
USER botuser

CMD ["python", "bot/main.py"]
```

---

## 🔌 Интеграции

### Google Sheets API Setup

**Задача для Claude Code:**
```
Создай инструкцию GOOGLE_SHEETS_SETUP.md с шагами:

1. Как создать проект в Google Cloud Console
2. Как включить Google Sheets API
3. Как создать Service Account
4. Как скачать JSON credentials
5. Как дать доступ Service Account к таблице
6. Формат таблицы с примером
```

### Gemini API Setup

**Задача для Claude Code:**
```
Создай инструкцию GEMINI_API_SETUP.md:

1. Регистрация на Google AI Studio
2. Получение API ключа
3. Лимиты бесплатного тарифа
4. Примеры тестирования API
```

---

## 🧪 Тестирование

**Задача для Claude Code:**
```
Создай тесты в tests/:

1. test_ai_vision.py - тесты распознавания
   - Используй реальные примеры чеков
   - Проверь точность распознавания
   - Тест обработки плохих изображений
   
2. test_handlers.py - тесты хендлеров
   - Mock объекты для Telegram
   - Тест FSM переходов
   - Тест валидации данных
   
3. test_analytics.py - тесты расчетов
   - Проверка формул расхода
   - Граничные случаи

Используй pytest и pytest-asyncio.
```

**Пример теста:**

```python
# tests/test_ai_vision.py
import pytest
from pathlib import Path
from services.ai_vision.gemini import recognize_receipt

@pytest.mark.asyncio
async def test_receipt_recognition():
    """Тест распознавания чека"""
    
    # Загружаем тестовое изображение
    test_image = Path("tests/test_data/receipt_samples/lukoil_ai95.jpg")
    with open(test_image, 'rb') as f:
        image_bytes = f.read()
    
    # Распознаем
    result = await recognize_receipt(image_bytes)
    
    # Проверяем результаты
    assert result.liters > 0
    assert result.price_per_liter > 0
    assert result.total_cost > 0
    assert result.station is not None
    assert result.fuel_type is not None
    assert result.confidence >= 70  # Минимальная уверенность
    
    # Проверяем математику
    calculated = result.liters * result.price_per_liter
    assert abs(calculated - result.total_cost) < 5  # Допуск 5 рублей
```

---

## 📝 Чек-лист разработки

### Phase 1: MVP (Базовый функционал)
- [ ] Инициализация проекта и структура
- [ ] Конфигурация и переменные окружения
- [ ] Модели данных (SQLAlchemy)
- [ ] Gemini Vision интеграция
- [ ] EXIF экстрактор
- [ ] Базовые хендлеры (/start, /add)
- [ ] FSM для процесса заправки
- [ ] Google Sheets интеграция
- [ ] Расчет базовой статистики
- [ ] Локальное тестирование

### Phase 2: Улучшения
- [ ] OpenAI Vision fallback
- [ ] Улучшенная валидация данных
- [ ] Inline клавиатуры и UX
- [ ] Команда /stats с графиками
- [ ] История заправок
- [ ] Редактирование последней записи
- [ ] Middleware для авторизации
- [ ] Обработка ошибок

### Phase 3: Аналитика
- [ ] Продвинутые графики (matplotlib)
- [ ] Отчеты за период
- [ ] Экспорт в Excel
- [ ] Dashboard (опционально)
- [ ] BigQuery интеграция (опционально)

### Phase 4: Production Ready
- [ ] Dockerfile и docker-compose
- [ ] CI/CD pipeline
- [ ] Мониторинг и логирование
- [ ] Документация API
- [ ] Unit тесты (>70% coverage)
- [ ] Деплой на сервер

---

## 🎯 Готовые промпты для Claude Code

### Промпт 1: Создание базовой структуры
```
Создай полную структуру проекта Telegram-бота для учета топлива согласно 
структуре из файла FUEL_BOT_CLAUDE_CODE_INSTRUCTION.md раздел "Структура проекта".

Создай все папки и базовые __init__.py файлы.
Создай requirements.txt со всеми зависимостями.
Создай .gitignore для Python.
Создай .env.example с примерами всех нужных переменных.
```

### Промпт 2: Конфигурация
```
Реализуй config/settings.py используя pydantic-settings.
Все настройки должны загружаться из .env файла.
Добавь валидацию для обязательных полей.
Создай логирование в config/logging_config.py.
```

### Промпт 3: Модели БД
```
Создай SQLAlchemy async модели в models/database.py:
- User (пользователи)
- Refuel (заправки)

Создай Pydantic схемы в models/schemas.py:
- ReceiptData (данные с чека)
- OdometerData (данные одометра)
- ExifData (EXIF данные)
- RefuelCreate (для создания записи)

Добавь функцию init_db() для создания таблиц.
```

### Промпт 4: Gemini Vision
```
Реализуй services/ai_vision/gemini.py:

Функция recognize_receipt(image_bytes) должна:
1. Отправить изображение в Gemini Vision
2. Получить JSON с данными чека
3. Вернуть ReceiptData модель

Функция recognize_odometer(image_bytes) должна:
1. Распознать показания одометра
2. Вернуть OdometerData модель

Добавь обработку ошибок и retry логику.
```

### Промпт 5: Основной хендлер
```
Реализуй bot/handlers/refuel.py с полным циклом добавления заправки:

1. Команда /add - начало
2. FSM состояния для пошагового процесса
3. Обработка фото чека с AI распознаванием
4. Подтверждение данных чека (inline кнопки)
5. Обработка фото одометра
6. Подтверждение одометра
7. Сохранение в БД и Google Sheets
8. Расчет расхода топлива
9. Отправка итогового сообщения

Добавь обработку ошибок и возможность отмены (/cancel).
```

### Промпт 6: Google Sheets
```
Реализуй services/storage/google_sheets.py:

Класс GoogleSheetsService с методами:
- add_refuel(refuel_data) - добавить заправку
- get_recent_refuels(user_id, limit) - последние N заправок
- get_stats(user_id, start_date, end_date) - статистика за период

Используй gspread для работы с API.
Добавь форматирование ячеек (цвета, границы).
```

### Промпт 7: Статистика и графики
```
Реализуй services/analytics/calculator.py с функциями расчетов.

Реализуй services/analytics/chart_builder.py с функциями для matplotlib графиков:
- График расхода топлива по времени
- График цен на топливо
- График затрат по месяцам

Графики должны возвращаться как BytesIO для отправки в Telegram.
```

### Промпт 8: Main и запуск
```
Реализуй bot/main.py - точку входа:
1. Инициализация БД
2. Создание бота и диспетчера
3. Подключение всех роутеров
4. Настройка middleware
5. Graceful shutdown
6. Запуск polling

Добавь логирование всех важных событий.
```

---

## 🐛 Отладка и логирование

**Настройка логирования:**

```python
# config/logging_config.py
import logging
import sys

def setup_logging(log_level: str = "INFO"):
    """Настройка логирования для всего приложения"""
    
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('bot.log', encoding='utf-8')
        ]
    )
    
    # Отключаем лишние логи от библиотек
    logging.getLogger('aiogram').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
```

---

## 📚 Полезные ссылки

- [aiogram 3.x документация](https://docs.aiogram.dev/)
- [Google Gemini API](https://ai.google.dev/tutorials/python_quickstart)
- [OpenAI Vision API](https://platform.openai.com/docs/guides/vision)
- [Google Sheets API Python](https://developers.google.com/sheets/api/quickstart/python)
- [SQLAlchemy Async](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)

---

## ✅ Критерии готовности MVP

Бот считается готовым к использованию если:

1. ✅ Успешно распознает чеки с точностью >85%
2. ✅ Успешно распознает одометр с точностью >90%
3. ✅ Сохраняет данные в Google Sheets
4. ✅ Показывает базовую статистику
5. ✅ Работает без ошибок при нормальном использовании
6. ✅ Логирует все важные события
7. ✅ Покрыт тестами на >50%

---

## 🎓 Советы по разработке с Claude Code

1. **Итеративная разработка**: Начни с простого, постепенно добавляй функционал
2. **Тестируй каждый модуль**: Не жди пока все будет готово
3. **Используй примеры данных**: Собери 10-15 реальных чеков для тестирования
4. **Логируй все**: Особенно AI ответы - поможет в отладке
5. **Обрабатывай ошибки**: AI может вернуть невалидный JSON
6. **Оптимизируй промпты**: Экспериментируй с формулировками
7. **Версионируй промпты**: Сохраняй успешные варианты

---

## 🚀 Быстрый старт (после создания)

```bash
# 1. Клонировать проект
git clone <your-repo>
cd fuel_tracker_bot

# 2. Создать виртуальное окружение
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows

# 3. Установить зависимости
pip install -r requirements.txt

# 4. Настроить .env
cp .env.example .env
# Заполнить все ключи в .env

# 5. Инициализировать БД
python -c "from models.database import init_db; import asyncio; asyncio.run(init_db())"

# 6. Запустить бота
python bot/main.py
```

---

**Готово! Начинай разработку с Claude Code 🚀**

**Первая команда:** "Создай базовую структуру проекта согласно инструкции"
