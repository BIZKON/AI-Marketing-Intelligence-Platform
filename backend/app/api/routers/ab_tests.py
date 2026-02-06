"""A/B test script routes — compare script variants."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.ab_test import ABTest
from app.models.ab_test_result import ABTestResult
from app.models.user import User

router = APIRouter()


class CreateABTestRequest(BaseModel):
    name: str
    scenario_id: str | None = None
    variant_a: str
    variant_b: str


class RecordResultRequest(BaseModel):
    variant: str  # "a" or "b"
    score: int


@router.post("/")
async def create_ab_test(
    data: CreateABTestRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a new A/B test comparing two script variants."""
    test = ABTest(
        user_id=user.id,
        name=data.name,
        scenario_id=uuid.UUID(data.scenario_id) if data.scenario_id else None,
        variant_a=data.variant_a,
        variant_b=data.variant_b,
    )
    db.add(test)
    await db.commit()
    await db.refresh(test)
    return {
        "id": str(test.id),
        "name": test.name,
        "variant_a": test.variant_a,
        "variant_b": test.variant_b,
        "created_at": test.created_at.isoformat(),
    }


@router.get("/")
async def list_ab_tests(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List user's A/B tests."""
    result = await db.execute(
        select(ABTest).where(ABTest.user_id == user.id).order_by(ABTest.created_at.desc())
    )
    tests = result.scalars().all()
    return [
        {
            "id": str(t.id),
            "name": t.name,
            "variant_a": t.variant_a,
            "variant_b": t.variant_b,
            "is_active": t.is_active,
            "created_at": t.created_at.isoformat(),
        }
        for t in tests
    ]


@router.get("/{test_id}")
async def get_ab_test(
    test_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get A/B test details with results summary."""
    result = await db.execute(
        select(ABTest).where(ABTest.id == uuid.UUID(test_id), ABTest.user_id == user.id)
    )
    test = result.scalar_one_or_none()
    if not test:
        raise HTTPException(status_code=404, detail="A/B test not found")

    # Get results per variant
    for variant in ("a", "b"):
        res = await db.execute(
            select(
                func.count(ABTestResult.id),
                func.avg(ABTestResult.score),
            ).where(
                ABTestResult.ab_test_id == test.id,
                ABTestResult.variant == variant,
            )
        )
        row = res.one()
        setattr(test, f"_count_{variant}", row[0])
        setattr(test, f"_avg_{variant}", float(row[1]) if row[1] else None)

    return {
        "id": str(test.id),
        "name": test.name,
        "variant_a": test.variant_a,
        "variant_b": test.variant_b,
        "is_active": test.is_active,
        "results": {
            "a": {"count": test._count_a, "avg_score": test._avg_a},
            "b": {"count": test._count_b, "avg_score": test._avg_b},
        },
    }


@router.post("/{test_id}/result")
async def record_result(
    test_id: str,
    data: RecordResultRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Record a test result for a variant."""
    if data.variant not in ("a", "b"):
        raise HTTPException(status_code=400, detail="Variant must be 'a' or 'b'")

    result_entry = ABTestResult(
        ab_test_id=uuid.UUID(test_id),
        user_id=user.id,
        variant=data.variant,
        score=data.score,
    )
    db.add(result_entry)
    await db.commit()
    return {"status": "recorded"}
