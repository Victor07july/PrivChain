import re
from http.client import BAD_REQUEST

from fastapi import HTTPException

password_regex = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$"
)


def validate_password(password):
    if not re.fullmatch(password_regex, password):
        raise HTTPException(
            status_code=BAD_REQUEST,
            detail="Invalid password format. It must contains a minimum of eight characters, at least one uppercase letter, one lowercase letter, one number, and one special character",
        )
