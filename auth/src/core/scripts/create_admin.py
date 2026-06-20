from passlib.handlers.pbkdf2 import pbkdf2_sha512
from src.core.models import User

import sys

from src.core.scripts.db import get_db


def main():
    try:
        username = sys.argv[1]
        password = sys.argv[2]
    except IndexError:
        raise ValueError("Username or password is missing")

    hashed_password = pbkdf2_sha512.hash(password)
    admin = User(
        username=username,
        hashed_password=hashed_password,
        is_admin=True,
    )

    db_session = next(get_db())
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)


if __name__ == "__main__":
    main()
    print("Admin user created")
    sys.exit(0)
