#!/usr/bin/env python3
"""
Autoriza ou revoga uma carteira para chamadas onlyAuthorized no CarbonCreditNFT_E1.
"""

import argparse
import json
from pathlib import Path

import requests
import urllib3
from eth_account import Account
from web3 import Web3
from web3.providers import HTTPProvider

try:
    from web3.middleware import ExtraDataToPOAMiddleware
except ImportError:
    ExtraDataToPOAMiddleware = None

DEFAULT_RPC_URL = "http://localhost:8545"
DEFAULT_GAS_LIMIT = 200_000
DEFAULT_GAS_PRICE_GWEI = 0
DEFAULT_PRIVATE_KEY = "0xc87509a1c067bbde78beb793e6fa76530b6382a4c0241e5e4a9ec0a0f44dc0d3"


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


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo nao encontrado: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_bool(value: str) -> bool:
    if isinstance(value, bool):
        return value
    raw = value.strip().lower()
    if raw in ("1", "true", "yes", "y", "on"):
        return True
    if raw in ("0", "false", "no", "n", "off"):
        return False
    raise argparse.ArgumentTypeError("status deve ser true/false")


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    default_deploy = (script_dir.parent / "deployment_info.json").resolve()

    parser = argparse.ArgumentParser(description="Autoriza ou revoga usuario para onlyAuthorized")
    parser.add_argument("--rpc-url", default=DEFAULT_RPC_URL, help="URL RPC do no")
    parser.add_argument("--private-key", default=DEFAULT_PRIVATE_KEY, help="Chave privada do owner")
    parser.add_argument("--deployment-file", default=str(default_deploy), help="deployment_info.json")
    parser.add_argument("--user-address", default=None, help="Endereco a autorizar/revogar")
    parser.add_argument("--user-private-key", default=None, help="Chave privada do usuario (deriva endereco)")
    parser.add_argument("--status", type=parse_bool, default=True, help="true para autorizar, false para revogar")
    parser.add_argument("--gas-limit", type=int, default=DEFAULT_GAS_LIMIT, help="Gas limit da transacao")
    parser.add_argument("--gas-price-gwei", type=int, default=DEFAULT_GAS_PRICE_GWEI, help="Gas price em gwei")
    parser.add_argument("--insecure-https", action="store_true", help="Desabilita validacao TLS no RPC HTTPS")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    deployment_file = Path(args.deployment_file).resolve()

    print("=" * 70)
    print("SET AUTHORIZED - CarbonCreditNFT_E1")
    print("=" * 70)
    print(f"[info] RPC: {args.rpc_url}")
    print(f"[info] Deployment: {deployment_file}")

    deploy_info = load_json(deployment_file)
    contract_address = deploy_info.get("contract_address")
    abi = deploy_info.get("abi")

    if not contract_address:
        raise ValueError("contract_address ausente no deploy")
    if not abi:
        raise ValueError("abi ausente no deploy")

    if args.user_private_key:
        user_address = Account.from_key(args.user_private_key).address
    else:
        user_address = args.user_address
    if not user_address:
        raise ValueError("Informe --user-address ou --user-private-key")

    w3 = get_web3(args.rpc_url, insecure_https=args.insecure_https)
    user_address = w3.to_checksum_address(user_address)
    print(f"[info] Usuario: {user_address} | status={args.status}")

    contract = w3.eth.contract(address=contract_address, abi=abi)
    account = w3.eth.account.from_key(args.private_key)
    nonce = w3.eth.get_transaction_count(account.address)

    tx = contract.functions.setAuthorized(user_address, bool(args.status)).build_transaction(
        {
            "from": account.address,
            "nonce": nonce,
            "gas": args.gas_limit,
            "gasPrice": w3.to_wei(args.gas_price_gwei, "gwei"),
            "chainId": w3.eth.chain_id,
        }
    )

    signed = w3.eth.account.sign_transaction(tx, args.private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)

    if receipt["status"] != 1:
        raise RuntimeError("Transacao revertida")

    print(f"[ok] setAuthorized tx: {receipt.transactionHash.hex()}")


if __name__ == "__main__":
    main()
