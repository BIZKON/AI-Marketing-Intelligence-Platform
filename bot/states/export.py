from aiogram.fsm.state import State, StatesGroup


class ConnectTelegramStates(StatesGroup):
    waiting_api_id = State()
    waiting_api_hash = State()
    waiting_phone = State()
    waiting_code = State()
    waiting_2fa_password = State()


class ExportStates(StatesGroup):
    selecting_type = State()
    selecting_source = State()
    selecting_folder = State()
    configuring = State()
    confirming = State()


class SearchStates(StatesGroup):
    waiting_query = State()
