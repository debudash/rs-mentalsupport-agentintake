"""Shared fixtures. Tests run on in-memory SQLite with Fake adapters at every seam."""

import os
import time
import uuid

from cryptography.fernet import Fernet

os.environ.update(
    APP_ENV="test",
    DATABASE_URL="sqlite://",
    FIELD_ENCRYPTION_KEY=Fernet.generate_key().decode(),
    LLM_PROVIDER="fake",
    OCR_ENGINE="fake",
    SUPABASE_URL="",
    SUPABASE_JWT_SECRET="test-secret-for-hs256-tokens-only-0123456789",
    FRONTEND_DIST="__no_frontend__",
)

import jwt  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api import deps  # noqa: E402
from app.auth_admin import FakeAuthAdmin, get_auth_admin  # noqa: E402
from app.db.models import Account, Base, Clinician  # noqa: E402
from app.db.session import get_engine, get_sessionmaker  # noqa: E402
from app.domain.intake import IntakeConductor  # noqa: E402
from app.llm.fake import FakeLLM, HeuristicResponder  # noqa: E402
from app.ocr import DocumentReader, get_reader  # noqa: E402
from app.ocr.engines import FakeEngine, Line  # noqa: E402
from app.profile import get_profile  # noqa: E402

SECRET = os.environ["SUPABASE_JWT_SECRET"]


def make_token(account_id: str, expires_in: int = 3600) -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": account_id, "aud": "authenticated", "iat": now, "exp": now + expires_in},
        SECRET,
        algorithm="HS256",
    )


def auth(account_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(account_id)}"}


@pytest.fixture(autouse=True)
def fresh_db():
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db():
    session = get_sessionmaker()()
    yield session
    session.close()


@pytest.fixture
def profile():
    return get_profile()


@pytest.fixture
def heuristic_llm(profile):
    return FakeLLM(HeuristicResponder(profile))


@pytest.fixture
def fake_engine():
    return FakeEngine(
        [
            Line("STATE OF RIVERSIDE", 95),
            Line("NAME", 95),
            Line("JANE Q DOE", 92, (("JANE", 92), ("Q", 90), ("DOE", 94))),
            Line("DATE OF BIRTH", 95),
            Line("1990-03-14", 91, (("1990-03-14", 91),)),
            Line("ADDRESS", 95),
            Line("123 MAIN ST", 88, (("123", 90), ("MAIN", 88), ("ST", 86))),
            Line("SPRINGFIELD, RS 12345", 87),
        ]
    )


@pytest.fixture
def app_client(heuristic_llm, profile, fake_engine):
    from app.main import app

    fake_admin = FakeAuthAdmin()
    conductor = IntakeConductor(profile, heuristic_llm, timeout=5)
    app.dependency_overrides[deps.conductor] = lambda: conductor
    app.dependency_overrides[get_auth_admin] = lambda: fake_admin
    app.dependency_overrides[get_reader] = lambda: DocumentReader(fake_engine, 70, 8 * 1024 * 1024)
    client = TestClient(app)
    client.llm = heuristic_llm
    client.auth_admin = fake_admin
    client.engine = fake_engine
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def new_account():
    return lambda: str(uuid.uuid4())


@pytest.fixture
def seeded(db):
    """Clinicians + Slots via the real seed logic (no Supabase)."""
    from app.seed import seed

    seed()
    return db.query(Clinician).all()


def make_role(db, account_id: str, role: str) -> None:
    db.add(Account(id=account_id, role=role))
    db.commit()
