# 🚗 FuelBot - Telegram Bot для обліку витрат на паливо

Telegram-бот для автоматичного обліку заправок з використанням AI розпізнавання чеків та одометра.

## ✨ Можливості

- 📸 **Розпізнавання чеків** - автоматичне витягування даних з фото чека АЗС
- 🔢 **Зчитування одометра** - розпізнавання показань пробігу з фото
- ⛽ **Розрахунок витрати** - автоматичний підрахунок витрати палива л/100км
- 💵 **Конвертація в USD** - збереження цін у доларах для довгострокового аналізу
- 📊 **Статистика** - детальна статистика по заправках та витратах
- 📈 **Google Sheets** - збереження даних у Google таблицю
- 🤖 **AI-powered** - використовує Google Gemini Vision для розпізнавання

## 🇺🇦 Підтримка українських АЗС

Бот розпізнає чеки з популярних українських АЗС:
- ОККО
- WOG
- БРСМ-Нафта
- Socar
- Shell
- ANP
- Parallel
- КЛО
- UPG

## 📋 Вимоги

- Python 3.10+
- Telegram Bot Token (отримати у [@BotFather](https://t.me/BotFather))
- Google Gemini API Key (отримати на [Google AI Studio](https://ai.google.dev/))
- Google Sheets API credentials (опціонально)

## 🚀 Швидкий старт

### 🐳 Запуск в Docker (Рекомендовано!)

**Найпростіший спосіб - всього 3 кроки:**

```bash
# 1. Налаштувати .env файл
cp .env.example .env
nano .env  # вставте ваші API ключі

# 2. Запустити
./start.sh

# 3. Готово! Бот працює 🎉
```

📖 **Детальна інструкція:** [DOCKER_QUICKSTART.md](DOCKER_QUICKSTART.md)

---

### 📦 Локальний запуск (без Docker)

### 1. Клонування репозиторію

```bash
git clone <your-repo-url>
cd FuelBot
```

### 2. Створення віртуального середовища

```bash
python -m venv venv

# Linux/Mac
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 3. Встановлення залежностей

```bash
pip install -r requirements.txt
```

### 4. Налаштування змінних оточення

Скопіюйте `.env.example` у `.env` та заповніть необхідні дані:

```bash
cp .env.example .env
```

Відредагуйте `.env`:

```env
# Telegram Bot Token (отримати у @BotFather)
BOT_TOKEN=your_telegram_bot_token_here

# Дозволені користувачі (Telegram ID через кому)
ALLOWED_USER_IDS=123456789,987654321

# Google Gemini API Key
GEMINI_API_KEY=your_gemini_api_key_here

# OpenAI API Key (опціонально, для fallback)
OPENAI_API_KEY=your_openai_api_key_here

# Google Sheets (опціонально)
GOOGLE_SHEETS_CREDENTIALS_FILE=credentials.json
GOOGLE_SHEET_ID=your_google_sheet_id_here

# База даних
DATABASE_URL=sqlite+aiosqlite:///./fuel_tracker.db

# Логування
LOG_LEVEL=INFO
```

### 5. Отримання API ключів

#### Telegram Bot Token

1. Відкрийте [@BotFather](https://t.me/BotFather) у Telegram
2. Відправте команду `/newbot`
3. Слідуйте інструкціям для створення бота
4. Скопіюйте отриманий токен у `.env`

#### Google Gemini API Key

1. Перейдіть на [Google AI Studio](https://ai.google.dev/)
2. Увійдіть з Google акаунтом
3. Натисніть "Get API Key"
4. Створіть новий API ключ
5. Скопіюйте ключ у `.env`

**Важливо:** Gemini має безкоштовний тариф з лімітами:
- 60 запитів на хвилину
- 1500 запитів на день
- Цього достатньо для особистого використання

#### Дізнатися свій Telegram ID

1. Відкрийте [@userinfobot](https://t.me/userinfobot)
2. Відправте будь-яке повідомлення
3. Скопіюйте ваш ID у `ALLOWED_USER_IDS`

### 6. Запуск бота

```bash
python bot/main.py
```

Якщо все налаштовано правильно, ви побачите:

```
2024-01-15 10:00:00 | __main__ | INFO | Starting Fuel Tracker Bot...
2024-01-15 10:00:00 | __main__ | INFO | Database initialized successfully
2024-01-15 10:00:00 | __main__ | INFO | All handlers registered
2024-01-15 10:00:00 | __main__ | INFO | Bot started successfully! Polling for updates...
```

## 📱 Використання бота

### Команди

- `/start` - Привітання та опис бота
- `/help` - Довідка по використанню
- `/add` - Додати нову заправку
- `/stats` - Статистика за поточний місяць
- `/history` - Історія останніх 10 заправок
- `/cancel` - Скасувати поточну дію

### Процес додавання заправки

1. Відправте команду `/add`
2. Сфотографуйте чек з АЗС
3. Бот розпізнає дані та покаже їх вам
4. Підтвердьте дані або повторіть фото
5. Сфотографуйте одометр (показання пробігу)
6. Підтвердьте показання
7. Готово! Дані збережено ✅

Бот автоматично:
- Конвертує ціну в долари за курсом ПриватБанку
- Розраховує витрату палива л/100км
- Зберігає дані в базу та Google Sheets

### Поради для кращого розпізнавання

📸 **Чек:**
- Добре освітлення
- Чек розгорнутий рівно
- Текст чітко читається
- Уникайте відблисків та тіней

🔢 **Одометр:**
- Цифри повинні бути чітко видні
- Знімайте загальний пробіг, не добовий (trip)
- Тримайте камеру рівно

## 💵 Конвертація в USD

Бот автоматично отримує актуальний курс USD/UAH з API ПриватБанку та зберігає ціни у доларах. Це дозволяє:

- Відстежувати реальні витрати на паливо з урахуванням інфляції
- Порівнювати витрати за різні періоди
- Аналізувати динаміку цін у стабільній валюті

Курс кешується на 1 годину для економії запитів до API.

## 📊 Структура проекту

```
FuelBot/
├── bot/
│   ├── handlers/          # Обробники команд
│   │   ├── start.py       # /start, /help, /cancel
│   │   ├── refuel.py      # /add - додавання заправки
│   │   └── stats.py       # /stats, /history
│   ├── keyboards/         # Inline клавіатури
│   ├── states/            # FSM стани
│   └── main.py            # Точка входу
│
├── config/
│   ├── settings.py        # Налаштування з .env
│   └── logging_config.py  # Конфігурація логування
│
├── models/
│   ├── database.py        # SQLAlchemy моделі
│   └── schemas.py         # Pydantic схеми
│
├── services/
│   ├── ai_vision/         # AI розпізнавання
│   │   ├── gemini.py      # Gemini Vision API
│   │   └── prompts.py     # Промпти для AI
│   │
│   ├── currency/          # Курси валют
│   │   └── exchange_rate.py  # ПриватБанк API
│   │
│   └── storage/
│       └── google_sheets.py  # Google Sheets API
│
├── .env                   # Змінні оточення (створити з .env.example)
├── requirements.txt       # Залежності Python
└── README.md             # Документація
```

## 🔧 Налаштування Google Sheets (опціонально)

Якщо ви хочете зберігати дані в Google Sheets:

### 1. Створення Service Account

1. Перейдіть у [Google Cloud Console](https://console.cloud.google.com/)
2. Створіть новий проект або виберіть існуючий
3. Увімкніть Google Sheets API:
   - APIs & Services → Library
   - Знайдіть "Google Sheets API"
   - Натисніть Enable

4. Створіть Service Account:
   - APIs & Services → Credentials
   - Create Credentials → Service Account
   - Заповніть назву та натисніть Create
   - Натисніть Continue, потім Done

5. Створіть ключ:
   - Натисніть на створений Service Account
   - Keys → Add Key → Create New Key
   - Виберіть JSON
   - Збережіть файл як `credentials.json` у корінь проекту

### 2. Налаштування Google Sheets

1. Створіть нову Google таблицю
2. Скопіюйте ID таблиці з URL:
   ```
   https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit
   ```
3. Відкрийте `credentials.json` та знайдіть `client_email`
4. Відкрийте доступ до таблиці для цього email (кнопка "Поділитися")
5. Додайте ID таблиці у `.env`:
   ```
   GOOGLE_SHEET_ID=YOUR_SHEET_ID
   ```

## 🐳 Docker команди

### Основні команди

```bash
# Запустити бота
docker-compose up -d

# Переглянути логи
docker-compose logs -f

# Перезапустити
docker-compose restart

# Зупинити
docker-compose stop

# Видалити контейнер
docker-compose down

# Оновити код та перезібрати
git pull && docker-compose up -d --build
```

### Моніторинг

```bash
# Статус контейнера
docker-compose ps

# Використання ресурсів
docker stats fuelbot

# Помилки в логах
docker-compose logs | grep -i error
```

## 🐛 Вирішення проблем

### Docker

```bash
# Бот не запускається в Docker
docker-compose logs        # подивіться логи
docker-compose down        # повністю зупиніть
docker-compose up -d --build  # перезберіть

# Оновити .env без перезбірки
docker-compose restart
```

### Локальний запуск

1. Перевірте що всі залежності встановлені:
   ```bash
   pip install -r requirements.txt
   ```

2. Перевірте `.env` файл:
   - BOT_TOKEN повинен бути валідним
   - GEMINI_API_KEY повинен бути активним

3. Перевірте логи в `bot.log`

### Помилки розпізнавання

1. Переконайтеся що фото чітке та добре освітлене
2. Спробуйте сфотографувати ще раз
3. Перевірте ліміти Gemini API
4. Перевірте логи для деталей помилки

### База даних

База даних SQLite створюється автоматично при першому запуску у файлі `fuel_tracker.db`.

Для перегляду даних можна використовувати:
```bash
sqlite3 fuel_tracker.db
.tables
SELECT * FROM refuels;
```

## 📈 Що далі?

### Phase 2: Покращення
- [ ] OpenAI Vision fallback
- [ ] Редагування розпізнаних даних
- [ ] Експорт статистики в PDF/Excel
- [ ] Графіки витрати (matplotlib)
- [ ] Повідомлення про заправки

### Phase 3: Аналітика
- [ ] Порівняння цін по АЗС
- [ ] Прогнозування витрат
- [ ] Рекомендації по заправках
- [ ] Інтеграція з картами

## 🤝 Внесок у проект

Якщо ви знайшли баг або хочете запропонувати покращення:

1. Створіть Issue з описом проблеми
2. Або зробіть Pull Request з вашими змінами

## 📝 Ліцензія

MIT License - використовуйте вільно!

## 💬 Підтримка

По питанням та пропозиціям:
- Telegram: @your_username
- Email: your@email.com

---

Зроблено з ❤️ для українських автомобілістів
