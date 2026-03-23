from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.models import (
    DailyLog, DailyLogCreate, DailyLogRead,
    Task, Expense, DailyLogTaskLink, DailyLogExpenseLink,
)
import json

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
    db_log = DailyLog(
        project_id=log.project_id,
        zone_id=log.zone_id,
        date=log.date,
        author=log.author,
        summary=log.summary,
        time_spent_hours=log.time_spent_hours,
        people_involved=json.dumps(log.people),
    )
    session.add(db_log)
    await session.flush()  # get id before adding links

    # Link tasks
    for task_id in log.task_ids:
        task = await session.get(Task, task_id)
        if task:
            link = DailyLogTaskLink(log_id=db_log.id, task_id=task_id)
            session.add(link)
            # Mark task as done
            task.status = "done"
            session.add(task)

    # Link expenses
    for expense_id in log.expense_ids:
        expense = await session.get(Expense, expense_id)
        if expense:
            link = DailyLogExpenseLink(log_id=db_log.id, expense_id=expense_id)
            session.add(link)

    await session.commit()
    await session.refresh(db_log)
    return db_log


@router.get("/{log_id}", response_model=DailyLogRead)
async def get_log(log_id: int, session: AsyncSession = Depends(get_session)):
    log = await session.get(DailyLog, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")
    return log


@router.delete("/{log_id}")
async def delete_log(log_id: int, session: AsyncSession = Depends(get_session)):
    log = await session.get(DailyLog, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")
    await session.delete(log)
    await session.commit()
    return {"ok": True}
