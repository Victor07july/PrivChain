#!/usr/bin/env python3
"""
Modulo separado para envio de resultados do oraculo para blockchain.

O modulo e propositalmente generico: o metodo do contrato e os argumentos
sao definidos em runtime via CLI (no oraculo) para desacoplar da ABI final.
"""

import json
from typing import Any, Dict, List, Optional

from eth_account import Account
from web3 import Web3
from web3.exceptions import ContractLogicError, TimeExhausted

try:
    from web3.middleware import ExtraDataToPOAMiddleware
except ImportError:
    ExtraDataToPOAMiddleware = None


DEFAULT_GAS_LIMIT = 900000


def load_deployment_info(deployment_file: str) -> Dict[str, Any]:
    with open(deployment_file, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_json_path(result: Dict[str, Any], spec: str) -> Any:
    if not spec.startswith("$."):
        return spec

    current: Any = result
    for part in spec[2:].split("."):
        if not isinstance(current, dict) or part not in current:
            raise KeyError(f"Caminho de argumento nao encontrado: {spec}")
        current = current[part]
    return current


def resolve_method_args(result: Dict[str, Any], method_args_spec: List[str]) -> List[Any]:
    args: List[Any] = []
    for spec in method_args_spec:
        args.append(resolve_json_path(result, spec))
    return args


def get_web3(rpc_url: str) -> Web3:
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if ExtraDataToPOAMiddleware is not None:
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3


def send_oracle_results(
    results: List[Dict[str, Any]],
    deployment_file: str,
    private_key: Optional[str],
    method_name: str,
    method_args_spec: List[str],
    private_keys_by_vehicle: Optional[Dict[str, str]] = None,
    gas_limit: int = DEFAULT_GAS_LIMIT,
    receipt_timeout: int = 180,
) -> List[str]:
    deployment = load_deployment_info(deployment_file)

    contract_address = deployment["contract_address"]
    abi = deployment["abi"]
    rpc_url = deployment.get("rpc_url", "http://localhost:8545")
    chain_id = deployment.get("chain_id")
    gas_price_gwei = deployment.get("gas_price_gwei", 0)

    w3 = get_web3(rpc_url)
    try:
        _ = w3.eth.chain_id
        _ = w3.eth.block_number
    except Exception as exc:
        raise ConnectionError(f"Nao foi possivel conectar ao RPC: {rpc_url} ({exc})") from exc

    code = w3.eth.get_code(contract_address)
    if code in (b"", b"\x00", b"\x00" * 1):
        raise RuntimeError(f"Endereco do contrato sem bytecode: {contract_address}")
    if isinstance(code, (bytes, bytearray)) and len(code) == 0:
        raise RuntimeError(f"Endereco do contrato sem bytecode: {contract_address}")

    contract = w3.eth.contract(address=contract_address, abi=abi)
    nonce_by_address: Dict[str, int] = {}

    if not private_key and not private_keys_by_vehicle:
        raise ValueError("Informe private_key ou private_keys_by_vehicle para envio on-chain")

    tx_hashes: List[str] = []

    for result in results:
        fn_args = resolve_method_args(result, method_args_spec)

        vehicle_id = str(result.get("vehicle_id", ""))
        key_for_tx = private_key
        if private_keys_by_vehicle is not None:
            if vehicle_id not in private_keys_by_vehicle:
                raise KeyError(f"Chave privada nao encontrada para vehicle_id={vehicle_id}")
            key_for_tx = private_keys_by_vehicle[vehicle_id]
        if not key_for_tx:
            raise ValueError(f"Chave privada vazia para vehicle_id={vehicle_id}")

        account = Account.from_key(key_for_tx)
        from_addr = account.address

        if not hasattr(contract.functions, method_name):
            raise AttributeError(f"Metodo {method_name} nao encontrado no contrato")

        if from_addr not in nonce_by_address:
            nonce_by_address[from_addr] = w3.eth.get_transaction_count(from_addr)
        nonce = nonce_by_address[from_addr]

        tx_payload = {
            "from": from_addr,
            "nonce": nonce,
            "gas": gas_limit,
            "gasPrice": w3.to_wei(gas_price_gwei, "gwei"),
        }
        if chain_id is not None:
            tx_payload["chainId"] = int(chain_id)

        fn = getattr(contract.functions, method_name)(*fn_args)
        try:
            fn.call({"from": from_addr})
        except (ContractLogicError, ValueError) as exc:
            raise RuntimeError(
                f"Transacao revertida (precheck) para vehicle_id={result.get('vehicle_id')}: {exc}"
            ) from exc

        txn = fn.build_transaction(tx_payload)
        signed = w3.eth.account.sign_transaction(txn, key_for_tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        print(f"[tx] enviado {tx_hash.hex()} | aguardando confirmacao...")
        try:
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=receipt_timeout)
        except TimeExhausted as exc:
            raise RuntimeError(f"Timeout aguardando receipt: {tx_hash.hex()}") from exc

        if receipt["status"] != 1:
            raise RuntimeError(f"Transacao revertida para vehicle_id={result.get('vehicle_id')}")

        tx_hashes.append(tx_hash.hex())
        nonce_by_address[from_addr] += 1

    return tx_hashes
