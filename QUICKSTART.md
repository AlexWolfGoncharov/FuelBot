# 🚀 Швидкий старт FuelBot

## Крок 1: Встановлення

```bash
# Клонування
git clone <your-repo-url>
cd FuelBot

# Віртуальне середовище
python -m venv venv
source venv/bin/activate  # Linux/Mac
# або venv\Scripts\activate для Windows

# Залежності
pip install -r requirements.txt
```

## Крок 2: Налаштування

1. **Створіть `.env` файл:**
```bash
cp .env.example .env
```

2. **Заповніть обов'язкові поля:**

```env
# 1. Telegram Bot Token (отримати у @BotFather)
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz

# 2. Ваш Telegram ID (дізнатися у @userinfobot)
ALLOWED_USER_IDS=123456789

# 3. Gemini API Key (безкоштовно на https://ai.google.dev/)
GEMINI_API_KEY=your_gemini_api_key_here
```

**Опціонально (можна не заповнювати зараз):**
- `OPENAI_API_KEY` - fallback для розпізнавання
- `GOOGLE_SHEETS_*` - для експорту в Google Sheets

## Крок 3: Запуск

```bash
python bot/main.py
```

Ви побачите:
```
INFO | Bot started successfully! Polling for updates...
```

## Крок 4: Використання

1. Відкрийте свого бота в Telegram
2. Відправте `/start`
3. Відправте `/add` та слідуйте інструкціям
4. Сфотографуйте чек з АЗС
5. Сфотографуйте одометр
6. Готово! ✅

## 📊 Команди

- `/add` - додати заправку
- `/stats` - статистика за місяць
- `/history` - останні 10 заправок

## ⚠️ Типові проблеми

**Бот не відповідає?**
- Перевірте `BOT_TOKEN` у `.env`
- Перевірте що ваш ID у `ALLOWED_USER_IDS`

**Помилка розпізнавання?**
- Перевірте `GEMINI_API_KEY`
- Перевірте ліміти API (60 запитів/хв)
- Зробіть чітке фото при хорошому освітленні

**Помилка імпорту?**
```bash
pip install -r requirements.txt --upgrade
```

## 📝 Детальна документація

Див. [README.md](README.md) для детальної інформації.
