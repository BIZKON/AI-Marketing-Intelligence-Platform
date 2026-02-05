"""Analyst Agent — competitive intelligence analysis.

Responsibilities:
- Trend detection across competitor content
- SWOT analysis
- Engagement pattern analysis
- Weekly/monthly competitive summaries
"""

from __future__ import annotations

from app.services.agents.base import BaseAgent


class AnalystAgent(BaseAgent):
    """AI agent specializing in competitive intelligence analysis."""

    @property
    def agent_name(self) -> str:
        return "analyst"

    @property
    def system_prompt(self) -> str:
        return """Ты — AI аналитик конкурентной разведки для маркетинговой платформы.

Твои задачи:
1. Анализировать контент конкурентов и выявлять тренды
2. Проводить SWOT-анализ на основе данных мониторинга
3. Определять паттерны вовлечённости (engagement patterns)
4. Выявлять возможности и угрозы для бренда клиента
5. Формировать инсайты на основе количественных данных

Формат ответа:
- Используй структурированный формат с разделами
- Приводи конкретные цифры и метрики из данных
- Делай чёткие выводы и рекомендации
- Пиши на русском языке

Когда данных недостаточно, честно об этом сообщай и предлагай что мониторить.

В конце каждого анализа добавляй JSON-блок с структурированными данными:
```json
{
  "trends": ["тренд 1", "тренд 2"],
  "opportunities": ["возможность 1"],
  "threats": ["угроза 1"],
  "top_performing_content": [{"platform": "...", "type": "...", "engagement": "..."}],
  "recommendations": ["рекомендация 1", "рекомендация 2"]
}
```"""

    def _build_user_message(self, context: str, query: str, **kwargs) -> str:
        brand_info = kwargs.get("brand_info", "")
        period = kwargs.get("period", "последняя неделя")

        message = f"""Проведи конкурентный анализ.

Период: {period}

Данные мониторинга конкурентов:
{context}
"""
        if brand_info:
            message += f"\nПрофиль бренда клиента:\n{brand_info}\n"

        message += f"\nЗапрос: {query}"
        return message
