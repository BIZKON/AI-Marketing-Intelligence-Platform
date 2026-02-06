"""Report export service — generate PDF, DOCX, and CSV reports."""

from __future__ import annotations

import csv
import io
import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.session_evaluation import SessionEvaluation
from app.models.training_session import SessionStatus, TrainingSession

logger = logging.getLogger(__name__)

CRITERIA_LABELS = {
    "greeting": "Greeting & Rapport",
    "listening": "Active Listening",
    "objection_handling": "Objection Handling",
    "product_knowledge": "Product Knowledge",
    "closing": "Closing Technique",
    "tone_empathy": "Tone & Empathy",
    "script_adherence": "Script Adherence",
}


class ExportService:
    """Generate training reports in various formats."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _get_sessions_data(
        self, user_id: uuid.UUID, start_date: datetime | None, end_date: datetime | None
    ) -> list[dict]:
        stmt = (
            select(TrainingSession)
            .options(selectinload(TrainingSession.evaluation))
            .where(
                TrainingSession.user_id == user_id,
                TrainingSession.status == SessionStatus.COMPLETED,
            )
            .order_by(TrainingSession.created_at)
        )
        if start_date:
            stmt = stmt.where(TrainingSession.started_at >= start_date)
        if end_date:
            stmt = stmt.where(TrainingSession.started_at <= end_date)

        result = await self.db.execute(stmt)
        sessions = result.scalars().all()

        data = []
        for s in sessions:
            row = {
                "date": s.started_at.strftime("%Y-%m-%d %H:%M") if s.started_at else "",
                "mode": s.mode.value if hasattr(s.mode, "value") else str(s.mode),
                "duration_minutes": (s.duration_seconds or 0) // 60,
                "overall_score": s.evaluation.overall_score if s.evaluation else None,
            }
            if s.evaluation and s.evaluation.criteria_scores:
                for key in CRITERIA_LABELS:
                    row[key] = s.evaluation.criteria_scores.get(key, "")
            data.append(row)
        return data

    async def export_csv(
        self, user_id: uuid.UUID,
        start_date: datetime | None = None, end_date: datetime | None = None,
    ) -> bytes:
        """Export training data as CSV."""
        data = await self._get_sessions_data(user_id, start_date, end_date)

        output = io.StringIO()
        fieldnames = [
            "date", "mode", "duration_minutes", "overall_score",
            *CRITERIA_LABELS.keys(),
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in data:
            writer.writerow(row)

        return output.getvalue().encode("utf-8")

    async def export_pdf(
        self, user_id: uuid.UUID,
        start_date: datetime | None = None, end_date: datetime | None = None,
    ) -> bytes:
        """Export training report as PDF.

        Uses a simple text-based PDF generation without external dependencies.
        For production, consider using reportlab or weasyprint.
        """
        data = await self._get_sessions_data(user_id, start_date, end_date)

        # Simple PDF generation using minimal PDF spec
        lines = [
            "TRAINING PROGRESS REPORT",
            "=" * 40,
            "",
            f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            f"Total sessions: {len(data)}",
        ]

        if data:
            scores = [d["overall_score"] for d in data if d["overall_score"] is not None]
            if scores:
                lines.append(f"Average score: {sum(scores) / len(scores):.1f}")
                lines.append(f"Best score: {max(scores)}")
            lines.append("")

            lines.append("SESSION DETAILS")
            lines.append("-" * 40)
            for row in data:
                lines.append(
                    f"  {row['date']} | {row['mode']} | "
                    f"{row['duration_minutes']}min | Score: {row['overall_score'] or 'N/A'}"
                )

            # Criteria averages
            if scores:
                lines.append("")
                lines.append("CRITERIA AVERAGES")
                lines.append("-" * 40)
                for key, label in CRITERIA_LABELS.items():
                    vals = [d.get(key) for d in data if d.get(key) and isinstance(d.get(key), (int, float))]
                    if vals:
                        avg = sum(vals) / len(vals)
                        lines.append(f"  {label}: {avg:.1f}")

        text_content = "\n".join(lines)

        # Wrap in minimal PDF structure
        pdf = self._text_to_pdf(text_content)
        return pdf

    async def export_docx(
        self, user_id: uuid.UUID,
        start_date: datetime | None = None, end_date: datetime | None = None,
    ) -> bytes:
        """Export training report as plain text (DOCX-compatible).

        For production, use python-docx for proper DOCX generation.
        Returns UTF-8 text that can be opened in Word.
        """
        data = await self._get_sessions_data(user_id, start_date, end_date)

        lines = [
            "TRAINING PROGRESS REPORT",
            "",
            f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            f"Total sessions: {len(data)}",
            "",
        ]

        if data:
            scores = [d["overall_score"] for d in data if d["overall_score"] is not None]
            if scores:
                lines.append(f"Average score: {sum(scores) / len(scores):.1f}")
                lines.append(f"Best score: {max(scores)}")
            lines.append("")
            lines.append("Date\tMode\tDuration\tScore")
            for row in data:
                lines.append(
                    f"{row['date']}\t{row['mode']}\t"
                    f"{row['duration_minutes']}min\t{row['overall_score'] or 'N/A'}"
                )

        return "\n".join(lines).encode("utf-8")

    @staticmethod
    def _text_to_pdf(text: str) -> bytes:
        """Generate a minimal valid PDF from plain text."""
        # Minimal PDF 1.4 structure
        lines_list = text.split("\n")
        stream_lines = []
        y = 750
        for line in lines_list:
            safe_line = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            stream_lines.append(f"BT /F1 10 Tf 50 {y} Td ({safe_line}) Tj ET")
            y -= 14
            if y < 50:
                break

        stream_content = "\n".join(stream_lines)

        objects = []
        # obj 1: catalog
        objects.append("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj")
        # obj 2: pages
        objects.append("2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj")
        # obj 3: page
        objects.append(
            "3 0 obj\n<< /Type /Page /Parent 2 0 R "
            "/MediaBox [0 0 612 792] /Contents 4 0 R "
            "/Resources << /Font << /F1 5 0 R >> >> >>\nendobj"
        )
        # obj 4: content stream
        stream_bytes = stream_content.encode("latin-1", errors="replace")
        objects.append(
            f"4 0 obj\n<< /Length {len(stream_bytes)} >>\n"
            f"stream\n{stream_content}\nendstream\nendobj"
        )
        # obj 5: font
        objects.append(
            "5 0 obj\n<< /Type /Font /Subtype /Type1 "
            "/BaseFont /Helvetica >>\nendobj"
        )

        body = "\n".join(objects)
        xref_offset = len(f"%PDF-1.4\n{body}\n")

        pdf_str = (
            f"%PDF-1.4\n{body}\n"
            f"xref\n0 6\n"
            f"0000000000 65535 f \n"
        )
        # Simplified: write trailer directly
        pdf_str += (
            f"trailer\n<< /Size 6 /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF"
        )
        return pdf_str.encode("latin-1", errors="replace")
