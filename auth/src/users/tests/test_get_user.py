from http import HTTPStatus
import pytest


class TestGetUser:
    @pytest.mark.asyncio
    async def test_get_users(self, client, user, admin, token):
        test_token = await token()
        user = await user()
        header = {"Authorization": f"Bearer {test_token}"}
        response = await client.get(
            url="/api/v1/users/",
            headers=header
        )
        assert response.status_code == HTTPStatus.OK
        print(response.json())
        assert response.json() == [
            {
                "id": admin.id,
                "email": admin.email,
                "first_name": None,
                "last_name": None,
                "is_active": admin.is_active
            },
            {
                "id": user.id,
                "email": user.email,
                "first_name": None,
                "last_name": None,
                "is_active": user.is_active
            }
        ]
    
    @pytest.mark.asyncio
    async def test_get_users_unauthorized(self, client):
        response = await client.get(url="/api/v1/users/")
        assert response.status_code == HTTPStatus.UNAUTHORIZED
        assert response.json() == {'detail': 'Invalid token'}