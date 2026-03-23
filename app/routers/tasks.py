from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.models import Task, TaskCreate, TaskRead

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/", response_model=list[TaskRead])
async def list_tasks(
    project_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    query = select(Task)
    if project_id:
        query = query.where(Task.project_id == project_id)
    if status:
        query = query.where(Task.status == status)
    result = await session.execute(query)
    return result.scalars().all()


@router.post("/", response_model=TaskRead)
async def create_task(task: TaskCreate, session: AsyncSession = Depends(get_session)):
    db_task = Task.from_orm(task)
    session.add(db_task)
    await session.commit()
    await session.refresh(db_task)
    return db_task


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(task_id: int, session: AsyncSession = Depends(get_session)):
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(task_id: int, updates: TaskCreate, session: AsyncSession = Depends(get_session)):
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    for key, value in updates.dict(exclude_unset=True).items():
        setattr(task, key, value)
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


@router.delete("/{task_id}")
async def delete_task(task_id: int, session: AsyncSession = Depends(get_session)):
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    await session.delete(task)
    await session.commit()
    return {"ok": True}
