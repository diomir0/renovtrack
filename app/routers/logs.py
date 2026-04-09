import json
from telnetlib import AUTHENTICATION

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.database import get_session
from app.models import (
    DailyLog,
    DailyLogCreate,
    DailyLogExpenseLink,
    DailyLogRead,
    DailyLogTaskLink,
    Expense,
    Task,
)

router = APIRouter(prefix="/logs", tags=["daily-logs"])


@router.get("/", response_model=list[DailyLogRead])
async def list_logs(
    project_id: int | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    query = select(DailyLog)
    if project_id:
        query = query.where(DailyLog.project_id == project_id)
    query = query.order_by(DailyLog.date.desc())
    result = await session.execute(query)
    return result.scalars().all()


@router.post("/", response_model=DailyLogRead)
async def create_log(log: DailyLogCreate, session: AsyncSession = Depends(get_session)):
    db_log = DailyLog.model_validate(log)
    session.add(db_log)
    await session.commit()
    await session.refresh(db_log)
    return db_log


@router.get("/{log_id}", response_model=DailyLogRead)
async def get_log(log_id: int, session: AsyncSession = Depends(get_session)):
    log = await session.get(DailyLog, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")
    return log


@router.patch("/{log_id}", response_model=DailyLogRead)
async def update_log(
    log_id: int, updates: DailyLogCreate, session: AsyncSession = Depends(get_session)
):
    log = await session.get(DailyLog, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")
    for key, value in updates.model_dump(exclude_unset=True).items():
        setattr(log, key, value)
    await session.commit()
    await session.refresh(log)
    return log


@router.delete("/{log_id}")
async def delete_log(log_id: int, session: AsyncSession = Depends(get_session)):
    log = await session.get(DailyLog, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")
    await session.delete(log)
    await session.commit()
    return {"ok": True}
