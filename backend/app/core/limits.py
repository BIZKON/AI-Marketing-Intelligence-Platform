from dataclasses import dataclass

from app.models.subscription import PlanType


@dataclass(frozen=True)
class PlanLimits:
    competitors: int
    platforms: int
    agents: int
    tasks_per_month: int
    voice_per_week: int
    video_per_week: int


PLAN_LIMITS: dict[PlanType, PlanLimits] = {
    PlanType.MONITOR: PlanLimits(
        competitors=3,
        platforms=2,
        agents=1,
        tasks_per_month=0,
        voice_per_week=0,
        video_per_week=0,
    ),
    PlanType.CREATOR: PlanLimits(
        competitors=7,
        platforms=3,
        agents=3,
        tasks_per_month=20,
        voice_per_week=1,
        video_per_week=0,
    ),
    PlanType.AUTOPILOT: PlanLimits(
        competitors=15,
        platforms=99,
        agents=5,
        tasks_per_month=50,
        voice_per_week=3,
        video_per_week=1,
    ),
    PlanType.ENTERPRISE: PlanLimits(
        competitors=999,
        platforms=99,
        agents=99,
        tasks_per_month=9999,
        voice_per_week=7,
        video_per_week=3,
    ),
}

LIMIT_WARNING_THRESHOLD = 0.8  # Notify at 80% usage


def get_plan_limits(plan: PlanType) -> PlanLimits:
    return PLAN_LIMITS[plan]
