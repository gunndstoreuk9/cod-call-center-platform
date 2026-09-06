import os
from pathlib import Path

DB_PATH = Path('/tmp/cod_call_center_pytest.db')
if DB_PATH.exists():
    DB_PATH.unlink()
os.environ['DATABASE_URL'] = f'sqlite+pysqlite:///{DB_PATH}'
os.environ['ADMIN_USERNAME'] = 'owner'
os.environ['ADMIN_PASSWORD'] = 'ChangeMeNow!123'
os.environ['COOKIE_SECURE'] = 'false'

import pytest
from fastapi.testclient import TestClient
from app.core.db import Base, engine
import app.models  # noqa: F401
from app.seed import seed
from app.main import app


@pytest.fixture(scope='session', autouse=True)
def database():
    Base.metadata.create_all(engine)
    seed()
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture()
def client():
    with TestClient(app) as c:
        login = c.post('/api/v1/auth/login', json={'username': 'owner', 'password': 'ChangeMeNow!123'})
        assert login.status_code == 200
        yield c
