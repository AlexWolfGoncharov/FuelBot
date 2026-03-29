# 🚀 Швидкий старт FuelBot

## Покрокова інструкція запуску бота

### Крок 1: Встановлення

```bash
# Клонуємо репозиторій
git clone <your-repo-url>
cd FuelBot

# Створюємо віртуальне середовище
python -m venv venv
source venv/bin/activate  # На Linux/Mac
# або
venv\Scripts\activate     # На Windows

# Встановлюємо залежності
pip install -r requirements.txt
```

### Крок 2: Створення Telegram бота

1. Відкрийте [@BotFather](https://t.me/BotFather) у Telegram
2. Відправте `/newbot`
3. Введіть назву бота (наприклад: `My Fuel Tracker`)
4. Введіть username бота (наприклад: `my_fuel_bot`)
5. Скопіюйте отриманий токен (виглядає як `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`)

### Крок 3: Отримання Gemini API ключа

1. Перейдіть на [Google AI Studio](https://ai.google.dev/)
2. Увійдіть через Google акаунт
3. Натисніть "Get API Key" → "Create API Key"
4. Скопіюйте ключ

### Крок 4: Дізнатися свій Telegram ID

1. Відкрийте [@userinfobot](https://t.me/userinfobot)
2. Відправте будь-яке повідомлення
3. Бот покаже ваш ID (наприклад: `123456789`)

### Крок 5: Налаштування `.env`

```bash
# Скопіюємо приклад
cp .env.example .env

# Відкриємо для редагування
nano .env  # або будь-який інший редактор
```

Заповніть файл:

```env
# Вставте ваш токен від BotFather
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz

# Вставте ваш Telegram ID
ALLOWED_USER_IDS=123456789

# Вставте Gemini API ключ
GEMINI_API_KEY=ваш_ключ_тут

# OpenAI опціонально, можна залишити порожнім
OPENAI_API_KEY=

# Google Sheets опціонально
GOOGLE_SHEETS_CREDENTIALS_FILE=credentials.json
GOOGLE_SHEET_ID=

# Ці значення можна не міняти
DATABASE_URL=sqlite+aiosqlite:///./fuel_tracker.db
LOG_LEVEL=INFO
```

### Крок 6: Запуск

```bash
python bot/main.py
```

Ви повинні побачити:

```
2024-01-24 10:00:00 | __main__ | INFO | Starting Fuel Tracker Bot...
2024-01-24 10:00:00 | __main__ | INFO | Database initialized successfully
2024-01-24 10:00:00 | __main__ | INFO | All handlers registered
2024-01-24 10:00:00 | __main__ | INFO | Bot started successfully! Polling for updates...
```

### Крок 7: Перевірка роботи

1. Відкрийте Telegram
2. Знайдіть вашого бота за username
3. Натисніть `START` або відправте `/start`
4. Бот має відповісти привітанням
5. Спробуйте `/add` щоб додати заправку

## ✅ Перша заправка

1. Відправте `/add`
2. Сфотографуйте чек з АЗС (ОККО, WOG, БРСМ тощо)
3. Перевірте розпізнані дані
4. Натисніть "✅ Да, верно"
5. Сфотографуйте одометр
6. Підтвердіть показання
7. Готово! Дані збережено

## 📊 Перегляд статистики

- `/stats` - статистика за місяць
- `/history` - останні 10 заправок

## 🐛 Якщо щось не працює

### Бот не запускається

```bash
# Перевірте що встановлені залежності
pip list | grep aiogram
pip list | grep google-generativeai

# Перевірте Python версію (має бути 3.10+)
python --version

# Перевірте логи
cat bot.log
```

### Помилка "Invalid token"

- Перевірте що BOT_TOKEN в `.env` скопійовано повністю
- Токен не повинен мати пробілів на початку/кінці
- Переконайтеся що ви взяли токен з BotFather

### Помилка "Gemini API key not valid"

- Перевірте що API ключ активний
- Перейдіть на [Google AI Studio](https://ai.google.dev/) і перевірте статус ключа
- Створіть новий ключ якщо потрібно

### Бот не розпізнає чек

- Переконайтеся що фото чітке
- Використовуйте добре освітлення
- Спробуйте кілька разів
- Перевірте ліміти Gemini API (60 запитів/хвилину)

## 💡 Корисні поради

1. **Якість фото** - чим краще фото, тим точніше розпізнавання
2. **Курс валют** - оновлюється автоматично з ПриватБанку
3. **База даних** - всі дані зберігаються в `fuel_tracker.db`
4. **Логи** - всі події записуються в `bot.log`
5. **Зупинка бота** - натисніть `Ctrl+C` в терміналі

## 🎯 Що далі?

- Налаштуйте Google Sheets для зберігання в таблицю (див. README.md)
- Додайте інших користувачів в `ALLOWED_USER_IDS`
- Експериментуйте з різними АЗС
- Дивіться статистику в гривнях та доларах

## 📖 Повна документація

Детальна документація доступна в [README.md](README.md)

---

Успішного використання! ⛽🚗
