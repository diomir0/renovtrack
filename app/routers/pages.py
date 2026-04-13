import json
import json as _json
from datetime import date, timedelta
from syslog import LOG_PID
from typing import Optional

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import func, select

from app.database import get_session
from app.models import (
    Building,
    DailyLog,
    DailyLogExpenseLink,
    DailyLogTaskLink,
    Expense,
    InventoryItem,
    Project,
    ProjectWithStats,
    Task,
    Zone,
)

router = APIRouter(default_response_class=HTMLResponse)
templates = Jinja2Templates(directory="app/templates")


# ── Dashboard ─────────────────────────────────────────────────────────────────


@router.get("/")
async def dashboard(request: Request, session: AsyncSession = Depends(get_session)):

    projects_result = await session.execute(select(Project))
    raw_projects = projects_result.scalars().all()

    enriched = []
    for p in raw_projects:
        spent_r = await session.execute(
            select(func.sum(Expense.amount)).where(Expense.project_id == p.id)
        )
        enriched.append(
            ProjectWithStats(
                project=p,
                spent=spent_r.scalar() or 0,
            )
        )

    for p in enriched:
        spent_r = await session.execute(
            select(func.sum(Expense.amount)).where(Expense.project_id == p.project.id)
        )
        p.spent = spent_r.scalar() or 0.0

    # Upcoming tasks
    upcoming_tasks_result = await session.execute(
        select(Task).where(Task.status != "done").order_by(Task.due_date)
    )
    upcoming_tasks = upcoming_tasks_result.scalars().all()

    # Stats
    active = sum(1 for p in raw_projects if p.status == "active")

    tasks_result = await session.execute(
        select(func.count(Task.id)).where(Task.status != "done")
    )
    open_tasks = tasks_result.scalar() or 0

    spent_result = await session.execute(select(func.sum(Expense.amount)))
    total_spent = spent_result.scalar() or 0

    # Recent logs
    logs_result = await session.execute(
        select(DailyLog).order_by(DailyLog.date.desc()).limit(5)
    )
    recent_logs = logs_result.scalars().all()

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "projects": enriched,
            "upcoming_tasks": upcoming_tasks,
            "recent_logs": recent_logs,
            "stats": {
                "active_projects": active,
                "open_tasks": open_tasks,
                "total_spent": total_spent,
            },
        },
    )


# ── New building ─────────────────────────────────────────────────────────────


@router.get("/buildings/new")
async def new_building_page(request: Request):
    return templates.TemplateResponse("building_new.html", {"request": request})


