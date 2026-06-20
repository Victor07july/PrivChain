#!/usr/bin/env python3
"""
Mass benchmark script for blockchain performance.

Scenarios:
- direct: send tx with user key
- pseudonym/direct_pseudonym: direct send with pseudonym key
- oracle: offset flow via oracle API
- redeem: redeem ZK proofs using the real user key (requires oracle ZK mints)
- redeem_pseudonym: redeem ZK proofs using the pseudonym key (requires oracle ZK mints)

Edit REPEAT_PER_CSV to control how many times each CSV is used.
"""

import csv
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from eth_account import Account
from web3 import Web3
from web3.exceptions import TimeExhausted

try:
    from web3.middleware import ExtraDataToPOAMiddleware
except ImportError:
    ExtraDataToPOAMiddleware = None

def resolve_repo_root(script_path: Path) -> Path:
    for parent in script_path.parents:
        if (parent / "contracts").is_dir() and (parent / "README.md").exists():
            return parent
    return script_path.parents[1]


REPO_ROOT = resolve_repo_root(Path(__file__).resolve())
SCRIPTS_DIR = REPO_ROOT / "contracts" / "privacy" / "implementacao_offset_zkp" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.append(str(SCRIPTS_DIR))

from blockchain_sender import load_deployment_info  # type: ignore
from usuario import (  # type: ignore
    build_trajectory_hash,
    generate_zk_proof,
    load_csv_first_vehicle,
    resolve_pseudonym_private_key,
    resolve_zk_dir,
    simulate_e1_value,
    strip_aux_fields,
    to_bytes32_hex,
)


# === CONFIG (edit as needed) ===
REPEAT_PER_CSV = 1
MAX_CSV_FILES: Optional[int] = None
SCENARIOS = ["direct"]
# Available: direct, pseudonym, direct_pseudonym, oracle, oracle_direto, redeem, redeem_pseudonym

DATA_DIR = REPO_ROOT / "contracts" / "privacy" / "implementacao_offset_zkp" / "data" / "trajetos_toyota_500"
DEPLOYMENT_FILE = Path(
    os.environ.get(
        "BENCH_DEPLOYMENT_FILE",
        str(REPO_ROOT / "contracts" / "privacy" / "implementacao_offset_zkp" / "deployment_info.json"),
    )
)
ORACLE_URL = os.environ.get("BENCH_ORACLE_URL", "http://127.0.0.1:5001")

USER_PRIVATE_KEY = os.environ.get("BENCH_USER_PRIVATE_KEY", "").strip()
PSEUDONYM_PRIVATE_KEY = os.environ.get("BENCH_PSEUDONYM_PRIVATE_KEY", "").strip()
PSEUDONYM_SEED_FILE = os.environ.get("BENCH_PSEUDONYM_SEED_FILE", "").strip()
PSEUDONYM_HD_INDEX = int(os.environ.get("BENCH_PSEUDONYM_HD_INDEX", "0"))

ORACLE_OPTION_INDEX = int(os.environ.get("BENCH_ORACLE_OPTION_INDEX", "1"))
MIN_VALUE_MICRO = int(os.environ.get("BENCH_MIN_VALUE_MICRO", "1"))
DIRECT_MIN_VALUE_MICRO = int(os.environ.get("BENCH_DIRECT_MIN_VALUE_MICRO", "0"))
REDEEM_PRIVATE_KEY = os.environ.get("BENCH_REDEEM_PRIVATE_KEY", "").strip()
REDEEM_LIMIT = int(os.environ.get("BENCH_REDEEM_LIMIT", "0"))

TX_GAS_LIMIT = int(os.environ.get("BENCH_GAS_LIMIT", "900000"))
TX_RECEIPT_TIMEOUT = int(os.environ.get("BENCH_RECEIPT_TIMEOUT", "180"))

RESULTS_DIR = REPO_ROOT / "test" / "results"
RESULTS_CSV = RESULTS_DIR / "benchmark_results.csv"
SUMMARY_CSV = RESULTS_DIR / "benchmark_summary.csv"

FIELDNAMES = [
    "record_type",
    "run_id",
    "scenario",
    "csv_file",
    "csv_index",
    "repeat_index",
    "tx_method",
    "tx_hash",
    "tx_status",
    "tx_seconds",
    "tx_wait_seconds",
    "gas_used",
    "effective_gas_price",
    "tx_fee_wei",
    "block_number",
    "e1_original_micro",
    "e1_after_micro",
    "e1_original_brl",
    "e1_after_brl",
    "oracle_process_seconds",
    "oracle_confirm_seconds",
    "zkp_enabled",
    "zk_proof_seconds",
    "pseudonym_gen_seconds",
    "error",
    "total_sent",
    "success_count",
    "fail_count",
    "duration_seconds",
    "throughput_tps",
    "latency_avg",
    "latency_p95",
    "latency_max",
]


def get_web3(rpc_url: str) -> Web3:
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if ExtraDataToPOAMiddleware is not None:
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3


def _csv_has_sufficient_columns(csv_path: Path) -> bool:
    """
    Retorna True se o CSV tem colunas alem de lat/lon suficientes
    para o benchmark (vehicle_id, co2, distancias, etc.).
    Um CSV com apenas lat e lon nao e suficiente.
    """
    try:
        import pandas as pd
        df = pd.read_csv(csv_path, nrows=1)
        cols = set(c.lower() for c in df.columns)
        # Considera suficiente se tiver pelo menos uma coluna alem de lat/lon
        basic = {"lat", "lon", "latitude", "longitude", "start_lat", "start_lon"}
        return bool(cols - basic)
    except Exception:
        return False


