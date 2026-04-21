import json

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from app.config import settings
from app.database import get_session
from app.models import DailyLog, Expense, InventoryItem, Project, Task

router = APIRouter(prefix="/assistant", tags=["assistant"])


class AssistantQuery(BaseModel):
    question: str
    project_id: int | None = None


async def build_context(project_id: int | None, session: AsyncSession) -> str:
    """Build a concise context string from the DB to feed the LLM."""
    lines = []

    if project_id:
        project = await session.get(Project, project_id)
        if project:
            lines.append(
                f"Project: {project.name} | Status: {project.status} | Budget: {project.budget_total}€"
            )

        # Task summary
        result = await session.execute(
            select(Task.status, func.count(Task.id).label("count"))
            .where(Task.project_id == project_id)
            .group_by(Task.status)
        )
        task_summary = {row.status: row.count for row in result.all()}
        lines.append(f"Tasks: {json.dumps(task_summary)}")

        # Expense summary
        result = await session.execute(
            select(func.sum(Expense.amount).label("total")).where(
                Expense.project_id == project_id
            )
        )
        total = result.scalar() or 0
        lines.append(f"Total spent: {total}€")

        # Last 3 logs
        result = await session.execute(
            select(DailyLog)
            .where(DailyLog.project_id == project_id)
            .order_by(DailyLog.date.desc())
            .limit(3)
        )
        logs = result.scalars().all()
        for log in logs:
            lines.append(f"Log {log.date}: {log.summary} ({log.time_spent_hours}h)")

        # Inventory pending
        result = await session.execute(
            select(InventoryItem).where(
                InventoryItem.project_id == project_id,
                InventoryItem.status == "pending",
            )
        )
        pending = result.scalars().all()
        if pending:
            lines.append(f"Pending items: {', '.join(i.name for i in pending)}")
    else:
        # Global summary
        result = await session.execute(select(Project))
        projects = result.scalars().all()
        lines.append(f"Projects: {', '.join(p.name for p in projects)}")

    return "\n".join(lines)


@router.post("/")
async def ask_assistant(
    query: AssistantQuery, session: AsyncSession = Depends(get_session)
):
    context = await build_context(query.project_id, session)

    system_prompt = (
        "You are a helpful assistant for a building renovation management app. "
        "Answer questions based on the following project data:\n\n"
        f"{context}\n\n"
        "Be concise and practical. If you don't have enough data to answer, say so."
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model": settings.ollama_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": query.question},
                    ],
                    "stream": False,
                },
            )
        data = response.json()
        answer = data["message"]["content"]
        return {"answer": answer, "context_used": context}

    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Could not connect to the LLM. Make sure you have acces to the internet and the API key is valid.",
        )
