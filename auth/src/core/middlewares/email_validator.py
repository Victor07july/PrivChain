import re
from http.client import BAD_REQUEST

from fastapi import HTTPException

email_regex = re.compile(
    r"([A-Za-z0-9]+[.-_])*[A-Za-z0-9]+@[A-Za-z0-9-]+(\.[A-Z|a-z]{2,})+"
)


def validate_email(email):
    if not re.fullmatch(email_regex, email):
        raise HTTPException(
            status_code=BAD_REQUEST,
            detail="Invalid email format",
        )
