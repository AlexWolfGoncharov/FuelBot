"""
FSM States for editing refuel records
"""
from aiogram.fsm.state import State, StatesGroup


class EditRefuelStates(StatesGroup):
    """States for editing refuel flow"""
    choosing_field = State()  # User choosing which field to edit
    editing_date = State()
    editing_liters = State()
    editing_price = State()
    editing_odometer = State()
    editing_station = State()
    editing_fuel_type = State()
