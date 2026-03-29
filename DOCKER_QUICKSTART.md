# 🐳 FuelBot - Швидкий запуск в Docker

Найпростіший спосіб запустити FuelBot за 3 хвилини!

## 📋 Що потрібно

1. **Docker** та **Docker Compose** встановлені на вашому комп'ютері
   - [Встановити Docker](https://docs.docker.com/get-docker/)
   - [Встановити Docker Compose](https://docs.docker.com/compose/install/)

2. **API ключі:**
   - Telegram Bot Token (від [@BotFather](https://t.me/BotFather))
   - Google Gemini API Key (з [Google AI Studio](https://ai.google.dev/))
   - Ваш Telegram ID (від [@userinfobot](https://t.me/userinfobot))

## 🚀 Швидкий старт (3 кроки)

### 1. Налаштуйте .env файл

```bash
# Скопіюйте приклад
cp .env.example .env

# Відредагуйте .env та вставте ваші ключі
nano .env
# або
vim .env
```

**Мінімальна конфігурація в .env:**
```env
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
GEMINI_API_KEY=AIzaSyD...your_key_here
ALLOWED_USER_IDS=123456789
```

### 2. Запустіть скрипт

```bash
./start.sh
```

Або вручну:

```bash
# Створити директорії для даних
mkdir -p data logs

# Зібрати та запустити
docker-compose up -d
```

### 3. Готово! 🎉

Відкрийте Telegram та напишіть вашому боту `/start`

## 📊 Перевірка роботи

```bash
# Подивитися логи
docker-compose logs -f

# Перевірити статус
docker-compose ps
```

Ви повинні побачити:
```
NAME      COMMAND              SERVICE   STATUS    PORTS
fuelbot   "python bot/main.py" fuelbot   running
```

## 🛠 Корисні команди

```bash
# Переглянути логи в реальному часі
docker-compose logs -f

# Перезапустити бота
docker-compose restart

# Зупинити бота
docker-compose stop

# Запустити знову
docker-compose start

# Повністю зупинити і видалити контейнер
docker-compose down

# Оновити код і перезібрати
git pull
docker-compose up -d --build
```

## 📁 Структура файлів

Після запуску у вас буде:

```
FuelBot/
├── .env                    # Ваші API ключі (НЕ КОММІТИТИ!)
├── docker-compose.yml      # Конфігурація Docker
├── data/                   # База даних (persistent)
│   └── fuel_tracker.db
├── logs/                   # Логи бота (optional)
│   └── bot.log
└── credentials.json        # Google Sheets (якщо використовуєте)
```

## 🔧 Налаштування Google Sheets (опціонально)

Якщо хочете зберігати дані в Google Sheets:

1. Створіть `credentials.json` (див. основний README.md)
2. Додайте в `.env`:
   ```env
   GOOGLE_SHEETS_CREDENTIALS_FILE=credentials.json
   GOOGLE_SHEET_ID=your_sheet_id_here
   ```
3. Файл автоматично змонтується в контейнер

## 🐛 Вирішення проблем

### Бот не запускається

```bash
# Подивіться логи
docker-compose logs

# Перевірте що .env файл існує
ls -la .env

# Перевірте статус контейнера
docker-compose ps
```

### Помилка "Cannot connect to Docker daemon"

Docker не запущений. Запустіть Docker Desktop або Docker daemon.

### Змінив .env, але бот не бачить нові значення

```bash
# Перезапустіть контейнер
docker-compose restart
```

### Хочу видалити все і почати заново

```bash
# Зупинити і видалити контейнер
docker-compose down

# Видалити базу даних (УВАГА: всі дані будуть втрачені!)
rm -rf data/

# Запустити знову
./start.sh
```

## 📦 Що всередині образу?

- Python 3.11 (slim)
- Всі залежності з requirements.txt
- База даних SQLite в `/app/data/`
- Логи в `/app/logs/`
- Бот працює від non-root користувача для безпеки

## 🔒 Безпека

- Контейнер працює від non-root користувача
- `.env` файл не потрапляє в образ (додано в .dockerignore)
- База даних зберігається на хості (volume mount)
- Логи обмежені (10MB × 3 файли)

## 🚀 Деплой на сервер

### Швидкий деплой на VPS:

```bash
# На вашому VPS
git clone <your-repo>
cd FuelBot

# Налаштувати .env
nano .env

# Запустити
./start.sh
```

### Автозапуск після перезавантаження:

Docker Compose автоматично налаштовує `restart: unless-stopped`, тому бот буде автоматично запускатися після перезавантаження сервера.

## 💡 Поради

1. **Резервне копіювання:**
   ```bash
   # Зробити backup бази даних
   cp data/fuel_tracker.db data/fuel_tracker_backup_$(date +%Y%m%d).db
   ```

2. **Моніторинг:**
   ```bash
   # Дивитись логи в реальному часі
   docker-compose logs -f | grep -i error
   ```

3. **Оновлення:**
   ```bash
   git pull && docker-compose up -d --build
   ```

---

**Готово!** Тепер у вас є повністю працюючий FuelBot в Docker 🎉
