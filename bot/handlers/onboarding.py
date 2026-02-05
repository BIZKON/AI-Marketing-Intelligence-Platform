"""Onboarding handler: 3-step brand profile setup via FSM."""

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.middlewares.auth import invalidate_cache
from bot.services.api_client import APIClient
from bot.states.onboarding import OnboardingStates

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("setup"))
async def cmd_setup(message: Message, state: FSMContext, **kwargs) -> None:
    await state.set_state(OnboardingStates.waiting_brand_name)
    await message.answer(
        "<b>Настройка профиля бренда</b>\n\n"
        "Шаг 1/3: Введите название вашего бренда или компании:"
    )


@router.message(OnboardingStates.waiting_brand_name)
async def process_brand_name(message: Message, state: FSMContext) -> None:
    if not message.text or len(message.text.strip()) < 2:
        await message.answer("Название должно содержать минимум 2 символа. Попробуйте ещё раз:")
        return

    await state.update_data(brand_name=message.text.strip())
    await state.set_state(OnboardingStates.waiting_brand_description)
    await message.answer(
        "Шаг 2/3: Кратко опишите ваш бренд и чем вы занимаетесь.\n"
        "(Это поможет AI генерировать релевантный контент.)"
    )


@router.message(OnboardingStates.waiting_brand_description)
async def process_brand_description(message: Message, state: FSMContext) -> None:
    if not message.text or len(message.text.strip()) < 10:
        await message.answer("Описание должно содержать минимум 10 символов. Попробуйте ещё раз:")
        return

    await state.update_data(brand_description=message.text.strip())
    await state.set_state(OnboardingStates.waiting_tone_of_voice)
    await message.answer(
        "Шаг 3/3: Опишите tone of voice вашего бренда.\n"
        "Примеры: профессиональный, дружелюбный, экспертный, неформальный, технический..."
    )


@router.message(OnboardingStates.waiting_tone_of_voice)
async def process_tone_of_voice(
    message: Message,
    state: FSMContext,
    api: APIClient = None,
    telegram_id: int = 0,
    **kwargs,
) -> None:
    if not message.text or len(message.text.strip()) < 3:
        await message.answer("Пожалуйста, опишите tone of voice хотя бы парой слов:")
        return

    data = await state.get_data()
    brand_name = data["brand_name"]
    brand_description = data["brand_description"]
    tone_of_voice = message.text.strip()

    # Save to backend via API
    if api:
        try:
            await api.update_profile(
                brand_name=brand_name,
                brand_description=brand_description,
                tone_of_voice=tone_of_voice,
            )
            # Invalidate cached user data so next request gets fresh profile
            invalidate_cache(telegram_id)
        except Exception:
            logger.exception("Failed to save brand profile")
            await state.clear()
            await message.answer(
                "Произошла ошибка при сохранении профиля. Попробуйте /setup заново."
            )
            return

    await state.clear()
    await message.answer(
        "<b>Профиль настроен!</b>\n\n"
        f"Бренд: <b>{brand_name}</b>\n"
        f"Описание: {brand_description}\n"
        f"Tone of voice: {tone_of_voice}\n\n"
        "Следующие шаги:\n"
        "/competitors — добавить конкурентов\n"
        "/billing — выбрать тарифный план"
    )
