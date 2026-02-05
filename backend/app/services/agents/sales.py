"""Sales Agent — sales-oriented content and funnel insights.

Responsibilities:
- Sales funnel analysis from competitor content
- CTA and conversion pattern detection
- Lead generation content recommendations
- Promotional calendar insights
"""

from __future__ import annotations

from app.services.agents.base import BaseAgent


class SalesAgent(BaseAgent):
    """AI agent specializing in sales-oriented analysis and content."""

    @property
    def agent_name(self) -> str:
        return "sales"

    @property
    def system_prompt(self) -> str:
        return """Ты — AI sales-аналитик для маркетинговой платформы.

Твои задачи:
1. Анализировать воронки продаж конкурентов по их контенту
2. Выявлять эффективные CTA и офферы в контенте конкурентов
3. Определять промо-активности и сезонные паттерны
4. Рекомендовать sales-контент на основе конкурентного анализа
5. Находить точки дифференциации для продаж

Формат ответа:
- Структурируй анализ по этапам воронки (TOFU/MOFU/BOFU)
- Приводи конкретные примеры CTA из контента конкурентов
- Рекомендуй конкретные форматы и подходы
- Пиши на русском языке

В конце добавляй JSON:
```json
{
  "funnel_analysis": {
    "tofu": {"competitor_tactics": [], "recommendations": []},
    "mofu": {"competitor_tactics": [], "recommendations": []},
    "bofu": {"competitor_tactics": [], "recommendations": []}
  },
  "effective_ctas": ["CTA 1", "CTA 2"],
  "promo_patterns": ["паттерн 1"],
  "sales_content_ideas": [
    {
      "title": "Идея",
      "funnel_stage": "tofu|mofu|bofu",
      "format": "post|video|lead_magnet|case_study",
      "description": "описание"
    }
  ],
  "competitive_advantages": ["преимущество 1"]
}
```"""

    def _build_user_message(self, context: str, query: str, **kwargs) -> str:
        brand_info = kwargs.get("brand_info", "")
        products = kwargs.get("products", "")

        message = f"""Проведи sales-анализ контента конкурентов.

Данные мониторинга:
{context}
"""
        if brand_info:
            message += f"\nПрофиль бренда:\n{brand_info}\n"
        if products:
            message += f"\nПродукты/услуги клиента:\n{products}\n"

        message += f"\nЗапрос: {query}"
        return message
