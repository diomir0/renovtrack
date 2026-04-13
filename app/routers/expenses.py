from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from app.database import get_session
from app.models import Expense, ExpenseCreate, ExpenseRead

router = APIRouter(prefix="/expenses", tags=["expenses"])


@router.get("/", response_model=list[ExpenseRead])
async def list_expenses(
    project_id: int | None = Query(default=None),
    zone_id: int | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    query = select(Expense)
    if project_id:
        query = query.where(Expense.project_id == project_id)
    if zone_id:
        query = query.where(Expense.zone_id == zone_id)
    result = await session.execute(query)
    return result.scalars().all()


@router.get("/summary")
async def expense_summary(
    project_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Total spent per category for a project."""
    result = await session.execute(
        select(Expense.category, func.sum(Expense.amount).label("total"))
        .where(Expense.project_id == project_id)
        .group_by(Expense.category)
    )
    rows = result.all()
    return {row.category: row.total for row in rows}


@router.post("/", response_model=ExpenseRead)
async def create_expense(
    expense: ExpenseCreate, session: AsyncSession = Depends(get_session)
):
    db_expense = Expense.model_validate(expense)
    session.add(db_expense)
    await session.commit()
    await session.refresh(db_expense)
    return db_expense


@router.get("/{expense_id}", response_model=ExpenseRead)
async def get_expense(expense_id: int, session: AsyncSession = Depends(get_session)):
    expense = await session.get(Expense, expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    return expense


@router.patch("/{expense_id}", response_model=ExpenseRead)
async def update_expense(
    expense_id: int,
    updates: ExpenseCreate,
    session: AsyncSession = Depends(get_session),
):
    expense = await session.get(Expense, expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Task not found")
    for key, value in updates.model_dump(exclude_unset=True).items():
        setattr(expense, key, value)
    session.add(expense)
    await session.commit()
    await session.refresh(expense)
    return expense


@router.delete("/{expense_id}")
async def delete_expense(expense_id: int, session: AsyncSession = Depends(get_session)):
    expense = await session.get(Expense, expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    await session.delete(expense)
    await session.commit()
    return {"ok": True}
