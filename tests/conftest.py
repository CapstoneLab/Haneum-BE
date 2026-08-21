import os
import tempfile
from pathlib import Path

import httpx
import pytest

TEST_DB = Path(tempfile.gettempdir()) / "keyback_backend_test.sqlite3"
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{TEST_DB}"
os.environ["ANDROID_API_KEY"] = "test-android-api-key"
os.environ["INTERNAL_API_KEY"] = "test-internal-api-key"
os.environ["LLM_PROVIDER"] = "local"
os.environ["APP_ENV"] = "test"

from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-API-Key": "test-android-api-key"}