def _resolve_data_file(csv_path: Path) -> Path:
    """
    Dado um CSV, verifica se ele tem colunas suficientes.
    Se nao tiver (ex: apenas lat/lon), tenta usar o JSON correspondente
    no mesmo diretorio (mesmo nome de arquivo, extensao .json).
    Retorna o caminho do arquivo a ser usado.
    """
    if _csv_has_sufficient_columns(csv_path):
        return csv_path
    json_path = csv_path.with_suffix(".json")
    if json_path.exists():
        return json_path
    # Sem JSON disponivel: retorna o CSV mesmo (load_data_file lidara com isso)
    return csv_path


def list_csv_files(data_dir: Path) -> List[Path]:
    """
    Lista arquivos de entrada do diretorio data_dir.
    - Para CSVs originais (vehicles_step_sim_*.csv): usa diretamente.
    - Para trajeto_*.csv: verifica se tem colunas suficientes; se nao tiver,
      resolve para o trajeto_*.json correspondente no mesmo diretorio.
    """
    files: List[Path] = sorted(data_dir.glob("vehicles_step_sim_*.csv"))
    if not files:
        raw = sorted(data_dir.glob("trajeto_*.csv"))
        files = [_resolve_data_file(p) for p in raw]
        # Remover duplicatas mantendo ordem (caso dois CSVs resolvam pro mesmo JSON)
        seen: set = set()
        unique: List[Path] = []
        for p in files:
            if p not in seen:
                seen.add(p)
                unique.append(p)
        files = unique

    def parse_index(path: Path) -> int:
        stem = path.stem
        try:
            return int(stem.split("_")[-1])
        except (ValueError, IndexError):
            return 0

    files.sort(key=parse_index)
    if MAX_CSV_FILES is None:
        return files
    return files[: MAX_CSV_FILES]


def load_obfuscated_json(json_path: str) -> Dict[str, Any]:
    """
    Carrega um trajeto a partir de um JSON salvo pelo oraculo em
    data/trajetos_ofuscados/trajeto_NNN.json.

    Reconstroi o hash e os contract_params a partir dos dados disponiveis,
    usando a trajectory_original (nao a ofuscada) para que o hash bata
    com o que foi registrado na blockchain.
    """
    import json as _json

    with open(json_path, "r", encoding="utf-8") as f:
        records = _json.load(f)

    if isinstance(records, list):
        rec = records[0]
    else:
        rec = records

    trajectory_original = rec["trajectory_original"]
    trajectory_private  = rec.get("trajectory_private", trajectory_original)
    vehicle_id          = rec.get("vin", "veh0")

    # Recalcular hash da trajetoria original (igual ao que o oraculo registrou)
    traj_hash = build_trajectory_hash(trajectory_original)

    # Reconstruir contract_params a partir dos campos do JSON
    co2_real_g      = float(rec.get("co2_real_g", 0.0))
    total_dist_km   = float(rec.get("total_distance_km", 0.0))
    city_km         = total_dist_km * 0.4
    highway_km      = total_dist_km * 0.6

    DEFAULT_ROAD_KML  = 8.5
    DEFAULT_CITY_KML  = 7.8
    DEFAULT_CARBON    = 67.13 * 6.17  # BRL/ton

    contract_params = {
        "highwayDistance":   int(highway_km * 1e6),
        "cityDistance":      int(city_km * 1e6),
        "ethanolPercent":    0,
        "roadGasoline":      int(DEFAULT_ROAD_KML * 1e6),
        "roadEthanol":       0,
        "cityGasoline":      int(DEFAULT_CITY_KML * 1e6),
        "cityEthanol":       0,
        "realCO2Emissions":  int(co2_real_g * 1e6),
        "carbonPricePerTon": int(DEFAULT_CARBON * 1e6),
        "_e1_estimado_micro": int(rec.get("valor_e1_reais", 0.0) * 1e6),
    }

    return {
        "vehicle_id":          vehicle_id,
        "trajectory":          trajectory_original,
        "trajectory_private":  trajectory_private,
        "hash":                traj_hash,
        "contract_params":     contract_params,
    }


def load_data_file(path: Path) -> Dict[str, Any]:
    """
    Carrega dados de um arquivo de entrada, seja CSV original ou
    JSON de trajeto ofuscado.
    """
    if path.suffix == ".json":
        return load_obfuscated_json(str(path))
    return load_csv_first_vehicle(str(path))


def next_nonce(w3: Web3, cache: Dict[str, int], address: str) -> int:
    if address not in cache:
        cache[address] = w3.eth.get_transaction_count(address)
    value = cache[address]
    cache[address] += 1
    return value


def wait_for_receipt(w3: Web3, tx_hash: str, timeout: int) -> Tuple[Dict[str, Any], float]:
    start = time.perf_counter()
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
    elapsed = time.perf_counter() - start
    return receipt, elapsed


def send_contract_tx(
    w3: Web3,
    contract,
    method_name: str,
    args: List[Any],
    private_key: str,
    chain_id: Optional[int],
    gas_price_gwei: int,
    nonce_cache: Dict[str, int],
) -> Dict[str, Any]:
    account = Account.from_key(private_key)
    from_addr = account.address

    tx_payload = {
        "from": from_addr,
        "nonce": next_nonce(w3, nonce_cache, from_addr),
        "gas": TX_GAS_LIMIT,
        "gasPrice": w3.to_wei(gas_price_gwei, "gwei"),
    }
    if chain_id is not None:
        tx_payload["chainId"] = int(chain_id)

    fn = getattr(contract.functions, method_name)(*args)
    txn = fn.build_transaction(tx_payload)
    signed = w3.eth.account.sign_transaction(txn, private_key)

    start = time.perf_counter()
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=TX_RECEIPT_TIMEOUT)
    elapsed = time.perf_counter() - start

    return {
        "tx_hash": tx_hash.hex(),
        "receipt": receipt,
        "tx_seconds": elapsed,
    }


