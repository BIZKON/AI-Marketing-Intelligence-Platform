from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.states.onboarding import OnboardingStates

router = Router()


@router.message(Command("setup"))
async def cmd_setup(message: Message, state: FSMContext) -> None:
    await state.set_state(OnboardingStates.waiting_brand_name)
    await message.answer(
        "<b>Let's set up your account!</b>\n\n"
        "Step 1/3: What is your brand or company name?"
    )


@router.message(OnboardingStates.waiting_brand_name)
async def process_brand_name(message: Message, state: FSMContext) -> None:
    await state.update_data(brand_name=message.text)
    await state.set_state(OnboardingStates.waiting_brand_description)
    await message.answer(
        "Step 2/3: Briefly describe your brand and what you do.\n"
        "(This helps AI generate relevant content for you.)"
    )


@router.message(OnboardingStates.waiting_brand_description)
async def process_brand_description(message: Message, state: FSMContext) -> None:
    await state.update_data(brand_description=message.text)
    await state.set_state(OnboardingStates.waiting_tone_of_voice)
    await message.answer(
        "Step 3/3: Describe your brand's tone of voice.\n"
        "Examples: professional, friendly, casual, technical, humorous..."
    )


@router.message(OnboardingStates.waiting_tone_of_voice)
async def process_tone_of_voice(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    # TODO: save to DB via API
    await state.clear()
    await message.answer(
        f"<b>Setup complete!</b>\n\n"
        f"Brand: {data['brand_name']}\n"
        f"Description: {data['brand_description']}\n"
        f"Tone: {message.text}\n\n"
        "Use /competitors to start tracking competitors.\n"
        "Use /billing to manage your subscription."
    )
