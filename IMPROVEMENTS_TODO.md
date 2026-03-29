# Список доработок для завершения

## ✅ Выполнено
1. Создано главное меню с inline-кнопками (`bot/keyboards/menu.py`)
2. Обновлен `bot/handlers/start.py` для работы с кнопками
3. Весь бот уже на украинском языке

## 📝 Нужно доделать

### 1. Обновить `bot/handlers/refuel.py`

Добавить callback handler для кнопки "⛽ Додати заправку":

```python
@router.callback_query(F.data == "add_refuel")
async def start_add_refuel(callback: CallbackQuery, state: FSMContext):
    """Start adding refuel from menu button"""
    await callback.answer()
    await cmd_add_refuel(callback.message, state)
```

И обновить все сообщения с ошибками/успехом - добавлять `reply_markup=get_back_to_menu_button()` или `get_main_menu()`

### 2. Обновить `bot/handlers/stats.py`

Добавить callback handlers:

```python
@router.callback_query(F.data == "show_stats")
async def show_stats_callback(callback: CallbackQuery):
    await callback.answer()
    await cmd_stats(callback.message)

@router.callback_query(F.data == "show_history")
async def show_history_callback(callback: CallbackQuery):
    await callback.answer()
    await cmd_history(callback.message)
```

### 3. Создать обработчики для новых кнопок

В `bot/handlers/start.py` или отдельном файле добавить:

```python
@router.callback_query(F.data == "my_vehicles")
async def show_my_vehicles(callback: CallbackQuery):
    """Show user vehicles"""
    text = "🚗 <b>Мої автомобілі</b>\n\nФункція в розробці..."
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_to_menu_button())
    await callback.answer()

@router.callback_query(F.data == "settings")
async def show_settings(callback: CallbackQuery):
    """Show settings"""
    text = "⚙️ <b>Налаштування</b>\n\nФункція в розробці..."
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_to_menu_button())
    await callback.answer()
```

### 4. Добавить поддержку нескольких автомобилей

#### 4.1. Создать модель Vehicle в `models/database.py`:
```python
class Vehicle(Base):
    __tablename__ = 'vehicles'

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    name: Mapped[str] = mapped_column(String(100))  # "Моя Тойота", "Робоча машина"
    brand: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # Relations
    user: Mapped["User"] = relationship(back_populates="vehicles")
    refuels: Mapped[list["Refuel"]] = relationship(back_populates="vehicle")
```

#### 4.2. Обновить модель User:
```python
vehicles: Mapped[list["Vehicle"]] = relationship(back_populates="user")
active_vehicle_id: Mapped[Optional[int]] = mapped_column(ForeignKey('vehicles.id'), nullable=True)
```

#### 4.3. Обновить модель Refuel:
```python
vehicle_id: Mapped[int] = mapped_column(ForeignKey('vehicles.id'))
vehicle: Mapped["Vehicle"] = relationship(back_populates="refuels")
```

#### 4.4. Создать handler для управления авто `bot/handlers/vehicles.py`:
```python
@router.callback_query(F.data == "my_vehicles")
async def show_vehicles_list(callback: CallbackQuery):
    """Show list of user vehicles"""
    # Получить список авто пользователя
    # Показать inline кнопки для каждого авто
    # Кнопка "Додати новий автомобіль"

@router.callback_query(F.data.startswith("select_vehicle:"))
async def select_vehicle(callback: CallbackQuery):
    """Select active vehicle"""
    vehicle_id = int(callback.data.split(":")[1])
    # Сделать этот авто активным

@router.callback_query(F.data == "add_vehicle")
async def start_add_vehicle(callback: CallbackQuery, state: FSMContext):
    """Start adding new vehicle"""
    # FSM для добавления нового авто
```

### 5. Создать миграцию базы данных

Создать alembic migration для добавления таблицы vehicles.

### 6. Обновить Docker и перезапустить

```bash
docker-compose down
docker-compose up -d --build
```

## Приоритеты

1. **Высокий**: Пункты 1-2 (обновить handlers для работы с кнопками)
2. **Средний**: Пункт 3 (заглушки для новых кнопок)
3. **Низкий**: Пункт 4-5 (поддержка нескольких авто - отдельная большая фича)

## Тестирование

После каждого изменения:
1. Перезапустить Docker
2. Отправить /start боту
3. Проверить все кнопки меню
4. Проверить процесс добавления заправки
