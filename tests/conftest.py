import os
import tempfile

# Must be set before the app is imported.
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-only-0123456789"
os.environ["ENV"] = "development"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c


def signup(client, email="a@example.com", name="Aarav", password="password123", starting_balance=10000):
    r = client.post("/api/auth/signup", json={"name": name, "email": email, "password": password, "starting_balance": starting_balance})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def auth(client):
    return signup(client)
