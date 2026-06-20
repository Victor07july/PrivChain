from os import getenv

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlmodel import Session

load_dotenv("src/config/.env")

DATABASE_SERVICE_NAME = getenv("DATABASE_SERVICE_NAME", None)
DATABASE_USER = getenv("DB_USER", None)
DATABASE_PASSWORD = getenv("DB_PASSWORD", None)
DATABASE_HOST = getenv("DB_HOST", None)
DATABASE_PORT = getenv("DB_PORT", None)
DATABASE_NAME = getenv("DB_NAME", None)
SQLALCHEMY_DATABASE_URL = f"{DATABASE_SERVICE_NAME}://{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"
engine = create_engine(SQLALCHEMY_DATABASE_URL, echo=True)


def get_db():
    with Session(engine) as session:
        yield session
