#!/usr/bin/env python3
"""Utilitarios de HD wallet para derivacao de pseudonimos Ethereum."""

from typing import Dict, List, Tuple

from eth_account import Account
DEFAULT_ACCOUNT_PATH_TEMPLATE = "m/44'/60'/0'/0/{index}"


def normalize_mnemonic(text: str) -> str:
    """Normaliza espacos e quebra de linha do mnemonic."""
    return " ".join((text or "").strip().split())


def load_mnemonic_from_file(seed_file: str) -> str:
    with open(seed_file, "r", encoding="utf-8") as f:
        content = f.read()
    mnemonic = normalize_mnemonic(content)
    if not mnemonic:
        raise ValueError(f"Arquivo de seed vazio: {seed_file}")
    return mnemonic


def validate_mnemonic(mnemonic: str) -> None:
    """Valida mnemonic BIP-39 usando parser interno do eth_account."""
    Account.enable_unaudited_hdwallet_features()
    try:
        Account.from_mnemonic(mnemonic, account_path=DEFAULT_ACCOUNT_PATH_TEMPLATE.format(index=0))
    except Exception as exc:
        raise ValueError("Mnemonic invalido. Verifique palavras e checksum BIP-39.") from exc


def derive_account_from_mnemonic(mnemonic: str, account_path: str) -> Tuple[str, str]:
    """Retorna (address, private_key_hex) para um caminho HD especifico."""
    Account.enable_unaudited_hdwallet_features()
    account = Account.from_mnemonic(mnemonic, account_path=account_path)
    private_key_hex = account.key.hex()
    if not private_key_hex.startswith("0x"):
        private_key_hex = f"0x{private_key_hex}"
    return account.address, private_key_hex


def build_vehicle_private_keys(
    vehicle_ids: List[str],
    mnemonic: str,
    vehicle_indices: Dict[str, int],
    account_path_template: str = DEFAULT_ACCOUNT_PATH_TEMPLATE,
) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Deriva uma chave privada por vehicle_id de forma deterministica.

    Retorna:
    - private_keys_by_vehicle: dict vehicle_id -> private_key_hex
    - addresses_by_vehicle: dict vehicle_id -> address
    """
    validate_mnemonic(mnemonic)

    unique_sorted_ids = sorted({str(v) for v in vehicle_ids})
    if not unique_sorted_ids:
        raise ValueError("Nenhum vehicle_id informado para derivacao HD")

    private_keys_by_vehicle: Dict[str, str] = {}
    addresses_by_vehicle: Dict[str, str] = {}

    for vehicle_id in unique_sorted_ids:
        if vehicle_id not in vehicle_indices:
            raise ValueError(f"Indice HD nao informado para vehicle_id={vehicle_id}")
        index = int(vehicle_indices[vehicle_id])
        if index < 0:
            raise ValueError(f"Indice HD invalido (<0) para vehicle_id={vehicle_id}: {index}")
        account_path = account_path_template.format(index=index)
        address, private_key_hex = derive_account_from_mnemonic(mnemonic, account_path)
        private_keys_by_vehicle[vehicle_id] = private_key_hex
        addresses_by_vehicle[vehicle_id] = address

    return private_keys_by_vehicle, addresses_by_vehicle