def direct_or_pseudonym_run(
    scenario: str,
    data: Dict[str, Any],
    deployment: Dict[str, Any],
    w3: Web3,
    contract,
    nonce_cache: Dict[str, int],
    private_key: str,
    recipient_key: Optional[str] = None,
) -> Dict[str, Any]:
    # Quem assina a transacao (deve ser carteira autorizada no contrato).
    # Nos cenarios pseudonym/direct_pseudonym, private_key e a chave autorizada
    # (USER_PRIVATE_KEY) e recipient_key e a chave pseudonima — o NFT vai para
    # o endereco pseudonimo, mas a transacao e assinada pela carteira autorizada.
    signing_key = private_key
    recipient = Account.from_key(recipient_key).address if recipient_key else Account.from_key(private_key).address

    cp = strip_aux_fields(data["contract_params"])
    estimated_value = max(0, simulate_e1_value(data["contract_params"]))
    original_hash = to_bytes32_hex(data["hash"])

    # Montar CalculationParams como tuple para calculateAndMintWithHash
    params_tuple = [
        int(cp.get("highwayDistance",   0)),
        int(cp.get("cityDistance",      0)),
        int(cp.get("ethanolPercent",    0)),
        int(cp.get("roadGasoline",      0)),
        int(cp.get("roadEthanol",       0)),
        int(cp.get("cityGasoline",      0)),
        int(cp.get("cityEthanol",       0)),
        int(cp.get("realCO2Emissions",  0)),
        int(cp.get("carbonPricePerTon", 0)),
    ]

    tx_result = send_contract_tx(
        w3=w3,
        contract=contract,
        method_name="calculateAndPay",
        args=[params_tuple, recipient, original_hash],
        private_key=signing_key,
        chain_id=deployment.get("chain_id"),
        gas_price_gwei=deployment.get("gas_price_gwei", 0),
        nonce_cache=nonce_cache,
    )

    receipt = tx_result["receipt"]
    status = int(receipt.get("status", 0))
    gas_used = int(receipt.get("gasUsed", 0))
    effective_gas_price = int(receipt.get("effectiveGasPrice", receipt.get("gasPrice", 0)))
    tx_fee = gas_used * effective_gas_price

    return {
        "tx_method": "calculateAndMintWithHash",
        "tx_hash": tx_result["tx_hash"],
        "tx_status": status,
        "tx_seconds": round(tx_result["tx_seconds"], 6),
        "tx_wait_seconds": round(tx_result["tx_seconds"], 6),
        "gas_used": gas_used,
        "effective_gas_price": effective_gas_price,
        "tx_fee_wei": tx_fee,
        "block_number": int(receipt.get("blockNumber", 0)),
        "e1_original_micro": estimated_value,
        "e1_after_micro": estimated_value,  # calculado pelo contrato; estimativa local como referencia
        "e1_original_brl": round(estimated_value / 1e6, 6),
        "e1_after_brl": round(estimated_value / 1e6, 6),
        "oracle_process_seconds": None,
        "oracle_confirm_seconds": None,
        "zkp_enabled": None,
        "zk_proof_seconds": None,
        "error": None,
    }


