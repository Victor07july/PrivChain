#!/usr/bin/env python3
"""
Compila e faz deploy do contrato de verificador Groth16 gerado pelo snarkjs.

Saida principal: verifier_deployment.json com ABI e endereco do verificador.
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Tuple

import requests
import urllib3
from solcx import compile_standard, install_solc
from web3 import Web3
from web3.providers import HTTPProvider

try:
    from web3.middleware import ExtraDataToPOAMiddleware
except ImportError:
    ExtraDataToPOAMiddleware = None

DEFAULT_SOLC_VERSION = "0.8.19"
DEFAULT_GAS_LIMIT = 5_000_000
DEFAULT_RPC_URL = "http://localhost:8545"
DEFAULT_PRIVATE_KEY = "0xc87509a1c067bbde78beb793e6fa76530b6382a4c0241e5e4a9ec0a0f44dc0d3"


def compile_contract(contract_file: Path, contract_name: str, solc_version: str) -> Tuple[Any, str]:
    if not contract_file.exists():
        raise FileNotFoundError(f"Contrato nao encontrado: {contract_file}")

    contracts_dir = contract_file.parent

    with open(contract_file, "r", encoding="utf-8") as f:
        source = f.read()

    try:
        install_solc(solc_version)
    except Exception:
        pass

    compiled = compile_standard(
        {
            "language": "Solidity",
            "sources": {contract_file.name: {"content": source}},
            "settings": {
                "outputSelection": {
                    "*": {
                        "*": ["abi", "evm.bytecode", "metadata"]
                    }
                },
            },
        },
        allow_paths=str(contracts_dir),
        solc_version=solc_version,
    )

    contract_data = compiled["contracts"][contract_file.name][contract_name]
    abi = contract_data["abi"]
    bytecode = contract_data["evm"]["bytecode"]["object"]
    if not bytecode:
        raise RuntimeError("Bytecode vazio apos compilacao")

    return abi, bytecode


def get_web3(rpc_url: str, insecure_https: bool) -> Web3:
    if insecure_https:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        session = requests.Session()
        session.verify = False
        provider = HTTPProvider(rpc_url, session=session)
    else:
        provider = HTTPProvider(rpc_url)

    w3 = Web3(provider)
    if ExtraDataToPOAMiddleware is not None:
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

    try:
        _ = w3.eth.chain_id
        _ = w3.eth.block_number
    except Exception as exc:
        raise ConnectionError(f"Nao foi possivel conectar ao RPC: {rpc_url} ({exc})") from exc

    return w3


def deploy(
    w3: Web3,
    abi: Any,
    bytecode: str,
    private_key: str,
    gas_limit: int,
    gas_price_gwei: int,
) -> Dict[str, Any]:
    account = w3.eth.account.from_key(private_key)
    nonce = w3.eth.get_transaction_count(account.address)

    contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    tx = contract.constructor().build_transaction(
        {
            "from": account.address,
            "nonce": nonce,
            "gas": gas_limit,
            "gasPrice": w3.to_wei(gas_price_gwei, "gwei"),
            "chainId": w3.eth.chain_id,
        }
    )

    signed = w3.eth.account.sign_transaction(tx, private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)

    if receipt["status"] != 1:
        raise RuntimeError("Deploy revertido")

    return {
        "deployer": account.address,
        "tx_hash": tx_hash.hex(),
        "contract_address": receipt.contractAddress,
        "gas_used": int(receipt.gasUsed),
        "block_number": int(receipt.blockNumber),
        "chain_id": int(w3.eth.chain_id),
    }


def save_deployment_info(
    output_file: Path,
    rpc_url: str,
    gas_price_gwei: int,
    deploy_info: Dict[str, Any],
    abi: Any,
    contract_name: str,
    contract_file: Path,
    solc_version: str,
) -> None:
    payload = {
        "contract_name": contract_name,
        "contract_file": str(contract_file),
        "compiler_version": solc_version,
        "contract_address": deploy_info["contract_address"],
        "abi": abi,
        "rpc_url": rpc_url,
        "chain_id": deploy_info["chain_id"],
        "gas_price_gwei": gas_price_gwei,
        "deploy_tx_hash": deploy_info["tx_hash"],
        "deployer": deploy_info["deployer"],
        "gas_used": deploy_info["gas_used"],
        "deployed_at_block": deploy_info["block_number"],
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    default_contract = (script_dir.parent / "zkp" / "artifacts" / "TrajectoryVerifier.sol").resolve()
    default_output = (script_dir.parent / "zkp" / "verifier_deployment.json").resolve()

    parser = argparse.ArgumentParser(description="Deploy do verificador Groth16")
    parser.add_argument("--rpc-url", default=DEFAULT_RPC_URL, help="URL RPC do no")
    parser.add_argument("--private-key", default=DEFAULT_PRIVATE_KEY, help="Chave privada do deployer")
    parser.add_argument("--contract-file", default=str(default_contract), help="Arquivo .sol do verifier")
    parser.add_argument("--contract-name", default="Groth16Verifier", help="Nome do contrato no arquivo")
    parser.add_argument("--output-file", default=str(default_output), help="JSON de saida")
    parser.add_argument("--solc-version", default=DEFAULT_SOLC_VERSION, help="Versao do compilador")
    parser.add_argument("--gas-limit", type=int, default=DEFAULT_GAS_LIMIT, help="Gas limit deploy")
    parser.add_argument("--gas-price-gwei", type=int, default=0, help="Gas price em gwei")
    parser.add_argument("--insecure-https", action="store_true", help="Desabilita validacao TLS no RPC HTTPS")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    contract_file = Path(args.contract_file).resolve()
    output_file = Path(args.output_file).resolve()

    print("=" * 70)
    print("DEPLOY - Verifier Groth16")
    print("=" * 70)
    print(f"[info] RPC: {args.rpc_url}")
    print(f"[info] Contrato: {contract_file}")

    w3 = get_web3(args.rpc_url, insecure_https=args.insecure_https)
    print(f"[ok] Conectado | chain_id={w3.eth.chain_id} | bloco={w3.eth.block_number}")

    abi, bytecode = compile_contract(contract_file, args.contract_name, args.solc_version)
    print("[ok] Contrato compilado")

    deploy_info = deploy(
        w3=w3,
        abi=abi,
        bytecode=bytecode,
        private_key=args.private_key,
        gas_limit=args.gas_limit,
        gas_price_gwei=args.gas_price_gwei,
    )

    save_deployment_info(
        output_file=output_file,
        rpc_url=args.rpc_url,
        gas_price_gwei=args.gas_price_gwei,
        deploy_info=deploy_info,
        abi=abi,
        contract_name=args.contract_name,
        contract_file=contract_file,
        solc_version=args.solc_version,
    )

    print(f"[ok] Deploy tx: {deploy_info['tx_hash']}")
    print(f"[ok] Contrato: {deploy_info['contract_address']}")
    print(f"[ok] verifier_deployment salvo em: {output_file}")


if __name__ == "__main__":
    main()
