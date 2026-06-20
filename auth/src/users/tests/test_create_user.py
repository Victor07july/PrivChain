import json
from http import HTTPStatus
import pytest


class TestCreateUser:
    @pytest.mark.asyncio
    async def test_create_user_successful(self, client, user_payload, token):
        test_token = await token()
        header = {"Authorization": f"Bearer {test_token}"}
        response = await client.post(
            url="/api/v1/users/", data=user_payload, headers=header
        )
        assert response.status_code == HTTPStatus.CREATED
        assert response.json() == {
            "id": 2,
            "email": user_payload["username"],
        }

    @pytest.mark.asyncio
    async def test_create_existent_user(self, client, user, user_payload, token):
        await user()
        test_token = await token()
        header = {"Authorization": f"Bearer {test_token}"}
        response = await client.post(
            url="/api/v1/users/", data=user_payload, headers=header
        )
        assert response.status_code == HTTPStatus.BAD_REQUEST

    @pytest.mark.asyncio
    async def test_create_user_with_invalid_email(self, client, token):
        test_token = await token()
        invalid_payload = {"username": "john.doe@email", "password": "Test@123"}
        header = {"Authorization": f"Bearer {test_token}"}
        response = await client.post(
            url="/api/v1/users/", data=invalid_payload, headers=header
        )
        assert response.status_code == HTTPStatus.BAD_REQUEST

        data = json.loads(response.content)
        assert data["detail"] == "Invalid email format"

    @pytest.mark.asyncio
    async def test_create_user_with_invalid_password(self, client, token):
        test_token = await token()
        invalid_payload = {"username": "john.doe@email.com", "password": "Test123"}
        header = {"Authorization": f"Bearer {test_token}"}
        response = await client.post(
            url="/api/v1/users/", data=invalid_payload, headers=header
        )
        assert response.status_code == HTTPStatus.BAD_REQUEST

        data = json.loads(response.content)
        assert (
            data["detail"]
            == "Invalid password format. It must contains a minimum of eight characters, at least one uppercase letter, one lowercase letter, one number, and one special character"
        )
