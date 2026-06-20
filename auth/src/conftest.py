from os import getenv, environ

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from dotenv import load_dotenv
from passlib.handlers.pbkdf2 import pbkdf2_sha512
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import SQLModel

from src.auth.services import signin_user
from src.config.database.setup import get_db_session
from src.core.models import User
from src.main import app
from src.core.repositories.users import UserSQLAlchemyRepository
from src.users.service import create_user

load_dotenv("src/config/.env")

DATABASE_SERVICE_NAME = getenv("DB_SERVICE_NAME", None)
DATABASE_USER = getenv("DB_USER", None)
DATABASE_PASSWORD = getenv("DB_PASSWORD", None)
DATABASE_HOST = getenv("DB_HOST", None)
DATABASE_PORT = getenv("DB_PORT", None)
DATABASE_NAME = getenv("DB_NAME", None)
TEST_SQLALCHEMY_DATABASE_URL = f"{DATABASE_SERVICE_NAME}://{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/test"

ENVIRONMENT = getenv("ENV", None)

db_logs = "debug" if ENVIRONMENT == "development" else True


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(TEST_SQLALCHEMY_DATABASE_URL, echo=db_logs)
    yield engine


@pytest_asyncio.fixture
async def db_connection(db_engine):
    async with db_engine.connect() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        yield conn
        await conn.run_sync(SQLModel.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session(db_connection) -> AsyncSession:
    async_session = sessionmaker(
        bind=db_connection, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session


@pytest_asyncio.fixture
async def setup_db(db_session):
    # TODO: add operations to initialize the database
    # await db_session.commit()
    pass


@pytest_asyncio.fixture
async def client(db_session, setup_db) -> AsyncClient:
    app.dependency_overrides[get_db_session] = lambda: db_session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
def user_payload():
    return {"username": "johndoe@email.com", "password": "Test@123"}


@pytest.fixture
def user(db_session, user_payload):
    async def _user():
        user_repo = UserSQLAlchemyRepository(db_session)
        fake_user = await create_user(
            user_payload.get("username"), user_payload.get("password"), user_repo
        )
        return fake_user

    return _user


@pytest.fixture
def admin_payload():
    return {"username": "alex.doe@email.com", "password": "test1234"}


@pytest_asyncio.fixture
async def admin(db_session, admin_payload):
    password = admin_payload["password"]
    hashed_password = pbkdf2_sha512.hash(password)
    fake_admin = User(
        email=admin_payload["username"],
        hashed_password=hashed_password,
        is_active=True,
        is_admin=True,
    )
    db_session.add(fake_admin)
    await db_session.commit()
    await db_session.refresh(fake_admin)
    return fake_admin


@pytest.fixture
def token(db_session, admin, admin_payload):
    async def _token():
        user_repo = UserSQLAlchemyRepository(db_session)
        auth_user = await signin_user(
            email=admin_payload["username"],
            password=admin_payload["password"],
            user_repo=user_repo,
        )
        return auth_user.token

    return _token

@pytest.fixture
def user_token(db_session, user, user_payload):
    async def _user_token():
        user_repo = UserSQLAlchemyRepository(db_session)
        auth_user = await signin_user(
            email=user_payload["username"],
            password=user_payload["password"],
            user_repo=user_repo,
        )
        return auth_user.token

    return _user_token
