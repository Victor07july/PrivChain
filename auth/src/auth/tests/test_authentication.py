import json
from http import HTTPStatus

import pytest


class TestAuthentication:
    @pytest.mark.asyncio
    async def test_user_signin_successful(self, client, user_payload, user):
        test_customer = await user()
        response = await client.post(url="/api/v1/auth/signin/", data=user_payload)
        assert response.status_code == HTTPStatus.OK

        data = json.loads(response.content)
        assert data["id"] == test_customer.id

    @pytest.mark.asyncio
    async def test_user_signin_with_wrong_password(self, client, user):
        await user()
        wrong_credentials = {"username": "john.doe@email.com", "password": "TEST123"}
        response = await client.post(url="/api/v1/auth/signin/", data=wrong_credentials)
        assert response.status_code == HTTPStatus.BAD_REQUEST

    @pytest.mark.asyncio
    async def test_user_signin_with_inexistent_user(self, client, user):
        await user()
        wrong_credentials = {"username": "alex.doe@email.com", "password": "TEST123"}
        response = await client.post(url="/api/v1/auth/signin/", data=wrong_credentials)
        assert response.status_code == HTTPStatus.BAD_REQUEST

    @pytest.mark.asyncio
    async def test_user_signup_successful(self, client, user_payload):
        response = await client.post(url="/api/v1/auth/signup/", data=user_payload)
        assert response.status_code == HTTPStatus.CREATED

    @pytest.mark.asyncio
    async def test_user_signup_fail_with_invalid_email(self, client):
        invalid_payload = {"username": "john.doe@email", "password": "Test@123"}
        response = await client.post(url="/api/v1/auth/signup/", data=invalid_payload)
        assert response.status_code == HTTPStatus.BAD_REQUEST

        data = json.loads(response.content)
        assert data["detail"] == "Invalid email format"

    @pytest.mark.asyncio
    async def test_user_signup_fail_with_invalid_password(self, client):
        invalid_payload = {"username": "john.doe@email.com", "password": "Test123"}
        response = await client.post(url="/api/v1/auth/signup/", data=invalid_payload)
        assert response.status_code == HTTPStatus.BAD_REQUEST

        data = json.loads(response.content)
        assert (
            data["detail"]
            == "Invalid password format. It must contains a minimum of eight characters, at least one uppercase letter, one lowercase letter, one number, and one special character"
        )
