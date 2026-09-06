from app.core.config import settings
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import Store, User
from app.services.digylog import seed_status_mappings


def seed():
    db = SessionLocal()
    try:
        owner = db.query(User).filter(User.username == settings.admin_username.strip().lower()).first()
        if not owner:
            owner = User(
                username=settings.admin_username.strip().lower(),
                password_hash=hash_password(settings.admin_password),
                display_name=settings.admin_display_name,
                role="OWNER",
                is_active=True,
            )
            db.add(owner)
        store = db.query(Store).filter(Store.code == "MOROCCO").first()
        if not store:
            db.add(Store(name="Morocco Store", code="MOROCCO", country="MA", currency="MAD", timezone="Africa/Casablanca"))
        seed_status_mappings(db)
        db.commit()
        print("Seed complete")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
