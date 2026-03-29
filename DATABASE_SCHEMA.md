# 🗄️ Структура бази даних FuelBot

## Таблиці

### 1. `users` - Користувачі бота

Зберігає інформацію про користувачів Telegram.

| Поле | Тип | Опис |
|------|-----|------|
| `id` | INTEGER | Primary Key, автоінкремент |
| `telegram_id` | BIGINT | Telegram User ID (унікальний) |
| `username` | VARCHAR(255) | Telegram username (@username) |
| `first_name` | VARCHAR(255) | Ім'я користувача |
| `created_at` | DATETIME | Дата реєстрації |

**Індекси:**
- `telegram_id` - унікальний індекс для швидкого пошуку

**Приклад:**
```sql
SELECT * FROM users;
```
| id | telegram_id | username | first_name | created_at |
|----|-------------|----------|------------|------------|
| 1 | 123456789 | johndoe | John | 2024-01-15 10:30:00 |

---

### 2. `refuels` - Заправки

Основна таблиця з даними про заправки.

#### Основні поля

| Поле | Тип | Опис |
|------|-----|------|
| `id` | INTEGER | Primary Key, автоінкремент |
| `user_id` | INTEGER | ID користувача |
| `date` | DATETIME | Дата та час заправки |
| `station_name` | VARCHAR(255) | Назва АЗС (ОККО, WOG тощо) |
| `fuel_type` | VARCHAR(50) | Тип палива (А-92, А-95, ДП) |

#### Дані про паливо (в гривнях)

| Поле | Тип | Опис |
|------|-----|------|
| `liters` | DECIMAL(10,2) | Літри палива |
| `price_per_liter` | DECIMAL(10,2) | Ціна за літр (грн) |
| `total_cost` | DECIMAL(10,2) | Загальна сума (грн) |

#### Конвертація в USD

| Поле | Тип | Опис |
|------|-----|------|
| `usd_rate` | DECIMAL(10,4) | Курс USD на момент заправки |
| `total_cost_usd` | DECIMAL(10,2) | Загальна сума в USD |
| `price_per_liter_usd` | DECIMAL(10,4) | Ціна за літр в USD |

#### Дані про пробіг

| Поле | Тип | Опис |
|------|-----|------|
| `odometer` | INTEGER | Показання одометра (км) |
| `distance_from_last` | INTEGER | Пробіг з попередньої заправки (км) |
| `consumption` | DECIMAL(5,2) | Витрата палива (л/100км) |

#### Геолокація

| Поле | Тип | Опис |
|------|-----|------|
| `latitude` | DECIMAL(10,7) | Широта (з EXIF фото) |
| `longitude` | DECIMAL(10,7) | Довгота (з EXIF фото) |

#### Файли та метадані

| Поле | Тип | Опис |
|------|-----|------|
| `receipt_file_id` | VARCHAR(255) | Telegram File ID чека |
| `odometer_file_id` | VARCHAR(255) | Telegram File ID одометра |
| `ai_confidence` | INTEGER | Впевненість AI (0-100) |
| `created_at` | DATETIME | Дата створення запису |
| `updated_at` | DATETIME | Дата оновлення запису |

**Індекси:**
- `user_id` - для швидкого пошуку за користувачем
- `date` - для пошуку по датах

**Приклад запису:**
```sql
SELECT * FROM refuels WHERE user_id = 1 ORDER BY date DESC LIMIT 1;
```

| id | user_id | date | station_name | fuel_type | liters | price_per_liter | total_cost | usd_rate | total_cost_usd | odometer | consumption |
|----|---------|------|--------------|-----------|--------|-----------------|------------|----------|----------------|----------|-------------|
| 1 | 1 | 2024-01-15 14:30:00 | ОККО | А-95 | 45.50 | 52.90 | 2406.95 | 36.5686 | 65.81 | 125430 | 8.50 |

---

## Корисні SQL запити

### Загальна статистика за місяць

