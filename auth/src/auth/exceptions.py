from http import HTTPStatus
from fastapi import HTTPException


class IncorrectEmailOrPassword(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=HTTPStatus.BAD_REQUEST, detail="Incorrect email or password."
        )
