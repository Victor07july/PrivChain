from http import HTTPStatus
from typing import Annotated, List, Any, Optional
from web3 import AsyncWeb3

from fastapi import APIRouter, Header, Depends, UploadFile, File, Form, HTTPException, Body
from src.core.middlewares.authentication_middleware import check_authorization, check_is_admin
from src.core.repositories.users import UserBaseRepository, get_user_repository
from src.besu.services import (
    is_besu_connected, 
    compile_solidity_contract,
    prepare_deployment_transaction,
    broadcast_signed_transaction
)
from src.besu.schemas import (
    BesuStatus, 
    ContractCompilationResponse,
    SignedTransactionRequest,
    SignedTransactionResponse
)
from src.config.web3.setup import get_web3_client

besu_v1_router = APIRouter(prefix="/v1/besu")

@besu_v1_router.get("/connected/", response_model=BesuStatus, status_code=HTTPStatus.OK)
async def is_connected(
        authorization: Annotated[str | None, Header()] = None, 
        web3_client: AsyncWeb3 = Depends(get_web3_client),
    ):
    is_authorized = await check_authorization(authorization)
    if is_authorized:
        return await is_besu_connected(web3_client)
    return None


@besu_v1_router.post("/compile-contract/", response_model=ContractCompilationResponse, status_code=HTTPStatus.OK)
async def compile_contract(
        contract_file: UploadFile = File(..., description="Arquivo .sol do contrato Solidity"),
        deployer_address: str = Form(..., description="Endereço público da conta que fará o deploy"),
        constructor_params: str = Form("[]", description="Parâmetros do construtor em formato JSON array. Ex: [42] ou []"),
        gas_limit: int = Form(3000000, description="Limite de gas para a transação"),
        authorization: Annotated[str | None, Header()] = None,
        user_repo: UserBaseRepository = Depends(get_user_repository),
        web3_client: AsyncWeb3 = Depends(get_web3_client),
    ):

    # Verifica se o usuário é admin
    is_admin = await check_is_admin(authorization, user_repo)
    
    # 1. Compilar o contrato
    compilation_result = await compile_solidity_contract(contract_file)
    
    # 2. Preparar transação de deployment (toda lógica delegada ao service)
    return await prepare_deployment_transaction(
        w3=web3_client,
        compilation_result=compilation_result,
        deployer_address=deployer_address,
        constructor_params_json=constructor_params,
        gas_limit=gas_limit
    )


@besu_v1_router.post("/deploy-signed/", response_model=SignedTransactionResponse, status_code=HTTPStatus.OK)
async def deploy_signed_contract(
        request: SignedTransactionRequest = Body(...),
        authorization: Annotated[str | None, Header()] = None,
        web3_client: AsyncWeb3 = Depends(get_web3_client),
        user_repo: UserBaseRepository = Depends(get_user_repository),
    ):

    is_authorized = await check_authorization(authorization)
    
    # Verifica se o usuário é admin
    is_admin = await check_is_admin(authorization, user_repo)
    if not is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado. Apenas administradores podem fazer deploy de contratos")
    
    return await broadcast_signed_transaction(
        w3=web3_client,
        signed_transaction=request.signed_transaction
    )