```sql
SELECT
    COUNT(*) as refuels,
    SUM(liters) as total_liters,
    SUM(total_cost) as total_uah,
    SUM(total_cost_usd) as total_usd,
    AVG(price_per_liter) as avg_price_uah,
    AVG(consumption) as avg_consumption
FROM refuels
WHERE user_id = 1
  AND date >= date('now', 'start of month');
```

### Середня витрата палива

```sql
SELECT
    AVG(consumption) as avg_consumption_l100km
FROM refuels
WHERE user_id = 1
  AND consumption IS NOT NULL;
```

### Витрати по АЗС

```sql
SELECT
    station_name,
    COUNT(*) as visits,
    SUM(total_cost) as total_spent_uah,
    AVG(price_per_liter) as avg_price
FROM refuels
WHERE user_id = 1
GROUP BY station_name
ORDER BY visits DESC;
```

### Динаміка цін на паливо (в USD для коректного порівняння)

```sql
SELECT
    DATE(date) as refuel_date,
    price_per_liter as price_uah,
    price_per_liter_usd as price_usd,
    usd_rate
FROM refuels
WHERE user_id = 1
  AND fuel_type = 'А-95'
ORDER BY date DESC
LIMIT 10;
```

### Загальний пробіг за період

```sql
SELECT
    SUM(distance_from_last) as total_km,
    SUM(liters) as total_fuel,
    SUM(total_cost) as total_spent_uah,
    SUM(total_cost_usd) as total_spent_usd
FROM refuels
WHERE user_id = 1
  AND date >= '2024-01-01'
  AND distance_from_last IS NOT NULL;
```

### Найвигідніші заправки (ціна в USD)

```sql
SELECT
    date,
    station_name,
    price_per_liter_usd,
    total_cost_usd,
    liters
FROM refuels
WHERE user_id = 1
  AND price_per_liter_usd IS NOT NULL
ORDER BY price_per_liter_usd ASC
LIMIT 10;
```

---

## Міграція даних

Якщо потрібно додати нові поля, використовуйте SQLAlchemy Alembic або вручну:

```sql
-- Приклад додавання нового поля
ALTER TABLE refuels ADD COLUMN notes TEXT;

-- Оновлення існуючих даних
UPDATE refuels SET notes = '' WHERE notes IS NULL;
```

---

## Резервне копіювання

### Створення бекапу

```bash
# SQLite база
cp fuel_tracker.db fuel_tracker_backup_$(date +%Y%m%d).db

# Або експорт в SQL
sqlite3 fuel_tracker.db .dump > backup.sql
```

### Відновлення з бекапу

```bash
# З файлу бази
cp fuel_tracker_backup_20240115.db fuel_tracker.db

# З SQL файлу
sqlite3 fuel_tracker.db < backup.sql
```

---

## Аналіз даних

### Перегляд структури

```bash
sqlite3 fuel_tracker.db

.schema users
.schema refuels
```

### Експорт в CSV

```sql
.mode csv
.output refuels_export.csv
SELECT * FROM refuels WHERE user_id = 1;
.output stdout
```

### Статистика по місяцях

```sql
SELECT
    strftime('%Y-%m', date) as month,
    COUNT(*) as refuels,
    SUM(liters) as total_liters,
    SUM(total_cost_usd) as total_usd,
    AVG(consumption) as avg_consumption
FROM refuels
WHERE user_id = 1
GROUP BY month
ORDER BY month DESC;
```

---

## Оптимізація

### Створення індексів для швидкого пошуку

```sql
CREATE INDEX IF NOT EXISTS idx_user_date ON refuels(user_id, date);
CREATE INDEX IF NOT EXISTS idx_station ON refuels(station_name);
CREATE INDEX IF NOT EXISTS idx_fuel_type ON refuels(fuel_type);
```

### Очищення старих даних (якщо потрібно)

```sql
-- Видалити записи старше 2 років
DELETE FROM refuels
WHERE date < datetime('now', '-2 years');

-- Vacuum для звільнення місця
VACUUM;
```

---

Це детальна документація структури бази даних FuelBot. Використовуйте ці запити для аналізу ваших витрат на паливо! 📊
