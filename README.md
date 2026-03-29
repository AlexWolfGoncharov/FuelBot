# FuelBot — Telegram-бот для обліку витрат на паливо

Telegram-бот для автоматичного обліку заправок з AI-розпізнаванням чеків та одометра (Google Gemini Vision).

**Репозиторій:** [github.com/AlexWolfGoncharov/FuelBot](https://github.com/AlexWolfGoncharov/FuelBot)

## Можливості

- Розпізнавання чеків АЗС та показань одометра з фото
- Розрахунок витрати л/100 км, конвертація в USD (курс ПриватБанку)
- Статистика та історія заправок
- Збереження в **SQLite** (локально) або **PostgreSQL** (наприклад Railway)
- Опційно — експорт у Google Sheets

## Вимоги

- Python 3.10+
- [Telegram Bot Token](https://t.me/BotFather)
- [Google Gemini API Key](https://ai.google.dev/)
- Google Sheets — за бажанням

## Швидкий старт

### Клонування

```bash
git clone https://github.com/AlexWolfGoncharov/FuelBot.git
cd FuelBot
```

### Локально (без Docker)

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Заповніть .env (BOT_TOKEN, GEMINI_API_KEY, ALLOWED_USER_IDS, …)
python bot/main.py
```

### Docker

```bash
cp .env.example .env
# Налаштуйте .env; для SQLite в контейнері зручно:
# DATABASE_URL=sqlite+aiosqlite:///./data/fuel_tracker.db
docker compose up -d --build
```

Детальніше: [DOCKER_QUICKSTART.md](DOCKER_QUICKSTART.md)

## Railway

1. **New Project** → Deploy from **GitHub** → репозиторій FuelBot.
2. Додай сервіс **PostgreSQL** (Add database → Postgres).
3. У сервісі **бота** → **Variables** → додай **`DATABASE_URL`** через **Reference** на змінну з сервісу Postgres (або встав URL вруучну з картки бази).
4. Додай вручну: `BOT_TOKEN`, `GEMINI_API_KEY`, `ALLOWED_USER_IDS`, за потреби `GOOGLE_SHEET_ID` та інше з `.env.example`.
5. **Google Sheets:** файл `credentials.json` у контейнер не кладуть. Створи змінну **`GOOGLE_SHEETS_CREDENTIALS_JSON`** і встав туди **весь вміст** JSON з service account (як у файлі з Google Cloud). Можна в один рядок. Якщо ця змінна задана, шлях `GOOGLE_SHEETS_CREDENTIALS_FILE` ігнорується.

Збірка йде з **`Dockerfile`**, конфіг у корені: **`railway.toml`**.

### Чи потрібен Volume у Railway?

**Ні**, якщо використовуєш **PostgreSQL** у Railway: усі дані бота зберігаються в керованій БД, окреме дискове сховище не потрібне.

**Volume** у Railway має сенс лише якщо ти свідомо зберігаєш щось у **файлах** у контейнері (наприклад, лише SQLite без Postgres, або великі локальні файли без S3). Для типового сценарію з Postgres — **не створюй Volume**.

## База даних

| Середовище | Підхід |
|------------|--------|
| Локально | За замовчуванням **SQLite**: `DATABASE_URL=sqlite+aiosqlite:///./fuel_tracker.db` |
| Railway / хмара | Підключіть **PostgreSQL**, у сервісі бота задайте `DATABASE_URL` з панелі Postgres (рядки `postgresql://` та `postgres://` автоматично перетворюються на `postgresql+asyncpg://`) |

### Міграція з SQLite в PostgreSQL

Один раз, з машини де лежить файл БД:

```bash
export POSTGRES_URL='postgresql://user:pass@host:port/dbname'   # або DATABASE_URL, якщо це саме Postgres
python scripts/migrate_sqlite_to_postgres.py --sqlite data/fuel_tracker.db
```

Повторний імпорт у непорожню базу (спочатку очистити таблиці):

```bash
python scripts/migrate_sqlite_to_postgres.py --sqlite data/fuel_tracker.db --truncate
```

Якщо в `.env` для Docker лишається SQLite, а Postgres потрібен лише для міграції, зручно задати цільовий URL через **`POSTGRES_URL`**, щоб не змінювати `DATABASE_URL` бота локально.

Якщо в PostgreSQL **немає рядків у `users`**, а заправки вже є (посилання `user_id` зламані), додай користувачів з локального SQLite:

```bash
export POSTGRES_URL='postgresql://...'
python scripts/sync_users_sqlite_to_postgres.py --sqlite data/fuel_tracker.db
```

Якщо в `refuels` є `user_id = 1`, а рядка `users` з `id = 1` немає (або він «чужий»), створи зв’язок із своїм Telegram вручну:

```bash
export POSTGRES_URL='postgresql://...'
python scripts/fix_user_row_for_refuels.py --user-id 1 --telegram-id ВАШ_TELEGRAM_ID
```

(`ВАШ_TELEGRAM_ID` — той самий числовий id, що в `ALLOWED_USER_IDS`.)

### Важливо для Telegram

Одночасно не запускайте **два** процеси з одним `BOT_TOKEN` (наприклад локально і на Railway у режимі polling) — отримуватиме лише один клієнт.

## Змінні оточення

Скопіюйте `.env.example` → `.env`. Основне:

| Змінна | Опис |
|--------|------|
| `BOT_TOKEN` | Токен від @BotFather |
| `ALLOWED_USER_IDS` | Telegram user id через кому |
| `GEMINI_API_KEY` | Ключ Gemini |
| `GEMINI_MODEL` | Опційно: напр. `gemini-2.5-flash` (за замовчуванням) або `gemini-2.0-flash` |
| `DATABASE_URL` | SQLite або PostgreSQL |
| `POSTGRES_URL` | Опційно: лише для скрипта міграції, якщо `DATABASE_URL` — SQLite |
| `GOOGLE_SHEET_ID` | За потреби інтеграції з таблицею |
| `GOOGLE_SHEETS_CREDENTIALS_JSON` | Опційно: повний JSON service account (для Railway замість файлу) |

Повний приклад — у `.env.example`.

## Структура проекту

```
FuelBot/
├── bot/
│   ├── handlers/       # Команди та сценарії
│   ├── keyboards/
│   ├── states/         # FSM
│   └── main.py
├── config/
│   ├── settings.py
│   ├── db_url.py       # Нормалізація URL БД для asyncpg
│   └── logging_config.py
├── models/             # SQLAlchemy
├── scripts/
│   ├── migrate_sqlite_to_postgres.py
│   ├── sync_users_sqlite_to_postgres.py
│   └── fix_user_row_for_refuels.py
├── services/           # AI, валюта, Google Sheets, …
├── Dockerfile
├── docker-compose.yml
├── railway.toml
├── requirements.txt
└── README.md
```

## Команди бота

- `/start`, `/help`, `/cancel`
- `/add` — нова заправка (чек → одометр)
- `/stats`, `/history` — статистика та історія

## Google Sheets (опційно)

Створіть service account, збережіть `credentials.json` у корінь (файл у `.gitignore`), надайте доступ до таблиці email з JSON, вкажіть `GOOGLE_SHEET_ID` у `.env`. Детальні кроки — у розділі Google Sheets у попередніх інструкціях або в [DOCKER_QUICKSTART.md](DOCKER_QUICKSTART.md).

## Docker: корисні команди

```bash
docker compose up -d
docker compose logs -f
docker compose restart
docker compose down
```

## Вирішення проблем

- **Бот не стартує** — перевірте `.env`, `pip install -r requirements.txt`, логи (`bot.log` або `docker compose logs`).
- **Gemini** — ліміти та якість фото; див. [Google AI](https://ai.google.dev/).
- **PostgreSQL** — чи доступний хост з вашої мережі (інколи потрібен `?sslmode=require` у URL для публічного endpoint).
- **SQLite** — файл `*.db` створюється автоматично; перегляд: `sqlite3 fuel_tracker.db`.

## Ліцензія

MIT

---

Зроблено для зручного обліку заправок у дорозі.
