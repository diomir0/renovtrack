from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.database import init_db
from app.routers import projects, tasks, expenses, inventory, logs, assistant
from app.routers import pages
import os


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    os.makedirs("./uploads", exist_ok=True)
    yield


app = FastAPI(
    title="RenovTrack",
    description="Renovation project management with local LLM assistant",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pages (HTML)
app.include_router(pages.router)

# API Routers (JSON)
app.include_router(projects.router)
app.include_router(tasks.router)
app.include_router(expenses.router)
app.include_router(inventory.router)
app.include_router(logs.router)
app.include_router(assistant.router)


@app.get("/api")
async def root():
    return {"message": "RenovTrack API running", "docs": "/docs"}
