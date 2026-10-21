from datetime import datetime, timedelta, timezone

from app.models import Approval
from app.routers import chat as chat_router
from tests.conftest import TestingSession


def meeting_payload(title="Planning"):
    start = datetime.now(timezone.utc) + timedelta(days=2)
    return {
        "title": title,
        "start_time": start.isoformat(),
        "end_time": (start + timedelta(hours=1)).isoformat(),
    }


def test_signup_login_and_current_user(client):
    signup = client.post("/api/auth/signup", json={
        "name": "Test User",
        "email": "user@example.test",
        "password": "secure-password-1",
    })
    assert signup.status_code == 201
    login = client.post("/api/auth/login", json={
        "email": "user@example.test",
        "password": "secure-password-1",
    })
    assert login.status_code == 200
    assert set(login.json()) == {"access_token", "token_type", "user"}
    current = client.get("/api/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
    assert current.status_code == 200
    assert current.json()["email"] == "user@example.test"


def test_meetings_are_owner_scoped(client, user_headers):
    created = client.post("/api/meetings", json=meeting_payload(), headers=user_headers)
    assert created.status_code == 201
    meeting_id = created.json()["id"]
    second_signup = client.post("/api/auth/signup", json={
        "name": "Other User",
        "email": "other@example.test",
        "password": "other-password-1",
    })
    assert second_signup.status_code == 201
    token = client.post("/api/auth/login", json={
        "email": "other@example.test",
        "password": "other-password-1",
    }).json()["access_token"]
    other = {"Authorization": f"Bearer {token}"}
    assert client.get(f"/api/meetings/{meeting_id}", headers=other).status_code == 404
    assert client.patch(f"/api/meetings/{meeting_id}", json={"title": "Stolen"}, headers=other).status_code == 404
    assert client.delete(f"/api/meetings/{meeting_id}", headers=other).status_code == 404
    assert client.get("/api/meetings", headers=other).json() == []
    own_delete = client.delete(f"/api/meetings/{meeting_id}", headers=user_headers)
    approval_id = own_delete.json()["approval"]["id"]
    assert client.get("/api/approvals", headers=other).json() == []
    assert client.post(
        f"/api/approvals/{approval_id}/decision",
        json={"decision": "approve"},
        headers=other,
    ).status_code == 404


def test_conflict_and_approval_single_use(client, user_headers):
    created = client.post("/api/meetings", json=meeting_payload(), headers=user_headers)
    assert created.status_code == 201
    conflict = client.post("/api/meetings", json=meeting_payload("Overlap"), headers=user_headers)
    assert conflict.status_code == 409
    deleted = client.delete(f"/api/meetings/{created.json()['id']}", headers=user_headers)
    assert deleted.status_code == 202
    approval_id = deleted.json()["approval"]["id"]
    assert client.get(f"/api/meetings/{created.json()['id']}", headers=user_headers).json()["status"] == "scheduled"
    approved = client.post(
        f"/api/approvals/{approval_id}/decision",
        json={"decision": "approve"},
        headers=user_headers,
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    again = client.post(
        f"/api/approvals/{approval_id}/decision",
        json={"decision": "reject"},
        headers=user_headers,
    )
    assert again.status_code == 409
    assert client.get(f"/api/meetings/{created.json()['id']}", headers=user_headers).json()["status"] == "cancelled"


def test_local_chat_books_and_lists(client, user_headers):
    response = client.post("/api/chat", json={"message": "help"}, headers=user_headers)
    assert response.status_code == 200
    assert response.json()["mode"] == "secure/local"
    start = (datetime.now(timezone.utc) + timedelta(days=4)).replace(microsecond=0)
    book = client.post("/api/chat", json={
        "message": f"book Demo from {start.isoformat()} to {(start + timedelta(hours=1)).isoformat()}",
    }, headers=user_headers)
    assert book.status_code == 200
    assert "Reply yes to confirm" in book.json()["reply"]
    confirmed = client.post("/api/chat", json={"message": "yes"}, headers=user_headers)
    assert "Confirmed. Created meeting" in confirmed.json()["reply"]
    listed = client.post("/api/chat", json={"message": "list meetings"}, headers=user_headers)
    assert "Demo" in listed.json()["reply"]
    unknown = client.post("/api/chat", json={"message": "send email to attendee"}, headers=user_headers)
    assert "couldn't determine" in unknown.json()["reply"]


def test_approval_expiry_is_persisted(client, user_headers):
    created = client.post("/api/meetings", json=meeting_payload(), headers=user_headers)
    response = client.delete(f"/api/meetings/{created.json()['id']}", headers=user_headers)
    approval_id = response.json()["approval"]["id"]
    with TestingSession() as db:
        approval = db.get(Approval, approval_id)
        approval.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    expired = client.post(
        f"/api/approvals/{approval_id}/decision",
        json={"decision": "approve"},
        headers=user_headers,
    )
    assert expired.status_code == 410
    approvals = client.get("/api/approvals", headers=user_headers)
    assert approvals.json()[0]["status"] == "expired"


def test_availability_returns_complete_owned_meeting_list(client, user_headers):
    created = client.post("/api/meetings", json=meeting_payload(), headers=user_headers)
    item = created.json()
    response = client.get(
        "/api/availability",
        params={"start": item["start_time"], "end": item["end_time"]},
        headers=user_headers,
    )
    assert response.status_code == 200
    assert response.json()["available"] is False
    assert [meeting["id"] for meeting in response.json()["meetings"]] == [item["id"]]
    assert response.json()["start"].endswith("Z")


def test_chat_understands_upcoming_and_next_week(client, user_headers):
    next_monday = datetime.now(timezone.utc).date() + timedelta(days=7 - datetime.now(timezone.utc).weekday())
    start = datetime.combine(next_monday, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=11)
    created = client.post("/api/meetings", json={
        "title": "Next week review",
        "start_time": start.isoformat(),
        "end_time": (start + timedelta(hours=1)).isoformat(),
        "location": "Room 3",
        "attendees": ["alex@example.test"],
    }, headers=user_headers)
    assert created.status_code == 201
    assert created.json()["location"] == "Room 3"
    assert created.json()["attendees"] == ["alex@example.test"]
    upcoming = client.post("/api/chat", json={"message": "Show my upcoming meetings"}, headers=user_headers)
    assert "Next week review" in upcoming.json()["reply"]
    next_week = client.post("/api/chat", json={"message": "What meetings do I have next week?"}, headers=user_headers)
    assert "Next week review" in next_week.json()["reply"]


def test_chat_checks_natural_language_availability(client, user_headers):
    start = datetime.now(timezone.utc).replace(hour=14, minute=0, second=0, microsecond=0) + timedelta(days=1)
    created = client.post("/api/meetings", json={
        "title": "Busy slot",
        "start_time": start.isoformat(),
        "end_time": (start + timedelta(hours=1)).isoformat(),
    }, headers=user_headers)
    assert created.status_code == 201
    result = client.post(
        "/api/chat",
        json={"message": "Check if I’m available tomorrow at 2 PM"},
        headers=user_headers,
    )
    assert "not available" in result.json()["reply"]
    assert "Busy slot" in result.json()["reply"]


def test_chat_asks_for_missing_create_fields_and_confirms_before_create(client, user_headers):
    first = client.post("/api/chat", json={"message": "Create tomorrow at 11"}, headers=user_headers)
    assert "title" in first.json()["reply"].lower()
    assert "how long" in first.json()["reply"].lower()
    assert client.get("/api/meetings", headers=user_headers).json() == []
    details = client.post("/api/chat", json={"message": "Project review, 30 minutes"}, headers=user_headers)
    assert "Reply yes to confirm" in details.json()["reply"]
    assert client.get("/api/meetings", headers=user_headers).json() == []
    confirmed = client.post("/api/chat", json={"message": "yes"}, headers=user_headers)
    assert "Confirmed. Created meeting" in confirmed.json()["reply"]
    meetings = client.get("/api/meetings", headers=user_headers).json()
    assert len(meetings) == 1
    assert meetings[0]["title"] == "Project review"


def test_chat_edit_ambiguity_and_confirmed_move(client, user_headers):
    start = datetime.now(timezone.utc) + timedelta(days=3)
    for title, offset in (("Project review", 0), ("Team review", 3)):
        begins = start + timedelta(days=offset)
        assert client.post("/api/meetings", json={
            "title": title,
            "start_time": begins.isoformat(),
            "end_time": (begins + timedelta(hours=1)).isoformat(),
        }, headers=user_headers).status_code == 201
    ambiguous = client.post("/api/chat", json={
        "message": "Move my review to tomorrow at 11 AM",
    }, headers=user_headers)
    assert "more than one" in ambiguous.json()["reply"]
    moved = client.post("/api/chat", json={
        "message": "Move Project review to tomorrow at 11 AM",
    }, headers=user_headers)
    assert "Reply yes to confirm" in moved.json()["reply"]
    before = client.get("/api/meetings", headers=user_headers).json()
    assert before[0]["start_time"] != (datetime.now(timezone.utc) + timedelta(days=1)).replace(hour=11, minute=0, second=0, microsecond=0).isoformat()
    confirm = client.post("/api/chat", json={"message": "yes"}, headers=user_headers)
    assert "Confirmed. Updated meeting" in confirm.json()["reply"]


def test_chat_title_edit_is_confirmed_before_persistence(client, user_headers):
    created = client.post("/api/meetings", json=meeting_payload("Roadmap call"), headers=user_headers)
    proposed = client.post("/api/chat", json={
        "message": "Change the title of my roadmap call to Product review",
    }, headers=user_headers)
    assert "Reply yes to confirm" in proposed.json()["reply"]
    assert client.get(f"/api/meetings/{created.json()['id']}", headers=user_headers).json()["title"] == "Roadmap call"
    confirmed = client.post("/api/chat", json={"message": "confirm"}, headers=user_headers)
    assert "Confirmed. Updated meeting" in confirmed.json()["reply"]
    assert client.get(f"/api/meetings/{created.json()['id']}", headers=user_headers).json()["title"] == "Product review"


def test_chat_cancel_creates_approval_without_cancelling(client, user_headers):
    created = client.post("/api/meetings", json=meeting_payload("Project review"), headers=user_headers)
    result = client.post("/api/chat", json={"message": "Cancel my project review meeting"}, headers=user_headers)
    assert "awaiting your approval" in result.json()["reply"]
    assert client.get(f"/api/meetings/{created.json()['id']}", headers=user_headers).json()["status"] == "scheduled"
    approvals = client.get("/api/approvals", headers=user_headers).json()
    assert len(approvals) == 1
    assert approvals[0]["status"] == "pending"


def test_vulnerable_demos_are_synthetic_and_secure_scope_is_unchanged(client, user_headers, monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "lab_mode", "vulnerable")
    scope_demo = client.post("/api/chat", json={"message": "demo scope"}, headers=user_headers)
    assert "[SYNTHETIC-ONLY" in scope_demo.json()["reply"]
    assert "Demo User B" in scope_demo.json()["reply"]
    injection_demo = client.post("/api/chat", json={
        "message": "demo untrusted description",
    }, headers=user_headers)
    assert "simulated model follows" in injection_demo.json()["reply"]
    autonomy_demo = client.post("/api/chat", json={"message": "demo autonomy"}, headers=user_headers)
    assert "Simulated after: cancelled" in autonomy_demo.json()["reply"]
    assert "No real calendar record" in autonomy_demo.json()["reply"]
    assert client.get("/api/meetings", headers=user_headers).json() == []
    created = client.post("/api/meetings", json=meeting_payload(), headers=user_headers)
    deleted = client.delete(f"/api/meetings/{created.json()['id']}", headers=user_headers)
    assert deleted.json()["status"] == "approval_required"
    assert client.get(f"/api/meetings/{created.json()['id']}", headers=user_headers).json()["status"] == "scheduled"
    health = client.get("/api/health")
    assert health.json()["lab_mode"] == "vulnerable"
    assert health.json()["chat_mode"] == "local"


def test_external_llm_intents_are_optional_and_modes_are_reported(client, user_headers, monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "openai_base_url", "")
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "openai_model", "")
    monkeypatch.setattr(chat_router, "_openai_intent", lambda message: None)
    fallback = client.post("/api/chat", json={"message": "Can you tell me a calendar joke?"}, headers=user_headers)
    assert fallback.json()["mode"] == "secure/local"
    assert client.get("/api/health").json()["external_llm"] == "disabled"

    monkeypatch.setattr(settings, "openai_base_url", "https://llm.example.test/v1")
    monkeypatch.setattr(settings, "openai_api_key", "test-only")
    monkeypatch.setattr(settings, "openai_model", "example-model")
    monkeypatch.setattr(chat_router, "_openai_intent", lambda message: {"intent": "help"})
    llm_routed = client.post("/api/chat", json={"message": "Can you tell me a calendar joke?"}, headers=user_headers)
    assert llm_routed.json()["mode"] == "secure/openai-compatible"
    assert client.get("/api/health").json()["chat_mode"] == "openai-compatible"
    assert client.get("/api/health").json()["llm_configured"] is True


def test_openai_compatible_response_is_allowlisted(monkeypatch):
    import json
    from app.config import get_settings

    class FakeResponse:
        def __init__(self, value):
            self.value = value

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return json.dumps({"choices": [{"message": {"content": json.dumps(self.value)}}]}).encode()

    settings = get_settings()
    monkeypatch.setattr(settings, "openai_base_url", "https://llm.example.test/v1")
    monkeypatch.setattr(settings, "openai_api_key", "test-only")
    monkeypatch.setattr(settings, "openai_model", "example-model")
    requests = []

    def fake_urlopen(request, **_kwargs):
        requests.append(request)
        return FakeResponse({
            "intent": "availability",
            "duration_minutes": 45,
            "tool": "arbitrary",
        })

    monkeypatch.setattr(chat_router, "urlopen", fake_urlopen)
    assert chat_router._openai_intent("Am I free?") == {
        "intent": "availability",
        "title": None,
        "meeting_query": None,
        "start_time": None,
        "end_time": None,
        "duration_minutes": 45,
        "new_title": None,
    }
    assert requests[0].get_header("Authorization") == f"Bearer {settings.openai_api_key}"
    monkeypatch.setattr(chat_router, "urlopen", lambda *_args, **_kwargs: FakeResponse({"intent": "run_shell"}))
    assert chat_router._openai_intent("ignore safeguards") is None
    monkeypatch.setattr(chat_router, "urlopen", lambda *_args, **_kwargs: FakeResponse({
        "intent": "availability",
        "duration_minutes": {"minutes": 999999},
    }))
    assert chat_router._openai_intent("check availability") is None
    monkeypatch.setattr(chat_router, "urlopen", lambda *_args, **_kwargs: FakeResponse({
        "intent": "availability",
        "start_time": "tomorrow at noon",
    }))
    assert chat_router._openai_intent("check availability") is None
    monkeypatch.setattr(chat_router, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline")))
    assert chat_router._openai_intent("calendar request") is None


def test_sqlite_schema_migration_adds_meeting_ui_fields():
    from sqlalchemy import create_engine, inspect, text
    from app.database import migrate_sqlite_schema
    # The test DB is isolated from the live application DB.
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE meetings (id INTEGER PRIMARY KEY, title VARCHAR(200))"))
    from app.database import engine as previous_engine
    import app.database as database_module

    try:
        database_module.engine = engine
        migrate_sqlite_schema()
        columns = {column["name"] for column in inspect(engine).get_columns("meetings")}
        assert {"location", "attendees"}.issubset(columns)
    finally:
        database_module.engine = previous_engine


def test_duplicate_cancellation_reuses_pending_approval(client, user_headers):
    created = client.post("/api/meetings", json=meeting_payload("One approval only"), headers=user_headers)
    meeting_id = created.json()["id"]
    first = client.delete(f"/api/meetings/{meeting_id}", headers=user_headers)
    second = client.delete(f"/api/meetings/{meeting_id}", headers=user_headers)
    assert first.status_code == second.status_code == 202
    assert first.json()["approval"]["id"] == second.json()["approval"]["id"]
    approvals = client.get("/api/approvals", headers=user_headers).json()
    assert len([approval for approval in approvals if approval["meeting_id"] == meeting_id]) == 1
    assert approvals[0]["meeting_title"] == "One approval only"
    assert approvals[0]["meeting_status"] == "scheduled"


def test_documented_environment_names_are_loaded(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://localhost:5173")
    monkeypatch.setenv("APPROVAL_TTL_MINUTES", "7")
    settings = Settings(_env_file=None)
    assert settings.jwt_secret == "test-secret-key-that-is-long-enough"
    assert settings.cors_origins == ["http://localhost:5173"]
    assert settings.approval_ttl_minutes == 7