def oracle_offset_run(
    data: Dict[str, Any],
    deployment: Dict[str, Any],
    w3: Web3,
) -> Dict[str, Any]:
    payload = {
        "trajetoria": data["trajectory"],
        "vehicle_id": data["vehicle_id"],
        "attempts": 10,
        "top_k": 5,
        "enable_map_matching": True,
        "search_radius_m": 1000,
        "max_radius_km": 1.0,
        "contract_params": strip_aux_fields(data["contract_params"]),
    }

    

    start_process = time.perf_counter()
    resp = requests.post(f"{ORACLE_URL}/processar_trajeto", json=payload, timeout=None)
    process_seconds = time.perf_counter() - start_process
    if resp.status_code != 200:
        raise RuntimeError(f"oracle /processar_trajeto error: {resp.status_code} - {resp.text}")

    body = resp.json()
    options = body.get("opcoes", [])
    if not options:
        raise RuntimeError("oracle returned no options")

    selected = max(
        options,
        key=lambda opt: int(opt["monetizacao"]["private_final_e1_micro"]),
    )
    final_micro = int(selected["monetizacao"]["private_final_e1_micro"])
    if final_micro <= 0:
        e1_original_micro = int(body["original"].get("e1_micro", 0))
        return {
            "tx_method": "oracle_cancelled",
            "tx_hash": None,
            "tx_status": 0,
            "tx_seconds": round(process_seconds, 6),
            "tx_wait_seconds": None,
            "gas_used": None,
            "effective_gas_price": None,
            "tx_fee_wei": None,
            "block_number": None,
            "e1_original_micro": e1_original_micro,
            "e1_after_micro": 0,
            "e1_original_brl": round(e1_original_micro / 1e6, 6),
            "e1_after_brl": 0.0,
            "oracle_process_seconds": round(process_seconds, 6),
            "oracle_confirm_seconds": None,
            "zkp_enabled": None,
            "zk_proof_seconds": None,
            "error": "oracle_offsets_zero",
            "_redeem_item": None,
        }

    option_index = int(selected.get("option_index", 1))
    confirm_payload = {
        "request_id": body["request_id"],
        "option_index": option_index,
    }
    if final_micro <= 0 and MIN_VALUE_MICRO > 0:
        confirm_payload["min_value_micro"] = MIN_VALUE_MICRO

    start_confirm = time.perf_counter()
    conf = requests.post(f"{ORACLE_URL}/confirmar_opcao", json=confirm_payload, timeout=None)
    confirm_seconds = time.perf_counter() - start_confirm
    if conf.status_code != 200:
        raise RuntimeError(f"oracle /confirmar_opcao error: {conf.status_code} - {conf.text}")

    conf_body = conf.json()
    tx_hash = conf_body["tx_hashes"][0]
    receipt, receipt_wait = wait_for_receipt(w3, tx_hash, TX_RECEIPT_TIMEOUT)

    status = int(receipt.get("status", 0))
    gas_used = int(receipt.get("gasUsed", 0))
    effective_gas_price = int(receipt.get("effectiveGasPrice", receipt.get("gasPrice", 0)))
    tx_fee = gas_used * effective_gas_price

    e1_original_micro = int(body["original"].get("e1_micro", 0))
    e1_after_micro = int(conf_body.get("monetizacao_e1_micro", 0))

    tx_wait_seconds = conf_body.get("tx_wait_seconds")
    if tx_wait_seconds is None:
        tx_wait_seconds = receipt_wait

    redeem_item = None
    poseidon_root = conf_body.get("poseidon_root")
    if poseidon_root and status == 1:
        redeem_item = {
            "poseidon_root": poseidon_root,
            "trajectory": data["trajectory"],
            "vehicle_id": data["vehicle_id"],
        }

    return {
        "tx_method": "calculateAndMintWithZK",
        "tx_hash": tx_hash,
        "tx_status": status,
        "tx_seconds": round(confirm_seconds, 6),
        "tx_wait_seconds": round(float(tx_wait_seconds), 6),
        "gas_used": gas_used,
        "effective_gas_price": effective_gas_price,
        "tx_fee_wei": tx_fee,
        "block_number": int(receipt.get("blockNumber", 0)),
        "e1_original_micro": e1_original_micro,
        "e1_after_micro": e1_after_micro,
        "e1_original_brl": round(e1_original_micro / 1e6, 6),
        "e1_after_brl": round(e1_after_micro / 1e6, 6),
        "oracle_process_seconds": round(process_seconds, 6),
        "oracle_confirm_seconds": round(confirm_seconds, 6),
        "zkp_enabled": conf_body.get("zkp_enabled"),
        "zk_proof_seconds": conf_body.get("zk_proof_seconds"),
        "error": None,
        "_redeem_item": redeem_item,
    }


def oracle_direto_run(
    data: Dict[str, Any],
    deployment: Dict[str, Any],
    w3: Web3,
) -> Dict[str, Any]:
    """
    Envia o trajeto original ao oraculo via /registrar_trajeto (sem ofuscacao).
    O oraculo calcula a monetizacao e registra na blockchain com ZKP.
    O redeem posterior funciona da mesma forma que no cenario oracle.
    """
    payload = {
        "trajetoria": data["trajectory"],
        "vehicle_id": data["vehicle_id"],
        "contract_params": strip_aux_fields(data["contract_params"]),
    }
    if MIN_VALUE_MICRO > 0:
        payload["min_value_micro"] = MIN_VALUE_MICRO

    start_process = time.perf_counter()
    resp = requests.post(f"{ORACLE_URL}/registrar_trajeto", json=payload, timeout=None)
    process_seconds = time.perf_counter() - start_process
    if resp.status_code != 200:
        raise RuntimeError(f"oracle /registrar_trajeto error: {resp.status_code} - {resp.text}")

    body = resp.json()
    tx_hash = body["tx_hashes"][0]
    receipt, receipt_wait = wait_for_receipt(w3, tx_hash, TX_RECEIPT_TIMEOUT)

    status = int(receipt.get("status", 0))
    gas_used = int(receipt.get("gasUsed", 0))
    effective_gas_price = int(receipt.get("effectiveGasPrice", receipt.get("gasPrice", 0)))
    tx_fee = gas_used * effective_gas_price

    e1_micro = int(body.get("monetizacao_e1_micro", 0))

    tx_wait_seconds = body.get("tx_wait_seconds") or receipt_wait

    redeem_item = None
    poseidon_root = body.get("poseidon_root")
    if poseidon_root and status == 1:
        redeem_item = {
            "poseidon_root": poseidon_root,
            "trajectory": data["trajectory"],
            "vehicle_id": data["vehicle_id"],
        }

    return {
        "tx_method": "calculateAndMintWithZK",
        "tx_hash": tx_hash,
        "tx_status": status,
        "tx_seconds": round(process_seconds, 6),
        "tx_wait_seconds": round(float(tx_wait_seconds), 6),
        "gas_used": gas_used,
        "effective_gas_price": effective_gas_price,
        "tx_fee_wei": tx_fee,
        "block_number": int(receipt.get("blockNumber", 0)),
        "e1_original_micro": e1_micro,
        "e1_after_micro": e1_micro,
        "e1_original_brl": round(e1_micro / 1e6, 6),
        "e1_after_brl": round(e1_micro / 1e6, 6),
        "oracle_process_seconds": round(process_seconds, 6),
        "oracle_confirm_seconds": None,
        "zkp_enabled": body.get("zkp_enabled"),
        "zk_proof_seconds": body.get("zk_proof_seconds"),
        "error": None,
        "_redeem_item": redeem_item,
    }


