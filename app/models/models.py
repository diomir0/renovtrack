import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel

# ── Link tables ──────────────────────────────────────────────────────────────


class DailyLogTaskLink(SQLModel, table=True):
    log_id: Optional[int] = Field(
        default=None, foreign_key="dailylog.id", primary_key=True
    )
    task_id: Optional[int] = Field(
        default=None, foreign_key="task.id", primary_key=True
    )


class DailyLogExpenseLink(SQLModel, table=True):
    log_id: Optional[int] = Field(
        default=None, foreign_key="dailylog.id", primary_key=True
    )
    expense_id: Optional[int] = Field(
        default=None, foreign_key="expense.id", primary_key=True
    )


# ── Building ──────────────────────────────────────────────────────────────────


class BuildingBase(SQLModel):
    name: str
    address: Optional[str] = None
    description: Optional[str] = None


class Building(BuildingBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    projects: List["Project"] = Relationship(back_populates="building")


class BuildingCreate(BuildingBase):
    pass


class BuildingRead(BuildingBase):
    id: int
    created_at: datetime


# ── Project ───────────────────────────────────────────────────────────────────
# A project = one infrastructure (roof, sanitation, electrical…)


class ProjectBase(SQLModel):
    name: str
    description: Optional[str] = None
    status: str = "planning"  # planning | active | on_hold | done
    budget_total: float = 0.0
    start_date: Optional[date] = None
    estimated_end_date: Optional[date] = None


class Project(ProjectBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    building_id: int = Field(foreign_key="building.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    building: Building = Relationship(back_populates="projects")
    zones: List["Zone"] = Relationship(back_populates="project")
    tasks: List["Task"] = Relationship(back_populates="project")
    inventory_items: List["InventoryItem"] = Relationship(back_populates="project")
    expenses: List["Expense"] = Relationship(back_populates="project")
    daily_logs: List["DailyLog"] = Relationship(back_populates="project")


@dataclass
class ProjectWithStats:
    project: Project
    spent: float
    task_done: int = 0
    task_total: int = 0


class ProjectCreate(ProjectBase):
    building_id: int


class ProjectRead(ProjectBase):
    id: int
    building_id: int
    created_at: datetime


# ── Zone ──────────────────────────────────────────────────────────────────────


class ZoneBase(SQLModel):
    name: str
    description: Optional[str] = None


class Zone(ZoneBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id")

    project: Optional[Project] = Relationship(back_populates="zones")
    tasks: List["Task"] = Relationship(back_populates="zone")
    inventory_items: List["InventoryItem"] = Relationship(back_populates="zone")
    expenses: List["Expense"] = Relationship(back_populates="zone")


class ZoneCreate(ZoneBase):
    project_id: int


class ZoneRead(ZoneBase):
    id: int
    project_id: int


# ── Task ──────────────────────────────────────────────────────────────────────


class TaskBase(SQLModel):
    title: str
    description: Optional[str] = None
    status: str = "todo"  # todo | in_progress | blocked | done
    priority: str = "normal"  # low | normal | high | urgent
    assigned_to: Optional[str] = None
    due_date: Optional[date] = None


class Task(TaskBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id")
    zone_id: Optional[int] = Field(default=None, foreign_key="zone.id")
    parent_task_id: Optional[int] = Field(default=None, foreign_key="task.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    project: Optional[Project] = Relationship(back_populates="tasks")
    zone: Optional[Zone] = Relationship(back_populates="tasks")
    daily_logs: List["DailyLog"] = Relationship(
        back_populates="tasks_completed", link_model=DailyLogTaskLink
    )
    inventory_items: List["InventoryItem"] = Relationship(back_populates="linked_task")


class TaskCreate(TaskBase):
    project_id: int
    zone_id: Optional[int] = None
    parent_task_id: Optional[int] = None


class TaskRead(TaskBase):
    id: int
    project_id: int
    zone_id: Optional[int]
    parent_task_id: Optional[int]
    created_at: datetime


# ── Inventory Item ────────────────────────────────────────────────────────────


class InventoryItemBase(SQLModel):
    name: str
    category: str = "material"  # material | tool | appliance | consumable
    quantity: float = 0.0
    unit: str = "unit"
    unit_price: float = 0.0
    status: str = "pending"  # pending | ordered | delivered | installed
    supplier: Optional[str] = None
    # unit_price: Optional[float] = None
    acquisition_date: Optional[date] = None
    storage: Optional[str] = None
    notes: Optional[str] = None


class InventoryItem(InventoryItemBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: Optional[int] = Field(foreign_key="project.id")
    zone_id: Optional[int] = Field(default=None, foreign_key="zone.id")
    linked_task_id: Optional[int] = Field(default=None, foreign_key="task.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    project: Optional[Project] = Relationship(back_populates="inventory_items")
    zone: Optional[Zone] = Relationship(back_populates="inventory_items")
    linked_task: Optional[Task] = Relationship(back_populates="inventory_items")

    @property
    def total_price(self) -> Optional[float]:
        if self.unit_price is not None:
            return round(self.unit_price * self.quantity, 2)
        return None


class InventoryItemCreate(InventoryItemBase):
    project_id: Optional[int] = None
    zone_id: Optional[int] = None
    linked_task_id: Optional[int] = None


class InventoryItemRead(InventoryItemBase):
    id: int
    project_id: Optional[int]
    zone_id: Optional[int]
    linked_task_id: Optional[int]
    created_at: datetime


# ── Expense ───────────────────────────────────────────────────────────────────


class ExpenseBase(SQLModel):
    label: str
    amount: float
    date: date
    category: str = "other"  # labor | material | equipment | other
    paid_by: str
    receipt_url: Optional[str] = None
    notes: Optional[str] = None


class Expense(ExpenseBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id")
    zone_id: Optional[int] = Field(default=None, foreign_key="zone.id")
    linked_item_id: Optional[int] = Field(default=None, foreign_key="inventoryitem.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    project: Optional[Project] = Relationship(back_populates="expenses")
    zone: Optional[Zone] = Relationship(back_populates="expenses")
    daily_logs: List["DailyLog"] = Relationship(
        back_populates="expenses_logged", link_model=DailyLogExpenseLink
    )


class ExpenseCreate(ExpenseBase):
    project_id: int
    zone_id: Optional[int] = None
    linked_item_id: Optional[int] = None


class ExpenseRead(ExpenseBase):
    id: int
    project_id: int
    zone_id: Optional[int]
    created_at: datetime


# ── Worker ────────────────────────────────────────────────────────────────────


class WorkerBase(SQLModel):
    name: str
    role: Optional[str] = None
    contact: Optional[str] = None


class Worker(WorkerBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.now)


class WorkerCreate(WorkerBase):
    pass


class WorkerRead(WorkerBase):
    id: int


# ── Daily Log ─────────────────────────────────────────────────────────────────


class DailyLogBase(SQLModel):
    date: date
    author: str
    time_spent_hours: float
    summary: Optional[str] = ""
    # Stored as JSON string: ["Alice", "Bob"] for flexibility
    people_involved: Optional[str] = ""


class DailyLog(DailyLogBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id")
    zone_id: Optional[int] = Field(default=None, foreign_key="zone.id")
    created_at: datetime = Field(default_factory=datetime.now)

    project: Optional[Project] = Relationship(back_populates="daily_logs")
    tasks_completed: List[Task] = Relationship(
        back_populates="daily_logs", link_model=DailyLogTaskLink
    )
    expenses_logged: List[Expense] = Relationship(
        back_populates="daily_logs", link_model=DailyLogExpenseLink
    )

    def get_people(self) -> List[str]:
        if self.people_involved:
            return json.loads(self.people_involved)
        return []

    def set_people(self, people: List[str]):
        self.people_involved = json.dumps(people)


class DailyLogCreate(DailyLogBase):
    project_id: int
    zone_id: Optional[int] = None
    task_ids: List[int] = Field(default_factory=list)
    expense_ids: List[int] = Field(default_factory=list)
    people: List[str] = Field(default_factory=list)


class DailyLogRead(DailyLogBase):
    id: int
    project_id: int
    zone_id: Optional[int]
    created_at: datetime
