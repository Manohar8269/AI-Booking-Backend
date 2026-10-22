from __future__ import annotations

from copy import deepcopy
from dataclasses import fields
from typing import Any, TypeVar

from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument

from app.config import get_settings
from app.models import Approval, AuditLog, ChatPendingAction, Meeting, User

Model = TypeVar("Model", User, Meeting, Approval, AuditLog, ChatPendingAction)
COLLECTIONS = {
    User: "users",
    Meeting: "meetings",
    Approval: "approvals",
    AuditLog: "audit_logs",
    ChatPendingAction: "chat_pending_actions",
}
TRANSIENT_FIELDS = {Approval: {"meeting_title", "meeting_status", "meeting_start_time"}}

_settings = get_settings()
_mongo_client: MongoClient | None = None
_mongo_database = None


def _database():
    global _mongo_client, _mongo_database
    if not _settings.mongodb_url.strip():
        raise RuntimeError("MONGODB_URL is required; SQL databases are not supported.")
    if _mongo_client is None:
        _mongo_client = MongoClient(
            _settings.mongodb_url,
            tz_aware=True,
            serverSelectionTimeoutMS=10000,
            appname="ai-booking-calendar",
        )
    if _mongo_database is None:
        _mongo_database = _mongo_client[_settings.mongodb_database]
    return _mongo_database


def initialize_database() -> None:
    database = _database()
    _mongo_client.admin.command("ping")
    database.users.create_index([("email", ASCENDING)], unique=True)
    database.meetings.create_index([("owner_id", ASCENDING), ("start_time", ASCENDING), ("status", ASCENDING)])
    database.approvals.create_index([("owner_id", ASCENDING), ("created_at", DESCENDING)])
    database.audit_logs.create_index([("actor_id", ASCENDING), ("created_at", DESCENDING)])
    database.chat_pending_actions.create_index([("owner_id", ASCENDING)], unique=True)
    for collection_name in COLLECTIONS.values():
        collection = database[collection_name]
        highest = collection.find_one({}, {"_id": 1}, sort=[("_id", DESCENDING)])
        highest_id = highest["_id"] if highest and isinstance(highest["_id"], int) else 0
        database["_counters"].find_one_and_update(
            {"_id": collection_name},
            {"$max": {"value": highest_id}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )


class MongoStore:
    """Small request-scoped unit of work backed only by MongoDB collections."""

    def __init__(self):
        self.database = _database()
        self._tracked: dict[tuple[type, int], Any] = {}
        self._originals: dict[tuple[type, int], dict[str, Any] | None] = {}
        self._deleted: set[tuple[type, int]] = set()

    def _collection(self, model: type):
        try:
            return self.database[COLLECTIONS[model]]
        except KeyError as exc:
            raise TypeError(f"Unsupported MongoDB record type: {model.__name__}") from exc

    def _next_id(self, model: type) -> int:
        collection_name = COLLECTIONS[model]
        counter = self.database["_counters"].find_one_and_update(
            {"_id": collection_name},
            {"$inc": {"value": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return int(counter["value"])

    @staticmethod
    def _document(record: Any) -> dict[str, Any]:
        ignored = TRANSIENT_FIELDS.get(type(record), set())
        document = {item.name: deepcopy(getattr(record, item.name)) for item in fields(record) if item.name != "id" and item.name not in ignored}
        document["_id"] = record.id
        return document

    def _from_document(self, model: type[Model], document: dict[str, Any]) -> Model:
        key = (model, int(document["_id"]))
        if key in self._deleted:
            raise LookupError("Record has been deleted in this request")
        if key in self._tracked:
            return self._tracked[key]
        accepted = {item.name for item in fields(model)}
        values = {name: deepcopy(value) for name, value in document.items() if name in accepted and name != "id"}
        values["id"] = int(document["_id"])
        record = model(**values)
        self._tracked[key] = record
        self._originals[key] = self._document(record)
        return record

    def get(self, model: type[Model], record_id: int) -> Model | None:
        key = (model, int(record_id))
        if key in self._deleted:
            return None
        if key in self._tracked:
            return self._tracked[key]
        document = self._collection(model).find_one({"_id": int(record_id)})
        return self._from_document(model, document) if document else None

    def find_one(self, model: type[Model], query: dict[str, Any], sort: list[tuple[str, int]] | None = None) -> Model | None:
        document = self._collection(model).find_one(query, sort=sort)
        if document and (model, int(document["_id"])) in self._deleted:
            return None
        return self._from_document(model, document) if document else None

    def find_many(
        self,
        model: type[Model],
        query: dict[str, Any] | None = None,
        sort: list[tuple[str, int]] | None = None,
        limit: int | None = None,
    ) -> list[Model]:
        cursor = self._collection(model).find(query or {})
        if sort:
            cursor = cursor.sort(sort)
        if limit is not None:
            cursor = cursor.limit(limit)
        records = []
        for document in cursor:
            if (model, int(document["_id"])) in self._deleted:
                continue
            records.append(self._from_document(model, document))
        return records

    def add(self, record: Any) -> None:
        model = type(record)
        self._collection(model)
        if record.id is None:
            record.id = self._next_id(model)
        key = (model, int(record.id))
        self._tracked[key] = record
        self._originals.setdefault(key, None)
        self._deleted.discard(key)

    def flush(self) -> None:
        # Mongo IDs are assigned by add(), so callers can safely use them now.
        return None

    def commit(self) -> None:
        for model, record_id in self._deleted:
            self._collection(model).delete_one({"_id": record_id})
        for key, record in self._tracked.items():
            if key in self._deleted:
                continue
            document = self._document(record)
            original = self._originals.get(key)
            if original != document:
                self._collection(key[0]).replace_one({"_id": record.id}, document, upsert=True)
                self._originals[key] = deepcopy(document)
        for key in self._deleted:
            self._tracked.pop(key, None)
            self._originals.pop(key, None)
        self._deleted.clear()

    def rollback(self) -> None:
        self._tracked.clear()
        self._originals.clear()
        self._deleted.clear()

    def refresh(self, _record: Any) -> None:
        return None

    def delete(self, record: Any) -> None:
        self._deleted.add((type(record), int(record.id)))

    def close(self) -> None:
        self._tracked.clear()
        self._originals.clear()
        self._deleted.clear()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def get_db():
    db = MongoStore()
    try:
        yield db
    finally:
        db.close()
