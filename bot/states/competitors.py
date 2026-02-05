from aiogram.fsm.state import State, StatesGroup


class AddCompetitorStates(StatesGroup):
    waiting_name = State()
    waiting_url = State()
    waiting_platforms = State()
