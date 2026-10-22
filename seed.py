from datetime import datetime, timedelta, timezone

from app.config import get_settings
from app.database import MongoStore, initialize_database
from app.models import Meeting, User
from app.security import hash_password


def main() -> None:
    settings = get_settings()
    email = settings.seed_email.strip().lower()
    password = settings.seed_password
    if not email or not email.endswith("@example.test"):
        raise SystemExit("Set SEED_EMAIL to a non-sensitive address at example.test.")
    if len(password) < 8:
        raise SystemExit("Set SEED_PASSWORD to a value of at least 8 characters.")

    initialize_database()
    with MongoStore() as db:
        user = db.find_one(User, {"email": email})
        if user is None:
            user = User(name=settings.seed_name, email=email, password_hash=hash_password(password))
            db.add(user)
            db.flush()
            db.commit()
            print(f"Created synthetic seed user: {email}")
        else:
            print(f"Synthetic seed user already exists; its password was not changed: {email}")

        examples = (("Demo: Project planning", 1, 10), ("Demo: Calendar review", 2, 14))
        for title, day_offset, hour in examples:
            if db.find_one(Meeting, {"owner_id": user.id, "title": title}):
                continue
            start = (datetime.now(timezone.utc) + timedelta(days=day_offset)).replace(
                hour=hour, minute=0, second=0, microsecond=0
            )
            db.add(Meeting(
                owner_id=user.id,
                title=title,
                description="Synthetic seed data for local training.",
                location="Demo room",
                attendees=[],
                start_time=start,
                end_time=start + timedelta(hours=1),
            ))
        db.commit()
        print("Synthetic demo meetings are present.")


if __name__ == "__main__":
    main()