@router.post("/buildings/new")
async def create_building_form(
    name: str = Form(...),
    address: str = Form(""),
    description: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    b = Building(name=name, address=address or None, description=description or None)
    session.add(b)
    await session.commit()
    return RedirectResponse("/projects/new", status_code=303)


# ── Project page --------------------------------------------------------------


@router.get("/projects")
async def projects_list(request: Request, session: AsyncSession = Depends(get_session)):
    projects_result = await session.execute(
        select(Project).options(selectinload(Project.building))
    )
    raw_projects = projects_result.scalars().all()

    enriched = []
    for p in raw_projects:
        spent_r = await session.execute(
            select(func.sum(Expense.amount)).where(Expense.project_id == p.id)
        )
        enriched.append(
            ProjectWithStats(
                project=p,
                spent=spent_r.scalar() or 0,
            )
        )

    for p in enriched:
        spent_r = await session.execute(
            select(func.sum(Expense.amount)).where(Expense.project_id == p.project.id)
        )
        p.spent = spent_r.scalar() or 0.0

        counts_r = await session.execute(
            select(Task.status, func.count(Task.id))
            .where(Task.project_id == p.project.id)
            .group_by(Task.status)
        )
        counts = dict(counts_r.all())
        p.task_done = counts.get("done", 0)
        p.task_total = sum(counts.values())

    return templates.TemplateResponse(
        "projects.html",
        {
            "request": request,
            "projects": enriched,
        },
    )


# ── New project ───────────────────────────────────────────────────────────────


@router.get("/projects/new")
async def new_project_page(
    request: Request, session: AsyncSession = Depends(get_session)
):
    result = await session.execute(select(Building))
    buildings = result.scalars().all()
    return templates.TemplateResponse(
        "project_new.html",
        {
            "request": request,
            "buildings": buildings,
        },
    )


@router.post("/projects/new")
async def create_project_form(
    name: str = Form(...),
    building_id: int = Form(...),
    description: str = Form(""),
    status: str = Form("planning"),
    budget_total: float = Form(...),
    start_date: Optional[str] = Form(None),
    estimated_end_date: Optional[str] = Form(None),
    session: AsyncSession = Depends(get_session),
):
    project = Project(
        name=name,
        building_id=building_id,
        description=description or None,
        status=status,
        budget_total=budget_total,
        start_date=date.fromisoformat(start_date) if start_date else None,
        estimated_end_date=date.fromisoformat(estimated_end_date)
        if estimated_end_date
        else None,
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return RedirectResponse(f"/projects/{project.id}", status_code=303)


# ── Project detail ────────────────────────────────────────────────────────────


@router.get("/projects/{project_id}")
async def project_detail(
    project_id: int, request: Request, session: AsyncSession = Depends(get_session)
):
    project = await session.get(Project, project_id)
    if not project:
        return RedirectResponse("/")

    tasks_r = await session.execute(select(Task).where(Task.project_id == project_id))
    tasks = tasks_r.scalars().all()

    inv_r = await session.execute(
        select(InventoryItem).where(InventoryItem.project_id == project_id)
    )
    inventory = inv_r.scalars().all()

    exp_r = await session.execute(
        select(Expense)
        .where(Expense.project_id == project_id)
        .order_by(Expense.date.desc())
    )
    expenses = exp_r.scalars().all()

    logs_r = await session.execute(
        select(DailyLog)
        .where(DailyLog.project_id == project_id)
        .order_by(DailyLog.date.desc())
    )
    logs = logs_r.scalars().all()

    task_counts = {}
    for t in tasks:
        task_counts[t.status] = task_counts.get(t.status, 0) + 1

    total_spent = sum(e.amount for e in expenses)
    total_hours = sum(l.time_spent_hours for l in logs)

    return templates.TemplateResponse(
        "project_detail.html",
        {
            "request": request,
            "project": project,
            "tasks": tasks,
            "inventory": inventory,
            "expenses": expenses,
            "logs": logs,
            "task_counts": task_counts,
            "task_total": len(tasks),
            "total_spent": total_spent,
            "total_hours": total_hours,
        },
    )


@router.get("/projects/{project_id}/edit")
async def project_edit_modal(
    project_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    project = await session.get(Project, project_id)
    buildings_r = await session.execute(select(Building))
    buildings = buildings_r.scalars().all()

    return templates.TemplateResponse(
        "partials/project_modal.html",
        {
            "request": request,
            "project_id": project.id,
            "project": project,
            "buildings": buildings,
        },
    )


@router.post("/projects/{project_id}/edit")
async def project_update(
    project_id: int,
    name: str = Form(...),
    building_id: int = Form(...),
    description: Optional[str] = Form(...),
    status: str = Form(...),
    budget_total: float = Form(...),
    start_date: Optional[date] = Form(...),
    estimated_end_date: Optional[date] = Form(...),
    session: AsyncSession = Depends(get_session),
):
    project = await session.get(Project, project_id)
    building = await session.get(Building, building_id)
    if project and building:
        project.name = name
        project.building_id = building_id
        project.building = building
        project.description = description if description else None
        project.status = status
        project.budget_total = budget_total
        project.start_date = start_date if start_date else None
        project.estimated_end_date = estimated_end_date if estimated_end_date else None
        await session.commit()
    return RedirectResponse(f"/projects/{project_id}", status_code=303)


@router.delete("/projects/{project_id}")
async def project_delete(project_id: int, session: AsyncSession = Depends(get_session)):
    project = await session.get(Project, project_id)

    expenses_r = await session.execute(
        select(Expense).where(Expense.project_id == project_id)
    )
    expenses = expenses_r.scalars().all()

    tasks_r = await session.execute(select(Task).where(Task.project_id == project_id))
    tasks = tasks_r.scalars().all()

    logs_r = await session.execute(
        select(DailyLog).where(DailyLog.project_id == project_id)
    )
    logs = logs_r.scalars().all()

    for expense in expenses:
        await session.delete(expense)
        await session.commit()

    for task in tasks:
        await session.delete(task)
        await session.commit()

    for log in logs:
        await session.delete(log)
        await session.commit()

    if project:
        await session.delete(project)
        await session.commit()
    return HTMLResponse("")


# ── HTMX modal partials ───────────────────────────────────────────────────────


@router.get("/projects/{project_id}/tasks/new")
async def task_modal(
    project_id: int, request: Request, session: AsyncSession = Depends(get_session)
):
    return templates.TemplateResponse(
        "partials/task_modal.html",
        {
            "request": request,
            "project_id": project_id,
            "task": None,
        },
    )


@router.post("/projects/{project_id}/tasks")
async def create_task_form(
    project_id: int,
    title: str = Form(...),
    description: Optional[str] = Form(...),
    status: str = Form("todo"),
    priority: str = Form("normal"),
    assigned_to: str = Form(""),
    due_date: Optional[str] = Form(None),
    session: AsyncSession = Depends(get_session),
):
    task = Task(
        project_id=project_id,
        title=title,
        description=description,
        status=status,
        priority=priority,
        assigned_to=assigned_to,
        due_date=date.fromisoformat(due_date) if due_date else None,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return RedirectResponse(f"/projects/{project_id}", status_code=303)

    # Return updated tasks list partial
    # tasks_r = await session.execute(select(Task).where(Task.project_id == project_id))
    # tasks = tasks_r.scalars().all()
    # return templates.TemplateResponse(
    #     "partials/tasks_table_body.html",
    #     {
    #         "request": request,
    #         "tasks": tasks,
    #     },
    # )


@router.get("/tasks/{task_id}/edit")
async def task_edit_modal(
    task_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    task = await session.get(Task, task_id)
    return templates.TemplateResponse(
        "partials/task_modal.html",
        {"request": request, "project_id": task.project_id, "task": task},
    )


@router.post("/tasks/{task_id}/edit")
async def task_update(
    task_id: int,
    title: str = Form(...),
    description: Optional[str] = Form(...),
    status: str = Form(...),
    priority: str = Form(...),
    assigned_to: Optional[str] = Form(...),
    due_date: Optional[date] = Form(None),
    session: AsyncSession = Depends(get_session),
):
    task = await session.get(Task, task_id)
    if task:
        task.title = title
        task.description = description if description else None
        task.status = status
        task.priority = priority
        task.assigned_to = assigned_to if assigned_to else None
        task.due_date = due_date if due_date else None
        await session.commit()
    return RedirectResponse(f"/projects/{task.project_id}", status_code=303)


@router.get("/projects/{project_id}/expenses/new")
async def expense_modal(
    project_id: int, request: Request, session: AsyncSession = Depends(get_session)
):
    zones_r = await session.execute(select(Zone).where(Zone.project_id == project_id))
    zones = zones_r.scalars().all()
    return templates.TemplateResponse(
        "partials/expense_modal.html",
        {
            "request": request,
            "project_id": project_id,
            "zones": zones,
            "expense": None,
            "today": date.today().isoformat(),
        },
    )


@router.post("/projects/{project_id}/expenses")
async def create_expense_form(
    project_id: int,
    label: str = Form(...),
    amount: float = Form(...),
    date_val: date = Form(..., alias="date"),
    category: str = Form("other"),
    zone_id: Optional[int] = Form(None),
    paid_by: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    expense = Expense(
        project_id=project_id,
        label=label,
        amount=amount,
        date=date_val,
        category=category,
        zone_id=zone_id,
        paid_by=paid_by,
    )
    session.add(expense)
    await session.commit()
    await session.refresh(expense)
    return RedirectResponse(f"/projects/{project_id}", status_code=303)


@router.get("/expenses/{expense_id}/edit")
async def expense_edit_modal(
    expense_id: int, request: Request, session: AsyncSession = Depends(get_session)
):
    expense = await session.get(Expense, expense_id)
    return templates.TemplateResponse(
        "partials/expense_modal.html",
        {
            "request": request,
            "project_id": expense.project_id,
            "expense": expense,
        },
    )


@router.post("/expenses/{expense_id}/edit")
async def expense_update(
    expense_id: int,
    label: str = Form(...),
    amount: float = Form(...),
    category: str = Form(...),
    paid_by: str = Form(...),
    receipt_url: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    zone_id: Optional[int] = Form(None),
    linked_item_id: Optional[int] = Form(None),
    session: AsyncSession = Depends(get_session),
):
    expense = await session.get(Expense, expense_id)
    if expense:
        expense.label = label
        expense.amount = amount
        expense.category = category
        expense.paid_by = paid_by
        expense.receipt_url = receipt_url
        expense.notes = notes
        expense.zone_id = zone_id
        expense.linked_item_id = linked_item_id
        await session.commit()
    return RedirectResponse(f"/projects/{expense.project_id}", status_code=303)


@router.get("/projects/{project_id}/inventory/new")
async def inventory_modal(
    project_id: int, request: Request, session: AsyncSession = Depends(get_session)
):
    projects_r = await session.execute(select(Project).where(Project.id == project_id))
    projects = projects_r.scalars().all()

    tasks_r = await session.execute(select(Task).where(Task.project_id == project_id))
    tasks = tasks_r.scalars().all()

    zones_r = await session.execute(select(Zone).where(Zone.project_id == project_id))
    zones = zones_r.scalars().all()
    return templates.TemplateResponse(
        "partials/inventory_modal.html",
        {
            "request": request,
            "projects": projects,
            "default_project_id": project_id,
            "tasks": tasks,
            "zones": zones,
            "item": None,
        },
    )


@router.post("/projects/{project_id}/inventory")
async def create_inventory_form(
    project_id: int,
    name: str = Form(...),
    category: str = Form("material"),
    status: str = Form("pending"),
    quantity: float = Form(1),
    unit: str = Form("unit"),
    supplier: str = Form(""),
    zone_id: Optional[int] = Form(None),
    bNewExpense: bool = Form(False),
    session: AsyncSession = Depends(get_session),
):
    item = InventoryItem(
        project_id=project_id,
        name=name,
        category=category,
        status=status,
        quantity=quantity,
        unit=unit,
        supplier=supplier or None,
        zone_id=zone_id or None,
    )

    if bNewExpense:
        exp_category = None
        if category in ["tool", "appliance"]:
            exp_category = "equipment"
        elif category == "material":
            exp_category = "material"
        else:
            exp_category = "other"

        exp_date = item.created_at if item.created_at else date.today()
        expense = Expense(
            label=name,
            amount=quantity,
            category=exp_category,
            date=exp_date,
            project_id=project_id,
            linked_item_id=item.id,
        )
        session.add(expense)

    session.add(item)
    await session.commit()
    return RedirectResponse(f"/projects/{project_id}", status_code=303)


@router.get("/logs/new")
async def log_modal(
    project_id: int, request: Request, session: AsyncSession = Depends(get_session)
):
    projects_r = await session.execute(select(Project))
    # .where(Project.id == project_id)
    projects = projects_r.scalars().all()

    zones_r = await session.execute(select(Zone).where(Zone.project_id == project_id))
    zones = zones_r.scalars().all()

    tasks_r = await session.execute(
        select(Task).where(Task.project_id == project_id, Task.status != "done")
    )
    tasks = tasks_r.scalars().all()

    return templates.TemplateResponse(
        "partials/log_modal.html",
        {
            "request": request,
            "projects": projects,
            "project": project_id,
            "default_project_id": project_id,
            "zones": zones,
            "tasks": tasks,
            "pending_expenses": [],
            "today": date.today().isoformat(),
        },
    )


@router.post("/logs/new")
async def create_log_form(
    request: Request,
    project_id: int = Form(...),
    date_val: date = Form(..., alias="date"),
    author: str = Form(...),
    summary: Optional[str] = Form(""),
    time_spent_hours: float = Form(...),
    zone_id: Optional[int] = Form(None),
    people: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    form_data = await request.form()
    task_ids = [int(v) for v in form_data.getlist("task_ids")]
    expense_ids = [int(v) for v in form_data.getlist("expense_ids")]
    people_list = [p.strip() for p in people.split(",") if p.strip()]

    log = DailyLog(
        project_id=project_id,
        zone_id=zone_id,
        date=date_val,
        author=author,
        summary=summary,
        time_spent_hours=time_spent_hours,
        people_involved=json.dumps(people_list),
    )

    session.add(log)
    await session.flush()

    for task_id in task_ids:
        task = await session.get(Task, task_id)
        if task:
            task.status = "done"
            session.add(task)
            session.add(DailyLogTaskLink(log_id=log.id, task_id=task_id))

    for expense_id in expense_ids:
        session.add(DailyLogExpenseLink(log_id=log.id, expense_id=expense_id))

    await session.commit()
    return RedirectResponse(f"/projects/{project_id}", status_code=303)


# ── Calendar ─────────────────────────────────────────────────────────────────


@router.get("/calendar")
async def calendar(
    request: Request,
    view: str = Query(default="month"),
    cursor: Optional[str] = Query(default=None),
    project_id: Optional[int] = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    today = date.today()
    cursor_date = date.fromisoformat(cursor) if cursor else today

    events = []

    # Tasks by due date
    q = select(Task).where(Task.due_date != None)
    if project_id:
        q = q.where(Task.project_id == project_id)
    tasks_r = await session.execute(q)
    for t in tasks_r.scalars().all():
        events.append(
            {
                "date": t.due_date.isoformat(),
                "type": "task",
                "title": t.title,
                "meta": f"{t.status} · {t.priority}",
            }
        )

    # Daily logs
    q = select(DailyLog)
    if project_id:
        q = q.where(DailyLog.project_id == project_id)
    logs_r = await session.execute(q)
    for l in logs_r.scalars().all():
        people = _json.loads(l.people_involved) if l.people_involved else []
        events.append(
            {
                "date": l.date.isoformat(),
                "type": "log",
                "title": l.summary or f"Log by {l.author}",
                "meta": f"{l.time_spent_hours}h · {', '.join(people)}"
                if people
                else f"{l.time_spent_hours}h",
            }
        )

    # Expenses
    q = select(Expense)
    if project_id:
        q = q.where(Expense.project_id == project_id)
    exp_r = await session.execute(q)
    for e in exp_r.scalars().all():
        events.append(
            {
                "date": e.date.isoformat(),
                "type": "expense",
                "title": e.label,
                "meta": f"{e.amount:.2f} € · {e.category}",
            }
        )

    # Inventory deliveries (items with status=ordered or delivered, use created_at date)
    q = select(InventoryItem).where(InventoryItem.status.in_(["ordered", "delivered"]))
    if project_id:
        q = q.where(InventoryItem.project_id == project_id)
    inv_r = await session.execute(q)
    for item in inv_r.scalars().all():
        events.append(
            {
                "date": item.created_at.date().isoformat(),
                "type": "delivery",
                "title": item.name,
                "meta": f"{item.status} · {item.quantity} {item.unit}",
            }
        )

    return templates.TemplateResponse(
        "calendar.html",
        {
            "request": request,
            "view": view,
            "cursor_iso": cursor_date.isoformat(),
            "events_json": _json.dumps(events),
        },
    )


# ── Assistant HTMX endpoint ───────────────────────────────────────────────────


@router.post("/assistant/query")
async def assistant_query_htmx(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    form = await request.form()
    question = form.get("assistant-input", "")
    project_id = int(form.get("project_id", 0))

    import httpx

    from app.config import settings
    from app.routers.assistant import build_context

    context = await build_context(project_id, session)

    system_prompt = (
        "You are a concise assistant for a building renovation management app. "
        f"Current project data:\n{context}\n\n"
        "Answer in 1-3 sentences. Be direct and practical."
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model": settings.ollama_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": question},
                    ],
                    "stream": False,
                },
            )
        data = response.json()
        answer = data["message"]["content"]
        return HTMLResponse(f'<p style="color:var(--text)">{answer}</p>')
    except Exception:
        return HTMLResponse(
            '<p style="color:var(--muted)">Could not reach local LLM. Is Ollama running?</p>'
        )


# ── Inventory page ────────────────────────────────────────────────────────────


@router.get("/inventory")
async def inventory_page(
    request: Request,
    project_id: Optional[int] = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    q = select(InventoryItem)
    if project_id:
        q = q.where(InventoryItem.project_id == project_id)
    items_r = await session.execute(
        q.order_by(
            InventoryItem.acquisition_date.desc().nullslast(), InventoryItem.name
        )
    )
    items = items_r.scalars().all()

    # Attach related project/task objects manually (no eager loading)
    proj_r = await session.execute(select(Project))
    proj_map = {p.id: p for p in proj_r.scalars().all()}

    task_r = await session.execute(select(Task))
    task_map = {t.id: t for t in task_r.scalars().all()}

    for item in items:
        item.project = proj_map.get(item.project_id)
        item.linked_task = (
            task_map.get(item.linked_task_id) if item.linked_task_id else None
        )

    return templates.TemplateResponse(
        "inventory.html",
        {
            "request": request,
            "items": items,
            "projects": list(proj_map.values()),
            "selected_project_id": project_id,
        },
    )


@router.get("/inventory/new")
async def inventory_new_modal(
    request: Request,
    project_id: Optional[int] = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    proj_r = await session.execute(select(Project))
    projects = proj_r.scalars().all()

    task_r = await session.execute(select(Task))
    tasks = task_r.scalars().all()

    return templates.TemplateResponse(
        "partials/inventory_modal.html",
        {
            "request": request,
            "item": None,
            "projects": projects,
            "tasks": tasks,
            "default_project_id": project_id,
        },
    )


@router.post("/inventory/new")
async def inventory_create(
    request: Request,
    name: str = Form(...),
    project_id: Optional[int] = Form(None),
    category: str = Form("material"),
    status: str = Form("pending"),
    quantity: float = Form(1),
    unit: str = Form("unit"),
    unit_price: float = Form(0),
    acquisition_date: Optional[str] = Form(None),
    supplier: str = Form(""),
    storage: str = Form(""),
    linked_task_id: Optional[int] = Form(None),
    notes: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    item = InventoryItem(
        name=name,
        project_id=project_id or None,
        category=category,
        status=status,
        quantity=quantity,
        unit=unit,
        unit_price=unit_price,
        acquisition_date=date.fromisoformat(acquisition_date)
        if acquisition_date
        else None,
        supplier=supplier or None,
        storage=storage or None,
        linked_task_id=linked_task_id or None,
        notes=notes or None,
    )

    if item.unit_price != 0.0 and project_id:
        exp_category = None
        if category in ["tool", "appliance"]:
            exp_category = "equipment"
        elif category == "material":
            exp_category = "material"
        else:
            exp_category = "other"

        exp_date = item.acquisition_date if item.acquisition_date else date.today()

        expense = Expense(
            label=name,
            amount=item.quantity * item.unit_price,
            category=exp_category,
            date=exp_date,
            project_id=project_id,
        )
        session.add(expense)

    session.add(item)
    await session.commit()
    return RedirectResponse("/inventory", status_code=303)


@router.get("/inventory/{item_id}/edit")
async def inventory_edit_modal(
    item_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(InventoryItem, item_id)
    task_r = await session.execute(select(Task))
    tasks = task_r.scalars().all()
    return templates.TemplateResponse(
        "partials/inventory_modal.html",
        {
            "request": request,
            "item": item,
            "projects": [],
            "tasks": tasks,
            "default_project_id": None,
        },
    )


@router.post("/inventory/{item_id}/edit")
async def inventory_update(
    item_id: int,
    name: str = Form(...),
    category: str = Form("material"),
    status: str = Form("pending"),
    quantity: float = Form(1),
    unit: str = Form("unit"),
    unit_price: float = Form(0),
    acquisition_date: Optional[str] = Form(None),
    supplier: str = Form(""),
    storage: str = Form(""),
    linked_task_id: Optional[int] = Form(None),
    notes: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(InventoryItem, item_id)
    expenses_r = await session.execute(
        select(Expense).filter_by(linked_item_id=item_id)
    )
    expenses = expenses_r.scalars().all()
    if expenses:
        for expense in expenses:
            expense.amount = quantity * unit_price
            if category in ["tools", "appliance"]:
                expense.category = "equipment"
            elif category == "material":
                expense.category = "material"
            else:
                expense.category = "other"
            session.add(expense)

    if item:
        item.name = name
        item.category = category
        item.status = status
        item.quantity = quantity
        item.unit = unit
        item.unit_price = unit_price
        item.acquisition_date = (
            date.fromisoformat(acquisition_date) if acquisition_date else None
        )
        item.supplier = supplier or None
        item.storage = storage or None
        item.linked_task_id = linked_task_id or None
        item.notes = notes or None
        session.add(item)
        await session.commit()
    return RedirectResponse("/inventory", status_code=303)


@router.delete("/inventory/{item_id}")
async def inventory_delete(item_id: int, session: AsyncSession = Depends(get_session)):
    item = await session.get(InventoryItem, item_id)

    expenses_r = await session.execute(
        select(Expense).filter_by(linked_item_id=item_id)
    )
    expenses = expenses_r.scalars().all()
    for expense in expenses:
        await session.delete(expense)

    if item:
        await session.delete(item)
        await session.commit()
    return HTMLResponse("")


# ── Daily logs list page ──────────────────────────────────────────────────────


@router.get("/logs")
async def logs_page(
    request: Request,
    building_id: Optional[int] = Query(default=None),
    project_id: Optional[int] = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    # Fetch all buildings and projects for filter dropdowns
    buildings_r = await session.execute(select(Building))
    buildings = buildings_r.scalars().all()

    result = await session.execute(
        select(Project).options(selectinload(Project.building))
    )
    # projects_r = await session.execute(select(Project))
    all_projects = result.scalars().all()

    # Build lookup maps
    # building_map = {b.id: b for b in buildings}
    project_map = {p.id: p for p in all_projects}

    # Attach building_name to each project for display
    # for p in all_projects:
    #     b = building_map.get(p.building_id)
    #     p.building = b.building if b else None

    # Filter projects by building if requested
    if building_id:
        visible_project_ids = {
            p.id for p in all_projects if p.building_id == building_id
        }
    elif project_id:
        visible_project_ids = {project_id}
    else:
        visible_project_ids = {p.id for p in all_projects}

    # Fetch logs, filtered
    q = (
        select(DailyLog)
        .where(DailyLog.project_id.in_(visible_project_ids))
        .order_by(DailyLog.project_id, DailyLog.date.desc())
    )
    logs_r = await session.execute(q)
    raw_logs = logs_r.scalars().all()

    # Fetch all task links and expense links in bulk
    if raw_logs:
        log_ids = [l.id for l in raw_logs]

        task_links_r = await session.execute(
            select(DailyLogTaskLink).where(DailyLogTaskLink.log_id.in_(log_ids))
        )
        task_links = task_links_r.scalars().all()

        task_ids = list({tl.task_id for tl in task_links})
        tasks_r = (
            await session.execute(select(Task).where(Task.id.in_(task_ids)))
            if task_ids
            else None
        )
        task_map = {t.id: t for t in (tasks_r.scalars().all() if tasks_r else [])}

        exp_links_r = await session.execute(
            select(DailyLogExpenseLink).where(DailyLogExpenseLink.log_id.in_(log_ids))
        )
        exp_links = exp_links_r.scalars().all()

        exp_ids = list({el.expense_id for el in exp_links})
        exps_r = (
            await session.execute(select(Expense).where(Expense.id.in_(exp_ids)))
            if exp_ids
            else None
        )
        exp_map = {e.id: e for e in (exps_r.scalars().all() if exps_r else [])}

        # Index links by log_id
        tasks_by_log = {}
        for tl in task_links:
            tasks_by_log.setdefault(tl.log_id, []).append(task_map[tl.task_id])

        expenses_by_log = {}
        for el in exp_links:
            expenses_by_log.setdefault(el.log_id, []).append(exp_map[el.expense_id])
    else:
        tasks_by_log = {}
        expenses_by_log = {}

    # Fetch zones
    zones_r = await session.execute(select(Zone))
    zone_map = {z.id: z.name for z in zones_r.scalars().all()}

    # Enrich logs
    for log in raw_logs:
        log.people_involved = (
            _json.loads(log.people_involved) if log.people_involved else []
        )
    # log.tasks_completed = tasks_by_log.get(log.id, [])
    # log.expenses_logged = expenses_by_log.get(log.id, [])
    # log.zone_name = zone_map.get(log.zone_id) if log.zone_id else None

    # Group by project, preserving project order
    grouped_logs = {}
    for log in raw_logs:
        p = project_map.get(log.project_id)
        if p.id not in grouped_logs.keys():
            grouped_logs[p.id] = []
        grouped_logs[p.id].append(log)

    total_logs = len(raw_logs)
    total_hours = sum(l.time_spent_hours for l in raw_logs)

    return templates.TemplateResponse(
        "logs.html",
        {
            "request": request,
            "grouped_logs": grouped_logs,
            "buildings": buildings,
            "projects": all_projects,
            "selected_building_id": building_id,
            "selected_project_id": project_id,
            "total_logs": total_logs,
            "total_hours": total_hours,
        },
    )


@router.get("/logs/{log_id}/edit")
async def log_edit_modal(
    log_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    log = await session.get(DailyLog, log_id)
    project_id = log.project_id if log else None

    projects_r = await session.execute(select(Project))
    projects = projects_r.scalars().all()

    tasks_r = await session.execute(select(Task))
    tasks = tasks_r.scalars().all()

    return templates.TemplateResponse(
        "partials/log_modal.html",
        {
            "request": request,
            "log": log,
            "projects": projects,
            "tasks": tasks,
            "project_id": project_id,
            "default_project_id": None,
        },
    )


@router.post("/logs/{log_id}/edit")
async def log_update(
    log_id: int,
    # project_id: int = Form(...),
    date_val: date = Form(..., alias="date"),
    author: str = Form(...),
    summary: Optional[str] = Form(""),
    time_spent_hours: float = Form(...),
    zone_id: Optional[int] = Form(None),
    people: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    log = await session.get(DailyLog, log_id)
    if log:
        # log.project_id = project_id
        log.date = date_val
        log.author = author
        log.summary = summary
        log.time_spent_hours = time_spent_hours
        log.zone_id = zone_id
        log.people_involved = people
        session.add(log)
        await session.commit()
    return RedirectResponse("/logs", status_code=303)


@router.delete("/logs/{log_id}")
async def delete_log_page(log_id: int, session: AsyncSession = Depends(get_session)):
    log = await session.get(DailyLog, log_id)
    if log:
        await session.delete(log)
        await session.commit()
    return HTMLResponse("")
