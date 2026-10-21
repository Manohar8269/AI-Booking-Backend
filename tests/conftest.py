import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "test-secret-that-is-long-enough-for-hs256"
os.environ["LAB_MODE"] = "secure"
os.environ["APP_ENV"] = "development"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app import models  # noqa: F401

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def client():
    Base.metadata.create_all(bind=engine)

    def override_db():
        with TestingSession() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def user_headers(client):
    response = client.post("/api/auth/signup", json={
        "name": "Example User",
        "email": "owner@example.test",
        "password": "testing-password-123",
    })
    assert response.status_code == 201
    login = client.post("/api/auth/login", json={"email": "owner@example.test", "password": "testing-password-123"})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}
