"""PDF report generator — converts digest reports to rich PDF with charts.

Uses ReportLab for layout and embeds Matplotlib chart images.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.services.media.chart_renderer import (
    render_engagement_bar_chart,
    render_engagement_pie_chart,
    render_er_comparison_chart,
    render_posts_comparison_chart,
)

logger = logging.getLogger(__name__)

# Brand colors
PRIMARY = colors.HexColor("#6366f1")
SECONDARY = colors.HexColor("#8b5cf6")
DARK = colors.HexColor("#1e1b4b")
LIGHT_BG = colors.HexColor("#f8f9fa")


def generate_digest_pdf(report_content: dict[str, Any], title: str = "") -> bytes:
    """Generate a PDF document from a digest report.

    Args:
        report_content: The report.content JSONB data containing stats and analysis.
        title: Report title.

    Returns:
        PDF file as bytes.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontSize=22,
        textColor=DARK,
        spaceAfter=12,
    )
    heading_style = ParagraphStyle(
        "ReportHeading",
        parent=styles["Heading2"],
        fontSize=16,
        textColor=PRIMARY,
        spaceBefore=16,
        spaceAfter=8,
    )
    body_style = ParagraphStyle(
        "ReportBody",
        parent=styles["BodyText"],
        fontSize=11,
        leading=16,
        spaceAfter=6,
    )
    meta_style = ParagraphStyle(
        "ReportMeta",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.grey,
        spaceAfter=16,
    )

    elements: list = []
    stats: dict = report_content.get("stats", {})

    # ── Title page ──
    elements.append(Spacer(1, 3 * cm))
    elements.append(Paragraph(title or "Дайджест конкурентной разведки", title_style))

    period_start = report_content.get("period_start", "")[:10]
    period_end = report_content.get("period_end", "")[:10]
    competitors_count = report_content.get("competitors_analyzed", 0)
    total_posts = report_content.get("total_posts", 0)

    elements.append(Paragraph(
        f"Период: {period_start} — {period_end}<br/>"
        f"Конкурентов: {competitors_count} | Постов: {total_posts}<br/>"
        f"Дата генерации: {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')} UTC",
        meta_style,
    ))

    elements.append(Spacer(1, 1 * cm))

    # ── Stats table ──
    if stats:
        elements.append(Paragraph("Общая статистика", heading_style))
        table_data = [["Конкурент", "Посты", "Просмотры", "Лайки", "Комменты", "ER"]]
        for s in stats.values():
            table_data.append([
                s["name"],
                str(s.get("post_count", 0)),
                f"{s.get('total_views', 0):,}",
                f"{s.get('total_likes', 0):,}",
                f"{s.get('total_comments', 0):,}",
                f"{s.get('avg_engagement_rate', 0):.4f}",
            ])

        table = Table(table_data, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.Color(0.8, 0.8, 0.8)),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 1 * cm))

    # ── Charts ──
    if stats and len(stats) > 0:
        elements.append(PageBreak())
        elements.append(Paragraph("Визуализация", heading_style))

        # Engagement bar chart
        try:
            chart_png = render_engagement_bar_chart(stats)
            img = Image(io.BytesIO(chart_png), width=16 * cm, height=10 * cm)
            elements.append(img)
            elements.append(Spacer(1, 0.5 * cm))
        except Exception:
            logger.exception("Failed to render engagement chart")

        # Posts vs views
        try:
            chart_png = render_posts_comparison_chart(stats)
            img = Image(io.BytesIO(chart_png), width=16 * cm, height=9 * cm)
            elements.append(img)
            elements.append(Spacer(1, 0.5 * cm))
        except Exception:
            logger.exception("Failed to render posts chart")

        elements.append(PageBreak())

        # Engagement pie
        try:
            chart_png = render_engagement_pie_chart(stats)
            img = Image(io.BytesIO(chart_png), width=14 * cm, height=14 * cm)
            elements.append(img)
            elements.append(Spacer(1, 0.5 * cm))
        except Exception:
            logger.exception("Failed to render pie chart")

        # ER comparison
        try:
            chart_png = render_er_comparison_chart(stats)
            img = Image(io.BytesIO(chart_png), width=16 * cm, height=9 * cm)
            elements.append(img)
        except Exception:
            logger.exception("Failed to render ER chart")

    # ── AI Analysis ──
    ai_analysis = report_content.get("ai_analysis", "")
    if ai_analysis:
        elements.append(PageBreak())
        elements.append(Paragraph("AI-анализ", heading_style))

        for paragraph in ai_analysis.split("\n\n"):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            # Handle markdown-like headings
            if paragraph.startswith("##"):
                clean = paragraph.lstrip("#").strip()
                elements.append(Paragraph(clean, heading_style))
            elif paragraph.startswith("- ") or paragraph.startswith("* "):
                for line in paragraph.split("\n"):
                    line = line.lstrip("- *").strip()
                    if line:
                        elements.append(Paragraph(f"• {_escape_xml(line)}", body_style))
            else:
                elements.append(Paragraph(_escape_xml(paragraph), body_style))
            elements.append(Spacer(1, 2 * mm))

    # ── Footer note ──
    elements.append(Spacer(1, 2 * cm))
    elements.append(Paragraph(
        "Отчёт сгенерирован AI Marketing Intelligence Platform",
        meta_style,
    ))

    doc.build(elements)
    buf.seek(0)
    pdf_bytes = buf.read()
    logger.info("Generated PDF report: %d bytes", len(pdf_bytes))
    return pdf_bytes


def _escape_xml(text: str) -> str:
    """Escape special XML characters for ReportLab Paragraph."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("**", "")  # Strip markdown bold
        .replace("__", "")
    )
