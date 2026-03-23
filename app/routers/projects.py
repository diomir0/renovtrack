from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.database import get_session
from app.models import Project, ProjectCreate, ProjectRead

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("/", response_model=list[ProjectRead])
async def list_projects(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Project))
    return result.scalars().all()


@router.post("/", response_model=ProjectRead)
async def create_project(
    project: ProjectCreate, session: AsyncSession = Depends(get_session)
):
    db_project = Project.from_orm(project)
    session.add(db_project)
    await session.commit()
    await session.refresh(db_project)
    return db_project


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(project_id: int, session: AsyncSession = Depends(get_session)):
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: int,
    updates: ProjectCreate,
    session: AsyncSession = Depends(get_session),
):
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    for key, value in updates.dict(exclude_unset=True).items():
        setattr(project, key, value)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


@router.delete("/{project_id}")
async def delete_project(project_id: int, session: AsyncSession = Depends(get_session)):
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    await session.delete(project)
    await session.commit()
    return {"ok": True}
