import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import init_db


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()


@pytest.mark.asyncio
async def test_create_and_get_project():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # First create a building
        r = await client.post("/buildings/", json={"name": "Test Building"})
        # Then create a project
        r = await client.post("/projects/", json={
            "name": "Roof",
            "building_id": 1,
            "budget_total": 15000,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "Roof"

        r = await client.get(f"/projects/{data['id']}")
        assert r.status_code == 200


@pytest.mark.asyncio
async def test_create_daily_log():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/logs/", json={
            "project_id": 1,
            "date": "2025-06-01",
            "author": "Tim",
            "summary": "Installed roof joists on north side.",
            "time_spent_hours": 6.5,
            "people": ["Tim", "Marco"],
            "task_ids": [],
            "expense_ids": [],
        })
        assert r.status_code == 200
        assert r.json()["author"] == "Tim"
