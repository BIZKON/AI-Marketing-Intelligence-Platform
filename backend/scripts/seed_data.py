"""Seed data — populate the database with training scenarios, demo user, and initial achievements.

Usage:
    cd backend && python -m scripts.seed_data

Requires DATABASE_URL to be set (or .env in the project root).
"""

from __future__ import annotations

import asyncio
import uuid
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory, engine
from app.models.training_scenario import ScenarioDifficulty, ScenarioType, TrainingScenario

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── Seed Scenarios ────────────────────────────────────────────────────────────

SEED_SCENARIOS: list[dict] = [
    {
        "title": "Входящий звонок — запись на пробное занятие",
        "description": (
            "Клиент звонит в студию йоги 'Алхимия' и интересуется пробным занятием. "
            "Задача администратора — узнать потребности, рассказать о студии и записать на пробное."
        ),
        "type": ScenarioType.INCOMING_CALL,
        "difficulty": ScenarioDifficulty.EASY,
        "client_persona": {
            "name": "Мария",
            "age": 32,
            "occupation": "офис-менеджер",
            "motivation": "хочет снять напряжение в спине после работы",
            "objections": ["нет времени", "дорого ли"],
            "personality": "дружелюбная, но немного нерешительная",
        },
        "system_prompt": (
            "Ты — Мария, 32 года, офис-менеджер. Ты позвонила в студию йоги 'Алхимия'. "
            "У тебя болит спина после работы, ты хочешь попробовать йогу. "
            "Ты дружелюбная, но немного нерешительная. Спрашиваешь о расписании, ценах, "
            "и нужен ли опыт для начала. Если администратор хорошо отвечает — соглашаешься на пробное. "
            "Если давит — сомневаешься. Отвечай на русском, коротко (1-3 предложения)."
        ),
        "ideal_script": (
            "1. Приветствие: 'Добрый день! Студия йоги Алхимия, меня зовут [имя], чем могу помочь?'\n"
            "2. Выявление потребности: 'Расскажите, что вас привело к нам?'\n"
            "3. Презентация: 'У нас есть мягкие классы, идеально для спины...'\n"
            "4. Работа с возражениями: 'Пробное занятие бесплатное / по акции...'\n"
            "5. Закрытие: 'Давайте я запишу вас на удобное время. Какой день подходит?'"
        ),
        "success_criteria": {
            "must_ask_name": True,
            "must_discover_need": True,
            "must_present_trial": True,
            "must_close": True,
        },
        "tags": ["входящий", "пробное", "лёгкий"],
    },
    {
        "title": "Исходящий звонок — возврат ушедшего клиента",
        "description": (
            "Клиент не ходил в студию 2 месяца. Задача — выяснить причину ухода, "
            "предложить мотивирующее решение и вернуть клиента."
        ),
        "type": ScenarioType.OUTBOUND_CALL,
        "difficulty": ScenarioDifficulty.MEDIUM,
        "client_persona": {
            "name": "Елена",
            "age": 28,
            "occupation": "дизайнер",
            "motivation": "раньше нравилось, но пропустила — потеряла мотивацию",
            "objections": ["нет времени", "я уже всё забыла", "может потом"],
            "personality": "вежливая, но уклончивая, не любит давления",
        },
        "system_prompt": (
            "Ты — Елена, 28 лет, дизайнер. Раньше ходила в студию 'Алхимия' 3 месяца, "
            "но пропустила 2 месяца и потеряла мотивацию. Тебе звонит администратор студии. "
            "Ты вежливая, но уклончивая. Основные возражения: 'нет времени', 'уже всё забыла', "
            "'может потом вернусь'. Если администратор эмпатичен и предлагает конкретный план — "
            "готова подумать. Если давит — отказываешь. Отвечай по-русски, 1-3 предложения."
        ),
        "ideal_script": (
            "1. Приветствие: 'Здравствуйте, Елена! Это [имя] из студии Алхимия.'\n"
            "2. Мягкий вход: 'Мы заметили, что давно вас не видели. Как у вас дела?'\n"
            "3. Выяснение причины: 'Что помешало продолжить? Может, мы можем помочь?'\n"
            "4. Предложение: 'У нас есть новое расписание / акция возврата...'\n"
            "5. Закрытие: 'Может, попробуем записаться на эту субботу? Без обязательств.'"
        ),
        "success_criteria": {
            "must_empathize": True,
            "must_discover_reason": True,
            "must_offer_solution": True,
            "must_soft_close": True,
        },
        "tags": ["исходящий", "возврат", "средний"],
    },
    {
        "title": "Работа с возражением 'Дорого'",
        "description": (
            "Клиент интересуется абонементом, но считает цену высокой. "
            "Отработайте возражение 'дорого' через ценность, а не скидку."
        ),
        "type": ScenarioType.OBJECTION_HANDLING,
        "difficulty": ScenarioDifficulty.MEDIUM,
        "client_persona": {
            "name": "Андрей",
            "age": 40,
            "occupation": "предприниматель",
            "motivation": "хочет поддерживать здоровье, но считает деньги",
            "objections": ["дорого", "в фитнесе дешевле", "сколько стоит разовое"],
            "personality": "прямой, конкретный, ценит время",
        },
        "system_prompt": (
            "Ты — Андрей, 40 лет, предприниматель. Пришёл в студию 'Алхимия', "
            "спрашиваешь цены на абонемент. Когда узнаёшь цену — говоришь 'дорого'. "
            "Сравниваешь с фитнес-клубом. Ты прямой и конкретный, ценишь время. "
            "Если администратор грамотно раскроет ценность и покажет выгоду — готов купить. "
            "Если просто снижает цену — подозреваешь подвох. Русский, 1-3 предложения."
        ),
        "ideal_script": (
            "1. Выслушать возражение полностью\n"
            "2. Согласиться: 'Понимаю, цена — важный фактор'\n"
            "3. Раскрыть ценность: малые группы, индивидуальный подход, квалификация тренеров\n"
            "4. Посчитать: 'Если разделить на занятия, получается X руб за занятие'\n"
            "5. Предложить альтернативу: пакет поменьше, рассрочку\n"
            "6. Закрыть: 'Давайте попробуем месячный пакет и оцените разницу'"
        ),
        "success_criteria": {
            "must_listen": True,
            "must_acknowledge": True,
            "must_show_value": True,
            "must_offer_alternative": True,
        },
        "tags": ["возражения", "дорого", "средний"],
    },
    {
        "title": "Закрытие сделки — продажа годового абонемента",
        "description": (
            "Клиент уже ходит месяц и доволен. Задача — предложить годовой абонемент "
            "с максимальной выгодой и закрыть сделку."
        ),
        "type": ScenarioType.CLOSING,
        "difficulty": ScenarioDifficulty.HARD,
        "client_persona": {
            "name": "Ольга",
            "age": 35,
            "occupation": "маркетолог",
            "motivation": "нравится студия, но боится долгосрочных обязательств",
            "objections": ["а вдруг перестану ходить", "большая сумма сразу", "надо подумать"],
            "personality": "аналитичная, любит взвешивать 'за' и 'против'",
        },
        "system_prompt": (
            "Ты — Ольга, 35 лет, маркетолог. Ходишь в 'Алхимию' уже месяц, тебе нравится. "
            "Администратор предлагает годовой абонемент. Ты аналитичная, взвешиваешь все 'за' и 'против'. "
            "Возражения: 'а вдруг перестану ходить', 'большая сумма сразу', 'надо подумать'. "
            "Если администратор хорошо работает с каждым возражением и показывает экономию — "
            "соглашаешься. Если торопит — просишь время подумать. Русский, 1-3 предложения."
        ),
        "ideal_script": (
            "1. Комплимент прогрессу клиента\n"
            "2. Предложить годовой абонемент с расчётом экономии\n"
            "3. Отработать 'вдруг перестану': заморозка, перенос, гарантия возврата\n"
            "4. Отработать 'большая сумма': рассрочка, помесячная оплата\n"
            "5. Создать срочность: 'Акция до конца недели'\n"
            "6. Мягкое закрытие: 'Оформим сейчас? Я зарезервирую для вас эту цену'"
        ),
        "success_criteria": {
            "must_build_value": True,
            "must_handle_3_objections": True,
            "must_show_savings": True,
            "must_close_or_schedule_followup": True,
        },
        "tags": ["закрытие", "годовой", "сложный"],
    },
    {
        "title": "Партнёрское предложение — фитнес-блогер",
        "description": (
            "Вы звоните фитнес-блогеру с предложением о сотрудничестве. "
            "Задача — презентовать студию и договориться о визите."
        ),
        "type": ScenarioType.PARTNER_PITCH,
        "difficulty": ScenarioDifficulty.HARD,
        "client_persona": {
            "name": "Кристина",
            "age": 26,
            "occupation": "фитнес-блогер, 50K подписчиков",
            "motivation": "ищет интересный контент и партнёрства",
            "objections": ["мне каждый день пишут", "что я получу", "йога — не мой формат"],
            "personality": "энергичная, занятая, привыкла к предложениям",
        },
        "system_prompt": (
            "Ты — Кристина, 26 лет, фитнес-блогер с 50K подписчиков в Instagram. "
            "Тебе звонит администратор студии 'Алхимия' с предложением о сотрудничестве. "
            "Ты получаешь такие предложения каждый день и привыкла. Тебе нужен конкретный "
            "выгодный оффер. Возражения: 'мне каждый день пишут', 'что я получу', "
            "'йога — не мой формат'. Если предложение уникальное и выгодное — заинтересуешься. "
            "Если шаблонное — быстро закончишь разговор. Русский, 1-3 предложения."
        ),
        "ideal_script": (
            "1. Зацепить внимание: 'Кристина, мы видели ваш контент о [тема] — впечатляет!'\n"
            "2. Быстрый питч: 'Мы — студия йоги Алхимия, хотим предложить уникальный формат'\n"
            "3. Конкретика: бесплатный абонемент + фотосессия в студии + коллаб-контент\n"
            "4. Уникальность: 'Вашим подписчикам — эксклюзивная акция'\n"
            "5. Закрытие: 'Можем организовать гостевой визит в удобное для вас время?'"
        ),
        "success_criteria": {
            "must_personalize": True,
            "must_show_unique_value": True,
            "must_offer_concrete_deal": True,
            "must_schedule_next_step": True,
        },
        "tags": ["партнёрство", "блогер", "сложный"],
    },
]


