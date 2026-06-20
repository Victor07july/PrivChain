from http import HTTPStatus
import pytest


class TestUpdateUser:
    @pytest.mark.asyncio
    async def test_update_user_success(self, client, user, token):
        test_token = await token()
        user = await user()
        header = {"Authorization": f"Bearer {test_token}"}
        response = await client.put(
            url=f"/api/v1/users/",
            headers=header,
            json={
                "email": user.email,
                "first_name": "UpdatedFirstName",
                "last_name": "UpdatedLastName",
                "is_active": True,
                "is_admin": True
            }
        )
        assert response.status_code == HTTPStatus.OK
        assert response.json() == {
            "details": "User updated successfully"
        }
    
    @pytest.mark.asyncio
    async def test_update_user_with_missing_fields_success(self, client, user, token):
        test_token = await token()
        user = await user()
        header = {"Authorization": f"Bearer {test_token}"}
        response = await client.put(
            url=f"/api/v1/users/",
            headers=header,
            json={
                "email": user.email,
                "first_name": "UpdatedFirstName",
                "last_name": "UpdatedLastName",
            }
        )
        assert response.status_code == HTTPStatus.OK
        assert response.json() == {
            "details": "User updated successfully"
        }

    @pytest.mark.asyncio
    async def test_update_user_unauthorized(self, client, user, token):
        user = await user()
        response = await client.put(
            url="/api/v1/users/",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": user.email,
            }
        )
        assert response.status_code == HTTPStatus.UNAUTHORIZED
        assert response.json() == {'detail': 'Invalid token'}

    @pytest.mark.asyncio
    async def test_update_user_forbidden(self, client, user, user_token):
        user = await user()
        token = await user_token()
        response = await client.put(
            url="/api/v1/users/",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": user.email,
            }
        )
        assert response.status_code == HTTPStatus.FORBIDDEN
        assert response.json() == {'detail': 'Token bearer cannot execute the required operation'}
    
    @pytest.mark.asyncio
    async def test_update_user_not_found(self, client, token):
        test_token = await token()
        header = {"Authorization": f"Bearer {test_token}"}
        response = await client.put(
            url="/api/v1/users/",
            headers=header,
            json={
                "email": "nonexistent@email.com",
                "first_name": "UpdatedFirstName",
                "last_name": "UpdatedLastName",
                "is_active": True,
                "is_admin": True
            }
        )
        assert response.status_code == HTTPStatus.NOT_FOUND
        assert response.json() == {"detail": "User not found for given email."}