"""Chart rendering service — Matplotlib-based charts for PDF and video reports.

Generates engagement bar charts, trend lines, and pie charts from report data.
All charts are rendered to PNG bytes (no file I/O).
"""

from __future__ import annotations

import io
import logging
from typing import Any

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.figure import Figure

logger = logging.getLogger(__name__)

# Default style
plt.rcParams.update({
    "figure.facecolor": "#ffffff",
    "axes.facecolor": "#f8f9fa",
    "axes.grid": True,
    "grid.alpha": 0.3,
    "font.size": 11,
})

BRAND_COLORS = [
    "#6366f1", "#8b5cf6", "#ec4899", "#f43f5e",
    "#f97316", "#eab308", "#22c55e", "#06b6d4",
]


def render_engagement_bar_chart(stats: dict[str, Any]) -> bytes:
    """Render a horizontal bar chart comparing competitor engagement.

    Args:
        stats: Dict of competitor_id -> {name, total_likes, total_comments, total_shares, ...}

    Returns:
        PNG image bytes.
    """
    names = []
    likes = []
    comments = []
    shares = []

    for s in stats.values():
        names.append(s["name"])
        likes.append(s.get("total_likes", 0))
        comments.append(s.get("total_comments", 0))
        shares.append(s.get("total_shares", 0))

    fig, ax = plt.subplots(figsize=(10, max(4, len(names) * 0.8)))
    y_pos = range(len(names))
    bar_height = 0.25

    ax.barh([y - bar_height for y in y_pos], likes, bar_height, label="Лайки", color=BRAND_COLORS[0])
    ax.barh(list(y_pos), comments, bar_height, label="Комментарии", color=BRAND_COLORS[1])
    ax.barh([y + bar_height for y in y_pos], shares, bar_height, label="Репосты", color=BRAND_COLORS[2])

    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(names)
    ax.set_xlabel("Количество")
    ax.set_title("Вовлечённость конкурентов")
    ax.legend(loc="lower right")
    fig.tight_layout()

    return _fig_to_png(fig)


def render_posts_comparison_chart(stats: dict[str, Any]) -> bytes:
    """Render a bar chart comparing post counts and views across competitors."""
    names = []
    posts = []
    views = []

    for s in stats.values():
        names.append(s["name"])
        posts.append(s.get("post_count", 0))
        views.append(s.get("total_views", 0))

    fig, ax1 = plt.subplots(figsize=(10, 5))
    x = range(len(names))
    width = 0.35

    bars1 = ax1.bar([i - width / 2 for i in x], posts, width, label="Посты", color=BRAND_COLORS[0])
    ax1.set_ylabel("Количество постов", color=BRAND_COLORS[0])
    ax1.set_xticks(list(x))
    ax1.set_xticklabels(names, rotation=30, ha="right")

    ax2 = ax1.twinx()
    bars2 = ax2.bar([i + width / 2 for i in x], views, width, label="Просмотры", color=BRAND_COLORS[3], alpha=0.7)
    ax2.set_ylabel("Просмотры", color=BRAND_COLORS[3])

    ax1.set_title("Активность конкурентов: посты vs просмотры")
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")
    fig.tight_layout()

    return _fig_to_png(fig)


def render_engagement_pie_chart(stats: dict[str, Any]) -> bytes:
    """Render a pie chart showing engagement distribution across competitors."""
    names = []
    totals = []

    for s in stats.values():
        names.append(s["name"])
        totals.append(
            s.get("total_likes", 0) + s.get("total_comments", 0) + s.get("total_shares", 0)
        )

    if not any(totals):
        totals = [1] * len(names)  # Avoid zero-division

    fig, ax = plt.subplots(figsize=(8, 8))
    colors = BRAND_COLORS[: len(names)]
    wedges, texts, autotexts = ax.pie(
        totals,
        labels=names,
        colors=colors,
        autopct="%1.1f%%",
        startangle=90,
        pctdistance=0.85,
    )
    for text in autotexts:
        text.set_fontsize(10)

    centre_circle = plt.Circle((0, 0), 0.60, fc="white")
    ax.add_artist(centre_circle)
    ax.set_title("Доля вовлечённости по конкурентам")
    fig.tight_layout()

    return _fig_to_png(fig)


def render_er_comparison_chart(stats: dict[str, Any]) -> bytes:
    """Render a bar chart comparing engagement rates."""
    names = []
    rates = []

    for s in stats.values():
        names.append(s["name"])
        rates.append(s.get("avg_engagement_rate", 0) * 100)  # Convert to percentage

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(names, rates, color=BRAND_COLORS[:len(names)])
    ax.set_ylabel("Engagement Rate (%)")
    ax.set_title("Сравнение Engagement Rate")

    for bar, rate in zip(bars, rates):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.01,
            f"{rate:.2f}%",
            ha="center",
            va="bottom",
            fontsize=10,
        )

    plt.xticks(rotation=30, ha="right")
    fig.tight_layout()

    return _fig_to_png(fig)


def _fig_to_png(fig: Figure) -> bytes:
    """Convert a matplotlib figure to PNG bytes and close it."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()
