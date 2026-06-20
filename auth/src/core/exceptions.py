from http import HTTPStatus

from fastapi import HTTPException


class InvalidEmail(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Email is invalid or already registered",
        )


class Unauthorized(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail="Invalid token",
        )

class UnauthorizedByExpiredSignature(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail="Credential expired",
        )

class Forbidden(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=HTTPStatus.FORBIDDEN,
            detail="Token bearer cannot execute the required operation",
        )

class UserNotFoundException(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=HTTPStatus.NOT_FOUND, detail="User not found for given email."
        )