def build_redeem_queue_from_csv(
    csv_files: List[Path],
    contract,
    recipient: str,
) -> List[Dict[str, Any]]:
    """
    Constrói a fila de redeem diretamente dos CSVs, sem depender do cenário oracle.

    Para cada CSV:
      1. Lê a trajetória original.
      2. Calcula o poseidon_root via prover ZK (determinístico para a mesma trajetória).
      3. Verifica no contrato se o root está registrado e ainda não resgatado.
      4. Se sim, adiciona à fila.

    Permite executar redeem/redeem_pseudonym de forma independente.
    """
    zk_dir = resolve_zk_dir(None)
    queue: List[Dict[str, Any]] = []

    print(f"[redeem] construindo fila a partir de {len(csv_files)} arquivo(s)...")
    for idx, csv_path in enumerate(csv_files, start=1):
        try:
            data = load_data_file(csv_path)
            trajectory = data["trajectory"]
            vehicle_id = data["vehicle_id"]

            # poseidon_root e determinístico para a mesma trajetória + recipient
            zk_nonce = 0  # nonce fixo apenas para obter o root; o redeem usará nonce real
            zk_result = generate_zk_proof(
                trajectory=trajectory,
                recipient=recipient,
                nonce=zk_nonce,
                zk_dir=zk_dir,
            )
            poseidon_root = zk_result["poseidon_root"]

            # Verificar no contrato
            if hasattr(contract.functions, "isPoseidonRootRegistered"):
                if not contract.functions.isPoseidonRootRegistered(poseidon_root).call():
                    print(f"[redeem] {csv_path.name}: poseidonRoot nao registrado, pulando.")
                    continue
            if hasattr(contract.functions, "redeemedPoseidonRoots"):
                if contract.functions.redeemedPoseidonRoots(poseidon_root).call():
                    print(f"[redeem] {csv_path.name}: poseidonRoot ja resgatado, pulando.")
                    continue

            csv_index = int(csv_path.stem.split("_")[-1]) if "_" in csv_path.stem else idx
            queue.append({
                "poseidon_root": poseidon_root,
                "trajectory": trajectory,
                "vehicle_id": vehicle_id,
                "csv_file": csv_path.name,
                "csv_index": csv_index,
                "repeat_index": 1,
            })
            print(f"[redeem] {csv_path.name}: adicionado à fila (root={hex(poseidon_root) if isinstance(poseidon_root, int) else poseidon_root})")

        except Exception as exc:
            print(f"[redeem] {csv_path.name}: erro ao processar — {exc}")

    print(f"[redeem] fila construída: {len(queue)} item(s) prontos para resgate.")
    return queue


def redeem_zk_run(
    item: Dict[str, Any],
    deployment: Dict[str, Any],
    w3: Web3,
    contract,
    nonce_cache: Dict[str, int],
    private_key: str,
) -> Dict[str, Any]:
    def parse_uint(value: Any) -> int:
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            return int(value, 0)
        raise ValueError(f"Valor numerico invalido: {value}")

    if not hasattr(contract.functions, "redeemWithZK"):
        raise RuntimeError("Contrato nao suporta redeemWithZK")

    poseidon_root = item["poseidon_root"]
    trajectory = item["trajectory"]

    if hasattr(contract.functions, "isPoseidonRootRegistered"):
        if not contract.functions.isPoseidonRootRegistered(poseidon_root).call():
            raise RuntimeError("poseidonRoot nao registrado")
    if hasattr(contract.functions, "redeemedPoseidonRoots"):
        if contract.functions.redeemedPoseidonRoots(poseidon_root).call():
            raise RuntimeError("poseidonRoot ja resgatado")

    token_id = None
    amount = None
    if hasattr(contract.functions, "poseidonRootToTokenId"):
        token_id = int(contract.functions.poseidonRootToTokenId(poseidon_root).call())
        if token_id > 0:
            try:
                calc = contract.functions.getCalculationDetails(token_id).call()
                amount = int(calc[5])
            except Exception:
                amount = None

    recipient = Account.from_key(private_key).address
    zk_nonce = int(time.time_ns())
    zk_dir = resolve_zk_dir(None)
    proof_start = time.perf_counter()
    zk_result = generate_zk_proof(
        trajectory=trajectory,
        recipient=recipient,
        nonce=zk_nonce,
        zk_dir=zk_dir,
    )
    zk_proof_seconds = time.perf_counter() - proof_start

    proof = zk_result["proof"]
    proof_a = [parse_uint(x) for x in proof["a"]]
    proof_b = [
        [parse_uint(x) for x in proof["b"][0]],
        [parse_uint(x) for x in proof["b"][1]],
    ]
    proof_c = [parse_uint(x) for x in proof["c"]]

    tx_result = send_contract_tx(
        w3=w3,
        contract=contract,
        method_name="redeemWithZK",
        args=[poseidon_root, zk_nonce, proof_a, proof_b, proof_c],
        private_key=private_key,
        chain_id=deployment.get("chain_id"),
        gas_price_gwei=deployment.get("gas_price_gwei", 0),
        nonce_cache=nonce_cache,
    )

    receipt = tx_result["receipt"]
    status = int(receipt.get("status", 0))
    gas_used = int(receipt.get("gasUsed", 0))
    effective_gas_price = int(receipt.get("effectiveGasPrice", receipt.get("gasPrice", 0)))
    tx_fee = gas_used * effective_gas_price

    if amount is None:
        amount = 0

    return {
        "tx_method": "redeemWithZK",
        "tx_hash": tx_result["tx_hash"],
        "tx_status": status,
        "tx_seconds": round(tx_result["tx_seconds"], 6),
        "tx_wait_seconds": round(tx_result["tx_seconds"], 6),
        "gas_used": gas_used,
        "effective_gas_price": effective_gas_price,
        "tx_fee_wei": tx_fee,
        "block_number": int(receipt.get("blockNumber", 0)),
        "e1_original_micro": int(amount),
        "e1_after_micro": int(amount),
        "e1_original_brl": round(int(amount) / 1e6, 6),
        "e1_after_brl": round(int(amount) / 1e6, 6),
        "oracle_process_seconds": None,
        "oracle_confirm_seconds": None,
        "zkp_enabled": True,
        "zk_proof_seconds": round(zk_proof_seconds, 6),
        "error": None,
    }


def percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    k = int(round((pct / 100.0) * (len(values) - 1)))
    return float(values[k])


def ensure_results_dir() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def check_oracle_connectivity() -> None:
    """Verifica se o oraculo esta acessivel antes de iniciar o cenario oracle.
    Lanca RuntimeError com mensagem clara se nao conseguir conectar."""
    try:
        resp = requests.get(f"{ORACLE_URL}/health", timeout=5)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Oraculo respondeu com status {resp.status_code} em GET /health. "
                f"Verifique se o oraculo esta configurado corretamente."
            )
        print(f"[oracle] Conectado em {ORACLE_URL} (status: ok)")
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            f"Nao foi possivel conectar ao oraculo em {ORACLE_URL}. "
            f"Inicie o oraculo antes de executar o cenario oracle."
        )
    except requests.exceptions.Timeout:
        raise RuntimeError(
            f"Timeout ao conectar ao oraculo em {ORACLE_URL}. "
            f"Verifique se o oraculo esta rodando e acessivel."
        )


def write_row(path: Path, row: Dict[str, Any]) -> None:
    file_exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def build_summary_row(
    run_id: str,
    scenario: str,
    scenario_start: float,
    total_sent: int,
    success_count: int,
    fail_count: int,
    latency_values: List[float],
    interrupted: bool = False,
) -> Dict[str, Any]:
    """Build a summary row from accumulated scenario stats."""
    duration = time.perf_counter() - scenario_start
    latency_avg = sum(latency_values) / len(latency_values) if latency_values else 0.0
    latency_p95 = percentile(latency_values, 95.0) if latency_values else 0.0
    latency_max = max(latency_values) if latency_values else 0.0
    throughput = (success_count / duration) if duration > 0 else 0.0

    return {
        "record_type": "summary",
        "run_id": run_id,
        "scenario": scenario + ("_interrupted" if interrupted else ""),
        "csv_file": None,
        "csv_index": None,
        "repeat_index": None,
        "tx_method": None,
        "tx_hash": None,
        "tx_status": None,
        "tx_seconds": None,
        "tx_wait_seconds": None,
        "gas_used": None,
        "effective_gas_price": None,
        "tx_fee_wei": None,
        "block_number": None,
        "e1_original_micro": None,
        "e1_after_micro": None,
        "e1_original_brl": None,
        "e1_after_brl": None,
        "oracle_process_seconds": None,
        "oracle_confirm_seconds": None,
        "zkp_enabled": None,
        "zk_proof_seconds": None,
        "error": "interrupted" if interrupted else None,
        "total_sent": total_sent,
        "success_count": success_count,
        "fail_count": fail_count,
        "duration_seconds": round(duration, 6),
        "throughput_tps": round(throughput, 6),
        "latency_avg": round(latency_avg, 6),
        "latency_p95": round(latency_p95, 6),
        "latency_max": round(latency_max, 6),
    }


