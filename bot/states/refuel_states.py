"""
FSM States for refuel process
"""
from aiogram.fsm.state import State, StatesGroup


class RefuelStates(StatesGroup):
    """States for the refuel adding process"""
    waiting_for_receipt = State()
    confirm_receipt = State()
    asking_full_tank = State()
    waiting_for_odometer = State()
    confirm_odometer = State()


class BatchRefuelStates(StatesGroup):
    """States for batch refuel upload"""
    collecting_photos = State()
    confirming_batch = State()
    waiting_manual_date = State()


class SmartPhotoStates(StatesGroup):
    """Очікування другої частини пари (чек або одометр) після першого фото в smart-режимі"""
    waiting_pair = State()


class ManualRefuelStates(StatesGroup):
    """States for manual refuel entry (without photos)"""
    waiting_station = State()
    waiting_liters = State()
    waiting_price_per_liter = State()
    waiting_fuel_type = State()
    waiting_odometer = State()
    waiting_datetime = State()
    confirm_manual = State()
