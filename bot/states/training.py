from aiogram.fsm.state import State, StatesGroup


class TrainingStates(StatesGroup):
    choosing_scenario = State()
    in_session = State()
