from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.database import get_session
from app.models import InventoryItem, InventoryItemCreate, InventoryItemRead

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("/", response_model=list[InventoryItemRead])
async def list_items(
    project_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    query = select(InventoryItem)
    if project_id:
        query = query.where(InventoryItem.project_id == project_id)
    if status:
        query = query.where(InventoryItem.status == status)
    result = await session.execute(query)
    return result.scalars().all()


@router.post("/", response_model=InventoryItemRead)
async def create_item(
    item: InventoryItemCreate, session: AsyncSession = Depends(get_session)
):
    db_item = InventoryItem.model_validate(item)
    session.add(db_item)
    await session.commit()
    await session.refresh(db_item)
    return db_item


@router.get("/{item_id}", response_model=InventoryItemRead)
async def get_item(item_id: int, session: AsyncSession = Depends(get_session)):
    item = await session.get(InventoryItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.patch("/{item_id}", response_model=InventoryItemRead)
async def update_item(
    item_id: int,
    updates: InventoryItemCreate,
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(InventoryItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    for key, value in updates.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


@router.delete("/{item_id}")
async def delete_item(item_id: int, session: AsyncSession = Depends(get_session)):
    item = await session.get(InventoryItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    await session.delete(item)
    await session.commit()
    return {"ok": True}
