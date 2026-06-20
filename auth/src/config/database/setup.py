from os import getenv, environ
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv("src/config/.env")

DATABASE_SERVICE_NAME = getenv("DB_SERVICE_NAME", None)
DATABASE_USER = getenv("DB_USER", None)
DATABASE_PASSWORD = getenv("DB_PASSWORD", None)
DATABASE_HOST = getenv("DB_HOST", None)
DATABASE_PORT = getenv("DB_PORT", None)
DATABASE_NAME = getenv("DB_NAME", None)
SQLALCHEMY_DATABASE_URL = f"{DATABASE_SERVICE_NAME}://{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"
environ.setdefault("DATABASE_URL", SQLALCHEMY_DATABASE_URL)

ENVIRONMENT = getenv("ENV", None)

db_logs = "debug" if ENVIRONMENT == "development" else True
engine = create_async_engine(SQLALCHEMY_DATABASE_URL, echo=db_logs)


async def get_db_session() -> AsyncSession:
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
