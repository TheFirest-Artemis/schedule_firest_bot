from aiogram.fsm.state import State, StatesGroup


class AuthGate(StatesGroup):
    waiting_for_password = State()


class GroupSetup(StatesGroup):
    waiting_for_group = State()


class DaysSetup(StatesGroup):
    waiting_for_days = State()
