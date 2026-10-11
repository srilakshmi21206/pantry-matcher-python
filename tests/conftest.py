import os
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import cache
from app.main import app

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


@pytest.fixture(scope="session")
def database():
    """Rebuild the schema from migrations/*.sql, applied in filename order."""
    url = os.environ.get("DATABASE_URL")
    if not url or not os.environ.get("REDIS_URL"):
        pytest.skip("DATABASE_URL and REDIS_URL are required for integration tests")
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
        for sql_file in sorted(MIGRATIONS.glob("*.sql")):
            conn.execute(sql_file.read_text(encoding="utf-8"))
    return url


@pytest.fixture
def client(database):
    """A test client with an empty pantry table and an empty Redis."""
    with psycopg.connect(database, autocommit=True) as conn:
        conn.execute("DELETE FROM pantry")
    cache.client().flushdb()
    return TestClient(app)
