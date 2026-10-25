# AI Booking & Calendar Agent backend

Python 3.11+ FastAPI service. MongoDB is the only supported database. The API stores users, meetings, approvals, assistant pending actions, and audit history in the database selected by `MONGODB_DATABASE`.

## Run

From `backend/`, create/activate a virtual environment, install `requirements.txt`, set `MONGODB_URL` and `MONGODB_DATABASE` in `.env`, then run:

```powershell
python -m uvicorn app.main:app --reload
```

MongoDB is pinged and the required indexes are created at startup. The MongoDB Atlas network access list must allow the backend host. Interactive API documentation is available at `/docs`. To seed a user, set `SEED_EMAIL` to an address ending in `.example.test` and `SEED_PASSWORD` (8+ characters), then run `python seed.py`. Seed credentials are optional and should be test-only.

Run the isolated backend API suite from this directory with `python -m pytest tests -q`. Tests use an in-memory store and do not connect to MongoDB.

`LAB_MODE` accepts `secure` or `vulnerable`. Vulnerable mode is rejected unless `APP_ENV=development`. Synthetic security demonstrations never access or mutate a real user's meetings. Real meeting cancellation always creates a pending approval. The service never connects to email, calendar providers, shell, or SQL databases.

An optional OpenAI-compatible chat completion endpoint is enabled only when `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `OPENAI_MODEL` are all configured. The completion receives only the user's current chat message and returns a filtered JSON intent; locally validated handlers still enforce ownership, conflict checks, and confirmation/approval. Network/configuration/response failures fall back to local command handling. `/api/health` reports whether completion is configured and whether chat is local or OpenAI-compatible.

## API contracts

All routes below are under `/api` and require `Authorization: Bearer <access_token>` except signup, login, and health.

* `POST /auth/signup` `{name,email,password}` creates an account.
* `POST /auth/login` `{email,password}` returns an access token and user.
* `GET /auth/me` returns the current user.
* `GET /meetings` lists the current user's meetings; `POST /meetings` creates a meeting.
* `GET /meetings/{id}` and `PATCH /meetings/{id}` only access a meeting owned by the caller. `DELETE /meetings/{id}` requests approval before cancellation.
* `GET /approvals` lists the caller's approvals. `POST /approvals/{id}/decision` accepts `{decision:"approve"|"reject"}`.
* `GET /availability?start=<ISO>&end=<ISO>` returns availability and matching meetings for the caller.
* `POST /chat` accepts `{message}` and returns `{reply,mode}`. Proposed creates and edits require confirmation; cancellations require approval.
* `GET /audit` returns the caller's latest 200 audit events.
* `GET /health` reports current lab mode and chat configuration without requiring auth.

Datetime values require an explicit timezone offset. Meeting intervals are half-open and overlapping scheduled meetings are rejected. User data is always scoped to the authenticated account.

Chat date/time phrases use `DEFAULT_TIMEZONE` (default `Asia/Kolkata`) unless the message names a timezone such as IST. Datetimes are stored as timezone-aware UTC instants. Meeting-title matching uses `MEETING_MATCH_THRESHOLD` (default `0.78`) and asks for clarification when the top matches are ambiguous. Chat state is scoped to the authenticated user and frontend conversation. Chat-based reschedules and title/field changes require conversational confirmation followed by an approval decision; the meeting is not changed until the approval is granted.

Existing records in local SQLite databases are not migrated automatically. Export any data that must be retained, then import it into MongoDB before switching users to the new backend.