def run_scenario(
    scenario: str,
    csv_files: List[Path],
    deployment: Dict[str, Any],
    w3: Web3,
    contract,
    run_id: str,
    redeem_queue: List[Dict[str, Any]],
) -> None:
    scenario_start = time.perf_counter()
    latency_values: List[float] = []
    total_sent = 0
    success_count = 0
    fail_count = 0
    nonce_cache: Dict[str, int] = {}

    if scenario in ("direct", "pseudonym", "direct_pseudonym"):
        if scenario == "direct" and not USER_PRIVATE_KEY:
            raise ValueError("BENCH_USER_PRIVATE_KEY is required for direct scenario")
        if scenario in ("pseudonym", "direct_pseudonym"):
            if not PSEUDONYM_PRIVATE_KEY and not PSEUDONYM_SEED_FILE:
                raise ValueError("Provide BENCH_PSEUDONYM_PRIVATE_KEY or BENCH_PSEUDONYM_SEED_FILE")

    if scenario in ("redeem", "redeem_pseudonym"):
        if scenario == "redeem_pseudonym":
            # resolve pseudonym key, measuring generation time
            if PSEUDONYM_PRIVATE_KEY:
                redeem_key = PSEUDONYM_PRIVATE_KEY
                redeem_pseudonym_gen_seconds = None
            elif PSEUDONYM_SEED_FILE:
                pseudonym_gen_start = time.perf_counter()
                _, redeem_key = resolve_pseudonym_private_key(
                    seed_file=PSEUDONYM_SEED_FILE,
                    hd_index=PSEUDONYM_HD_INDEX,
                )
                redeem_pseudonym_gen_seconds = round(time.perf_counter() - pseudonym_gen_start, 6)
            else:
                raise ValueError(
                    "BENCH_PSEUDONYM_PRIVATE_KEY or BENCH_PSEUDONYM_SEED_FILE is required for redeem_pseudonym scenario"
                )
        else:
            redeem_key = REDEEM_PRIVATE_KEY or USER_PRIVATE_KEY
            redeem_pseudonym_gen_seconds = None
            if not redeem_key:
                raise ValueError("BENCH_REDEEM_PRIVATE_KEY or BENCH_USER_PRIVATE_KEY is required for redeem scenario")

        items = list(redeem_queue)
        if not items:
            # Fila vazia: tentar construir independentemente a partir dos CSVs
            print(f"[redeem] redeem_queue vazia — tentando construir a partir dos CSVs em {DATA_DIR}...")
            items = build_redeem_queue_from_csv(
                csv_files=csv_files,
                contract=contract,
                recipient=Account.from_key(redeem_key).address,
            )

        if REDEEM_LIMIT > 0:
            items = items[:REDEEM_LIMIT]

        if not items:
            summary_row = build_summary_row(
                run_id, scenario, scenario_start,
                total_sent=0, success_count=0, fail_count=0,
                latency_values=[],
            )
            summary_row["error"] = "no_redeem_items"
            write_row(RESULTS_CSV, summary_row)
            write_row(SUMMARY_CSV, summary_row)
            return

        try:
            for idx, item in enumerate(items, start=1):
                total_sent += 1
                row: Dict[str, Any] = {
                    "record_type": "tx",
                    "run_id": run_id,
                    "scenario": scenario,
                    "csv_file": item.get("csv_file"),
                    "csv_index": item.get("csv_index"),
                    "repeat_index": item.get("repeat_index", idx),
                }
                try:
                    # for redeem_pseudonym, derive a fresh pseudonym per item
                    if scenario == "redeem_pseudonym" and PSEUDONYM_SEED_FILE:
                        current_hd_index = PSEUDONYM_HD_INDEX + (total_sent - 1)
                        pseudonym_gen_start = time.perf_counter()
                        _, redeem_key = resolve_pseudonym_private_key(
                            seed_file=PSEUDONYM_SEED_FILE,
                            hd_index=current_hd_index,
                        )
                        redeem_pseudonym_gen_seconds = round(time.perf_counter() - pseudonym_gen_start, 6)
                    result = redeem_zk_run(item, deployment, w3, contract, nonce_cache, redeem_key)
                    result["pseudonym_gen_seconds"] = redeem_pseudonym_gen_seconds
                    row.update(result)
                    status = int(result.get("tx_status", 0))
                    if status == 1:
                        success_count += 1
                        latency_values.append(float(result.get("tx_wait_seconds") or 0.0))
                    else:
                        fail_count += 1
                except Exception as exc:
                    fail_count += 1
                    print(f"\n[erro] {csv_path.name} rep={rep}: {exc}", flush=True)
                    row.update({
                        "tx_method": None, "tx_hash": None, "tx_status": 0,
                        "tx_seconds": None, "tx_wait_seconds": None,
                        "gas_used": None, "effective_gas_price": None, "tx_fee_wei": None,
                        "block_number": None, "e1_original_micro": None, "e1_after_micro": None,
                        "e1_original_brl": None, "e1_after_brl": None,
                        "oracle_process_seconds": None, "oracle_confirm_seconds": None,
                        "zkp_enabled": None, "zk_proof_seconds": None,
                        "pseudonym_gen_seconds": None, "error": str(exc),
                    })
                write_row(RESULTS_CSV, row)

        except KeyboardInterrupt:
            print(f"\n[!] Interrupted during scenario '{scenario}'. Saving partial summary...")
            summary_row = build_summary_row(
                run_id, scenario, scenario_start,
                total_sent, success_count, fail_count,
                latency_values, interrupted=True,
            )
            write_row(RESULTS_CSV, summary_row)
            write_row(SUMMARY_CSV, summary_row)
            raise

        summary_row = build_summary_row(
            run_id, scenario, scenario_start,
            total_sent, success_count, fail_count, latency_values,
        )
        write_row(RESULTS_CSV, summary_row)
        write_row(SUMMARY_CSV, summary_row)
        return

    # --- scenarios: direct, pseudonym, direct_pseudonym, oracle, oracle_direto ---
    if scenario in ("oracle", "oracle_direto"):
        check_oracle_connectivity()

    try:
        for csv_path in csv_files:
            data = load_data_file(csv_path)
            csv_index = int(csv_path.stem.split("_")[-1]) if "_" in csv_path.stem else 0

            for rep in range(1, REPEAT_PER_CSV + 1):
                total_sent += 1
                row: Dict[str, Any] = {
                    "record_type": "tx",
                    "run_id": run_id,
                    "scenario": scenario,
                    "csv_file": csv_path.name,
                    "csv_index": csv_index,
                    "repeat_index": rep,
                }
                try:
                    if scenario == "oracle":
                        result = oracle_offset_run(data, deployment, w3)
                        redeem_item = result.pop("_redeem_item", None)
                        if redeem_item:
                            redeem_item["csv_file"] = csv_path.name
                            redeem_item["csv_index"] = csv_index
                            redeem_item["repeat_index"] = rep
                            redeem_queue.append(redeem_item)
                    elif scenario == "oracle_direto":
                        result = oracle_direto_run(data, deployment, w3)
                        redeem_item = result.pop("_redeem_item", None)
                        if redeem_item:
                            redeem_item["csv_file"] = csv_path.name
                            redeem_item["csv_index"] = csv_index
                            redeem_item["repeat_index"] = rep
                            redeem_queue.append(redeem_item)
                    elif scenario == "direct":
                        result = direct_or_pseudonym_run(
                            scenario, data, deployment, w3, contract, nonce_cache, USER_PRIVATE_KEY,
                        )
                    elif scenario in ("pseudonym", "direct_pseudonym"):
                        # A chave pseudonima e apenas o recipient do NFT.
                        # Quem assina a transacao e USER_PRIVATE_KEY (carteira autorizada).
                        if not USER_PRIVATE_KEY:
                            raise ValueError("BENCH_USER_PRIVATE_KEY e obrigatorio para cenarios pseudonym/direct_pseudonym (assina a transacao)")
                        pseudonym_key = PSEUDONYM_PRIVATE_KEY
                        pseudonym_gen_seconds = None
                        if not pseudonym_key:
                            # Derivar pseudonimo diferente por iteracao
                            current_hd_index = PSEUDONYM_HD_INDEX + (total_sent - 1)
                            pseudonym_gen_start = time.perf_counter()
                            _, pseudonym_key = resolve_pseudonym_private_key(
                                seed_file=PSEUDONYM_SEED_FILE,
                                hd_index=current_hd_index,
                            )
                            pseudonym_gen_seconds = round(time.perf_counter() - pseudonym_gen_start, 6)
                        # signing_key = USER_PRIVATE_KEY (autorizado), recipient = pseudonimo
                        result = direct_or_pseudonym_run(
                            scenario, data, deployment, w3, contract, nonce_cache,
                            private_key=USER_PRIVATE_KEY,
                            recipient_key=pseudonym_key,
                        )
                        result["pseudonym_gen_seconds"] = pseudonym_gen_seconds
                    else:
                        raise ValueError(f"Unknown scenario: {scenario} (available: direct, pseudonym, direct_pseudonym, oracle, oracle_direto, redeem, redeem_pseudonym)")

                    row.update(result)
                    status = int(result.get("tx_status", 0))
                    if status == 1:
                        success_count += 1
                        latency_values.append(float(result.get("tx_wait_seconds") or 0.0))
                    else:
                        if result.get("error") != "oracle_offsets_zero":
                            fail_count += 1
                    write_row(RESULTS_CSV, row)
                except requests.exceptions.ConnectionError as exc:
                    # oracle went down mid-run — stop the scenario immediately
                    error_msg = f"Conexao com oraculo perdida em {ORACLE_URL}: {exc}"
                    print(f"\n[!] {error_msg}")
                    print(f"[!] Interrompendo cenario '{scenario}' e salvando summary parcial...")
                    fail_count += 1
                    row.update({
                        "tx_method": None, "tx_hash": None, "tx_status": 0,
                        "tx_seconds": None, "tx_wait_seconds": None,
                        "gas_used": None, "effective_gas_price": None, "tx_fee_wei": None,
                        "block_number": None, "e1_original_micro": None, "e1_after_micro": None,
                        "e1_original_brl": None, "e1_after_brl": None,
                        "oracle_process_seconds": None, "oracle_confirm_seconds": None,
                        "zkp_enabled": None, "zk_proof_seconds": None,
                        "pseudonym_gen_seconds": None, "error": error_msg,
                    })
                    write_row(RESULTS_CSV, row)
                    summary_row = build_summary_row(
                        run_id, scenario, scenario_start,
                        total_sent, success_count, fail_count,
                        latency_values, interrupted=True,
                    )
                    write_row(RESULTS_CSV, summary_row)
                    write_row(SUMMARY_CSV, summary_row)
                    return
                except Exception as exc:
                    fail_count += 1
                    print(f"\n[erro] {csv_path.name} rep={rep}: {exc}", flush=True)
                    row.update({
                        "tx_method": None, "tx_hash": None, "tx_status": 0,
                        "tx_seconds": None, "tx_wait_seconds": None,
                        "gas_used": None, "effective_gas_price": None, "tx_fee_wei": None,
                        "block_number": None, "e1_original_micro": None, "e1_after_micro": None,
                        "e1_original_brl": None, "e1_after_brl": None,
                        "oracle_process_seconds": None, "oracle_confirm_seconds": None,
                        "zkp_enabled": None, "zk_proof_seconds": None,
                        "pseudonym_gen_seconds": None, "error": str(exc),
                    })
                    write_row(RESULTS_CSV, row)

    except KeyboardInterrupt:
        print(f"\n[!] Interrupted during scenario '{scenario}'. Saving partial summary...")
        summary_row = build_summary_row(
            run_id, scenario, scenario_start,
            total_sent, success_count, fail_count,
            latency_values, interrupted=True,
        )
        write_row(RESULTS_CSV, summary_row)
        write_row(SUMMARY_CSV, summary_row)
        raise

    summary_row = build_summary_row(
        run_id, scenario, scenario_start,
        total_sent, success_count, fail_count, latency_values,
    )
    write_row(RESULTS_CSV, summary_row)
    write_row(SUMMARY_CSV, summary_row)


