# RenovTrack 🏗️

A self-hosted renovation project management tool with a local LLM assistant.

## Features

- **Buildings & Projects** — organise work by building, then by infrastructure (roof, sanitation, electrical…)
- **Zones** — break projects into sub-areas (rooms, sections)
- **Task planning** — subtasks, priorities, statuses, assignees
- **Inventory tracking** — materials, tools, delivery status
- **Expense tracking** — per project, per zone, per category
- **Daily logs** — who worked, how long, what was done, what was spent
- **LLM assistant** — ask natural language questions about your project data (via local Ollama)

## Setup

### 1. Clone and configure

```bash
cp .env.example .env
# Edit .env — at minimum set a proper SECRET_KEY
```

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Run

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be live at `http://localhost:8000`  
Interactive docs at `http://localhost:8000/docs`

### 4. (Optional) Local LLM assistant

Install [Ollama](https://ollama.com), then:

```bash
ollama pull mistral
```

Make sure Ollama is running when you use the `/assistant` endpoint.  
You can change the model in `.env` (`OLLAMA_MODEL=mistral`).

## Project Structure

```
renovtrack/
├── app/
│   ├── main.py           # FastAPI app entry point
│   ├── config.py         # Settings from .env
│   ├── database.py       # Async SQLite engine + session
│   ├── models/
│   │   └── models.py     # All SQLModel data models
│   └── routers/
│       ├── projects.py   # CRUD for projects
│       ├── tasks.py      # CRUD for tasks
│       ├── expenses.py   # CRUD + summary for expenses
│       ├── inventory.py  # CRUD for inventory items
│       ├── logs.py       # Daily log creation + linking
│       └── assistant.py  # Local LLM query endpoint
├── tests/
├── requirements.txt
└── .env.example
```

## Data Hierarchy

```
Building
└── Project (roof, sanitation, electrical…)
    ├── Zone (optional: kitchen, north wall…)
    ├── Task (with subtasks, priorities, assignees)
    ├── Inventory Item (material, tool, appliance…)
    ├── Expense (linked to zone and/or inventory item)
    └── Daily Log
            ├── tasks completed (→ auto-marked done)
            ├── expenses logged
            └── people involved
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `/projects/` | List / create projects |
| GET/PATCH/DELETE | `/projects/{id}` | Get / update / delete |
| GET/POST | `/tasks/` | List (filterable) / create |
| GET/POST | `/expenses/` | List / create |
| GET | `/expenses/summary?project_id=` | Spending by category |
| GET/POST | `/inventory/` | List / create items |
| GET/POST | `/logs/` | List / create daily logs |
| POST | `/assistant/` | Ask LLM about project data |

## Next Steps (suggested)

- [ ] Add authentication (JWT — skeleton ready in `auth.py`)
- [ ] Receipt/photo upload endpoint (Pillow + aiofiles ready)
- [ ] HTMX frontend for mobile-friendly UI
- [ ] Export daily logs to PDF
- [ ] Alembic migrations for schema evolution
- [ ] Worker roster management
