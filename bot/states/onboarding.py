from aiogram.fsm.state import State, StatesGroup


class OnboardingStates(StatesGroup):
    waiting_brand_name = State()
    waiting_brand_description = State()
    waiting_tone_of_voice = State()