def main() -> None:
    if not DEPLOYMENT_FILE.exists():
        raise FileNotFoundError(f"deployment file not found: {DEPLOYMENT_FILE}")

    csv_files = list_csv_files(DATA_DIR)
    if not csv_files:
        raise FileNotFoundError(f"no CSV files found in {DATA_DIR}")

    deployment = load_deployment_info(str(DEPLOYMENT_FILE))
    rpc_url = deployment.get("rpc_url", "http://localhost:8545")
    w3 = get_web3(rpc_url)
    _ = w3.eth.chain_id
    _ = w3.eth.block_number

    contract = w3.eth.contract(address=deployment["contract_address"], abi=deployment["abi"])

    ensure_results_dir()
    run_id = uuid.uuid4().hex
    redeem_queue: List[Dict[str, Any]] = []

    try:
        for scenario in SCENARIOS:
            run_scenario(
                scenario=scenario,
                csv_files=csv_files,
                deployment=deployment,
                w3=w3,
                contract=contract,
                run_id=run_id,
                redeem_queue=redeem_queue,
            )
    except KeyboardInterrupt:
        print(f"\n[!] Benchmark cancelled. Partial results saved to: {RESULTS_CSV}")
        print(f"[!] Partial summary saved to: {SUMMARY_CSV}")
        sys.exit(1)

    print(f"Done. Results: {RESULTS_CSV} | Summary: {SUMMARY_CSV}")


if __name__ == "__main__":
    main()