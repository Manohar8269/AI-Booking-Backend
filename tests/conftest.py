import os

os.environ["MONGODB_URL"] = ""
os.environ["JWT_SECRET"] = "test-secret-that-is-long-enough-for-hs256"
os.environ["LAB_MODE"] = "secure"
os.environ["APP_ENV"] = "development"

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import api, app
from app.models import Approval, AuditLog, ChatPendingAction, Meeting, User


class MemoryStore:
    """Isolated in-memory implementation of the MongoStore methods used by routes."""

    records: dict[type, dict[int, object]] = {}
    counters: dict[type, int] = {}
    models = (User, Meeting, Approval, AuditLog, ChatPendingAction)

    @classmethod
    def reset(cls):
        cls.records = {model: {} for model in cls.models}
        cls.counters = {model: 0 for model in cls.models}

    @staticmethod
    def _matches(record, query):
        for key, expected in query.items():
            actual = getattr(record, "id" if key == "_id" else key)
            if isinstance(expected, dict):
                for operator, value in expected.items():
                    if operator == "$lt" and not actual < value:
                        return False
                    if operator == "$gt" and not actual > value:
                        return False
                    if operator == "$ne" and actual == value:
                        return False
            elif actual != expected:
                return False
        return True

    def find_one(self, model, query, sort=None):
        rows = [record for record in self.records[model].values() if self._matches(record, query)]
        if sort:
            for field, direction in reversed(sort):
                name = "id" if field == "_id" else field
                rows.sort(key=lambda item: getattr(item, name), reverse=direction < 0)
        return rows[0] if rows else None

    def find_many(self, model, query=None, sort=None, limit=None):
        rows = [
            record for record in self.records[model].values()
            if self._matches(record, query or {})
        ]
        if sort:
            for field, direction in reversed(sort):
                name = "id" if field == "_id" else field
                rows.sort(key=lambda item: getattr(item, name), reverse=direction < 0)
        return rows[:limit] if limit is not None else rows

    def get(self, model, record_id):
        return self.records[model].get(record_id)

    def add(self, record):
        model = type(record)
        if record.id is None:
            self.counters[model] += 1
            record.id = self.counters[model]
        self.records[model][record.id] = record

    def flush(self):
        return None

    def commit(self):
        return None

    def rollback(self):
        return None

    def delete(self, record):
        self.records[type(record)].pop(record.id, None)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


MemoryStore.reset()
TestingSession = MemoryStore


@pytest.fixture()
def client():
    MemoryStore.reset()
    api.dependency_overrides[get_db] = lambda: MemoryStore()
    test_client = TestClient(app)
    yield test_client
    test_client.close()
    api.dependency_overrides.clear()


@pytest.fixture()
def user_headers(client):
    response = client.post("/api/auth/signup", json={
        "name": "Example User",
        "email": "owner@example.test",
        "password": "testing-password-123",
    })
    assert response.status_code == 201
    login = client.post("/api/auth/login", json={
        "email": "owner@example.test",
        "password": "testing-password-123",
    })
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}