async def seed_scenarios(db: AsyncSession) -> int:
    """Insert seed scenarios if they don't already exist. Returns count of inserted."""
    existing = await db.execute(select(TrainingScenario.title))
    existing_titles = {r[0] for r in existing.all()}

    inserted = 0
    for data in SEED_SCENARIOS:
        if data["title"] in existing_titles:
            logger.info("Scenario already exists: %s", data["title"])
            continue

        scenario = TrainingScenario(
            id=uuid.uuid4(),
            title=data["title"],
            description=data["description"],
            type=data["type"],
            difficulty=data["difficulty"],
            client_persona=data["client_persona"],
            system_prompt=data["system_prompt"],
            ideal_script=data["ideal_script"],
            success_criteria=data["success_criteria"],
            is_public=True,
            tags=data.get("tags"),
        )
        db.add(scenario)
        inserted += 1
        logger.info("Added scenario: %s", data["title"])

    await db.commit()
    return inserted


async def main() -> None:
    logger.info("=== Seeding database ===")

    async with async_session_factory() as db:
        count = await seed_scenarios(db)
        logger.info("Inserted %d new scenarios (of %d total defined)", count, len(SEED_SCENARIOS))

    await engine.dispose()
    logger.info("=== Seed complete ===")


if __name__ == "__main__":
    asyncio.run(main())
