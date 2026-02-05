"""Marketer Agent — content strategy and planning.

Responsibilities:
- Content strategy generation based on competitor analysis
- Tone of voice recommendations
- Content calendar planning
- Platform-specific content adaptation
"""

from __future__ import annotations

from app.services.agents.base import BaseAgent


class MarketerAgent(BaseAgent):
    """AI agent specializing in content marketing strategy."""

    @property
    def agent_name(self) -> str:
        return "marketer"

    @property
    def system_prompt(self) -> str:
        return """Ты — AI маркетолог-стратег для маркетинговой платформы.

Твои задачи:
1. Создавать контент-стратегию на основе анализа конкурентов
2. Генерировать контент-планы с конкретными темами и форматами
3. Рекомендовать tone of voice для каждой платформы
4. Адаптировать контент под специфику каждой соцсети
5. Предлагать идеи контента которые отличают бренд от конкурентов

Формат ответа:
- Структурируй контент-план по дням/неделям
- Указывай платформу, формат, тему и ключевые тезисы для каждого поста
- Добавляй рекомендации по визуалу и хэштегам
- Пиши на русском языке

В конце добавляй JSON с контент-планом:
```json
{
  "strategy_summary": "краткое описание стратегии",
  "content_pillars": ["столп 1", "столп 2"],
  "tasks": [
    {
      "title": "Название поста",
      "platform": "telegram|youtube|vk|instagram",
      "format": "text|video|carousel|story|reels",
      "topic": "Описание темы",
      "key_points": ["тезис 1", "тезис 2"],
      "hashtags": ["#тег1", "#тег2"],
      "suggested_day": "monday|tuesday|..."
    }
  ],
  "tone_of_voice": "описание тона коммуникации"
}
```"""

    def _build_user_message(self, context: str, query: str, **kwargs) -> str:
        brand_info = kwargs.get("brand_info", "")
        period = kwargs.get("period", "weekly")
        target_platforms = kwargs.get("target_platforms", [])

        message = f"""Создай контент-стратегию.

Период планирования: {period}
"""
        if target_platforms:
            message += f"Целевые платформы: {', '.join(target_platforms)}\n"

        message += f"""
Инсайты из мониторинга конкурентов:
{context}
"""
        if brand_info:
            message += f"\nПрофиль бренда:\n{brand_info}\n"

        message += f"\nЗапрос: {query}"
        return message
