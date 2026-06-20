from datetime import datetime, timedelta, timezone
from os import getenv
from web3 import AsyncWeb3
from web3.middleware import ExtraDataToPOAMiddleware
from jose import jwt

JWT_EXPIRATION_DAYS = getenv("JWT_EXPIRATION_DAYS", 1)
BESU_RPC_HOST = getenv("BESU_RPC_HOST", "localhost")
BESU_RPC_PORT = getenv("BESU_RPC_PORT", "8545")
BESU_JWT_PRIVATE_KEY = getenv("BESU_JWT_PRIVATE_KEY", "src/config/web3/privateRSAKey.pem")


def create_token():
    expire = datetime.now(timezone.utc) + timedelta(days=int(JWT_EXPIRATION_DAYS))
    access_token = jwt.encode(
        {
            "permissions": ["*:*"],
            "exp": expire,
            "iat": datetime.now(timezone.utc).timestamp(),
        },
        BESU_JWT_PRIVATE_KEY,
        algorithm="RS256",
    )
    return access_token


def get_web3_client() -> AsyncWeb3:
    token = create_token()
    headers = {"Authorization": f"Bearer {token}"}
    w3 = AsyncWeb3(
        AsyncWeb3.AsyncHTTPProvider(
            f"http://{BESU_RPC_HOST}:{BESU_RPC_PORT}", 
            request_kwargs={'headers': headers}
            )
        )
    # Adicionar middleware POA para Besu QBFT
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3