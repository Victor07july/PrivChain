#!/usr/bin/env python3
"""
Servidor API do oraculo de privacidade por offset.

Endpoints:
- POST /processar_trajeto
- POST /confirmar_opcao
- GET /health
"""

import argparse
import csv
import hashlib
import json
import logging
import math
import os
import random
import subprocess
import tempfile
import time
import traceback
import uuid
from typing import Any, Dict, List, Optional, Tuple

import uvicorn
from eth_account import Account
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from web3 import Web3

from blockchain_sender import load_deployment_info, send_oracle_results

try:
    import osmnx as ox
    from shapely.geometry import Point

    # Timeout da requisicao HTTP a Overpass API (padrao: 180s — muito alto).
    # Reduza via variavel de ambiente ORACLE_OSM_TIMEOUT se necessario.
    ox.settings.requests_timeout = int(os.environ.get("ORACLE_OSM_TIMEOUT", "30"))
    # Propagar logs do osmnx para o handler raiz do Python (capturado pelo FileHandler).
    ox.settings.log_console = False  # evitar duplicar no terminal
    ox.settings.log_file = False     # gerenciamos o arquivo de log manualmente

    MAP_MATCHING_AVAILABLE = True
except ImportError:
    MAP_MATCHING_AVAILABLE = False


EARTH_RADIUS_KM = 6371.0
DEFAULT_ATTEMPTS = 20
DEFAULT_TOP_K = 5

DEFAULT_ROAD_GASOLINE_KM_L = 11.3
DEFAULT_CITY_GASOLINE_KM_L = 10.3
DEFAULT_CARBON_PRICE_BRL_TON = 67.13 * 6.17  # ~414.19 BRL/ton (€67.13 * 6.17 BRL/€)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5000

DEFAULT_ZK_MAX_POINTS = 500
DEFAULT_ZK_INPUT_SCALE = 1e7

# Defina como True para salvar automaticamente CSV e JSON do trajeto ofuscado
# em data/trajetos_ofuscados/ a cada confirmacao de opcao.
SAVE_OBFUSCATED_TRIPS = True


class ContractParamsInput(BaseModel):
    highwayDistance: Optional[int] = None
    cityDistance: Optional[int] = None
    ethanolPercent: Optional[int] = 0
    roadGasoline: Optional[int] = None
    roadEthanol: Optional[int] = 0
    cityGasoline: Optional[int] = None
    cityEthanol: Optional[int] = 0
    realCO2Emissions: Optional[int] = None
    carbonPricePerTon: Optional[int] = None


class ProcessarTrajetoRequest(BaseModel):
    trajetoria: List[List[float]] = Field(..., min_length=2)
    vehicle_id: Optional[str] = "veh0"
    attempts: int = DEFAULT_ATTEMPTS
    top_k: int = DEFAULT_TOP_K
    max_radius_km: float = 2.0
    enable_map_matching: bool = False
    search_radius_m: int = 3000
    contract_params: Optional[ContractParamsInput] = None


class ConfirmarOpcaoRequest(BaseModel):
    request_id: str
    option_index: int = Field(..., ge=1)
    min_value_micro: Optional[int] = None


app = FastAPI(title="Oracle Offset API", version="1.0.0")

logger = logging.getLogger("uvicorn.error")

# Pendencias em memoria: request_id -> dados da proposta
PENDING_SELECTIONS: Dict[str, Dict[str, Any]] = {}


# -----------------------------------------------------------------------
# Logging para arquivo
# -----------------------------------------------------------------------
def _get_log_dir() -> str:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(script_dir, "..", "data"))


def setup_file_logging() -> Optional[str]:
    """
    Adiciona um FileHandler ao logger raiz para persistir todos os logs
    em data/oraculo.log (ou no caminho definido por ORACLE_LOG_FILE).

    Retorna o caminho do arquivo de log configurado, ou None se falhou.
    """
    log_path = os.environ.get("ORACLE_LOG_FILE", "").strip()
    if not log_path:
        log_dir = _get_log_dir()
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "oraculo.log")

    try:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(formatter)

        # Anexar ao logger raiz para capturar uvicorn, fastapi e osmnx
        root_logger = logging.getLogger()
        root_logger.addHandler(file_handler)
        # Garantir nivel minimo no root para que DEBUG/INFO passem
        if root_logger.level == logging.NOTSET or root_logger.level > logging.DEBUG:
            root_logger.setLevel(logging.DEBUG)

        return log_path
    except Exception as exc:
        # Nao impedir inicializacao por falha de log
        print(f"[oraculo] AVISO: nao foi possivel configurar log em arquivo: {exc}", flush=True)
        return None


# -----------------------------------------------------------------------
# Global exception handler — loga traceback completo e retorna detalhe
# -----------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    tb = traceback.format_exc()
    logger.error(
        "[oraculo] ERRO nao tratado em %s %s\n%s",
        request.method,
        request.url.path,
        tb,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": str(exc),
            "traceback": tb,
        },
    )


def validate_environment() -> List[str]:
    """Valida variaveis de ambiente obrigatorias e retorna lista de avisos/erros."""
    issues = []

    deployment_file = os.environ.get("ORACLE_DEPLOYMENT_FILE", "").strip()
    oracle_key = os.environ.get("ORACLE_PRIVATE_KEY", "").strip()
    zkp_enabled = os.environ.get("ORACLE_ZKP_ENABLED", "1").strip().lower() not in ("0", "false", "no")

    if not deployment_file:
        issues.append("ORACLE_DEPLOYMENT_FILE nao definido")
    elif not os.path.exists(deployment_file):
        issues.append(f"ORACLE_DEPLOYMENT_FILE nao encontrado: {deployment_file}")
    else:
        try:
            deployment = load_deployment_info(deployment_file)
            rpc_url = deployment.get("rpc_url", "http://localhost:8545")
            w3 = Web3(Web3.HTTPProvider(rpc_url))
            _ = w3.eth.chain_id
            _ = w3.eth.block_number
        except Exception as exc:
            issues.append(f"Falha ao carregar/conectar deployment_file={deployment_file}: {exc}")

    if not oracle_key:
        issues.append("ORACLE_PRIVATE_KEY nao definido")
    else:
        try:
            addr = Account.from_key(oracle_key).address
            logger.info("[oraculo] carteira do oraculo: %s", addr)
        except Exception as exc:
            issues.append(f"ORACLE_PRIVATE_KEY invalida: {exc}")

    if zkp_enabled:
        zk_dir = resolve_zk_dir()
        prover_script = os.path.join(zk_dir, "scripts", "prove.js")
        if not os.path.exists(prover_script):
            issues.append(
                f"ZKP habilitado mas prover nao encontrado: {prover_script} "
                f"(defina ORACLE_ZKP_DIR ou desative com ORACLE_ZKP_ENABLED=0)"
            )
        else:
            logger.info("[oraculo] ZKP habilitado, prover encontrado em: %s", prover_script)
    else:
        logger.info("[oraculo] ZKP desabilitado (ORACLE_ZKP_ENABLED=0)")

    return issues


def log_map_matching_status(enabled: bool, radius_m: int) -> None:
    if enabled:
        if MAP_MATCHING_AVAILABLE:
            logger.warning("[oraculo] MAP MATCHING ATIVADO (raio=%sm)", radius_m)
        else:
            logger.warning(
                "[oraculo] MAP MATCHING ATIVADO, mas indisponivel (osmnx/shapely nao instalados)"
            )
    else:
        logger.warning("[oraculo] MAP MATCHING DESATIVADO")


def resolve_zk_dir() -> str:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_dir = os.path.abspath(os.path.join(script_dir, "..", "zkp"))
    return os.environ.get("ORACLE_ZKP_DIR", default_dir)


def log_oracle_runtime_info() -> None:
    zkp_dir = resolve_zk_dir()
    zkp_enabled = is_zk_enabled()
    logger.info("[oraculo] zkp_enabled=%s zkp_dir=%s", zkp_enabled, zkp_dir)

    deployment_file = os.environ.get("ORACLE_DEPLOYMENT_FILE")
    if not deployment_file:
        logger.warning("[oraculo] ORACLE_DEPLOYMENT_FILE nao configurado")
        return

    try:
        deployment = load_deployment_info(deployment_file)
        contract_address = deployment["contract_address"]
        rpc_url = deployment.get("rpc_url", "http://localhost:8545")
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        try:
            _ = w3.eth.chain_id
            _ = w3.eth.block_number
        except Exception as exc:
            logger.warning("[oraculo] RPC indisponivel para debug: %s", exc)
            return
        contract = w3.eth.contract(address=contract_address, abi=deployment["abi"])
        zk_verifier = None
        if hasattr(contract.functions, "zkVerifier"):
            zk_verifier = contract.functions.zkVerifier().call()
        logger.info(
            "[oraculo] contract=%s rpc=%s zkVerifier=%s",
            contract_address,
            rpc_url,
            zk_verifier,
        )
    except Exception as exc:
        logger.warning("[oraculo] Falha ao carregar info do contrato: %s", exc)


@app.on_event("startup")
def on_startup() -> None:
    log_oracle_runtime_info()

    # Valida variaveis de ambiente e loga problemas encontrados
    issues = validate_environment()
    if issues:
        logger.error("[oraculo] PROBLEMAS DE CONFIGURACAO DETECTADOS NO STARTUP:")
        for issue in issues:
            logger.error("[oraculo]   - %s", issue)
        logger.error(
            "[oraculo] O servidor iniciou mas pode falhar ao processar requisicoes. "
            "Corrija as variaveis de ambiente acima."
        )
    else:
        logger.info("[oraculo] Configuracao validada com sucesso.")


def generate_zk_proof(
    trajectory: List[List[float]],
    recipient: str,
    nonce: int,
) -> Dict[str, Any]:
    if len(trajectory) > DEFAULT_ZK_MAX_POINTS:
        raise ValueError(
            f"Trajetoria excede maximo de {DEFAULT_ZK_MAX_POINTS} pontos para ZK"
        )

    zk_dir = resolve_zk_dir()
    prover_script = os.path.join(zk_dir, "scripts", "prove.js")
    if not os.path.exists(prover_script):
        raise FileNotFoundError(
            f"Prover ZK nao encontrado: {prover_script} (ORACLE_ZKP_DIR={zk_dir})"
        )

    payload = {
        "points": trajectory,
        "recipient": recipient,
        "nonce": str(nonce),
        "max_points": DEFAULT_ZK_MAX_POINTS,
        "scale": DEFAULT_ZK_INPUT_SCALE,
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, "zk_input.json")
        output_path = os.path.join(tmpdir, "zk_output.json")
        with open(input_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        try:
            subprocess.run(
                ["node", prover_script, "--input", input_path, "--output", output_path],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"Falha ao gerar prova ZK: {exc.stderr or exc.stdout}"
            ) from exc

        with open(output_path, "r", encoding="utf-8") as f:
            return json.load(f)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_KM * c


def trajectory_distance_km(points: List[List[float]]) -> float:
    if len(points) < 2:
        return 0.0

    total = 0.0
    for i in range(len(points) - 1):
        lat1, lon1 = points[i]
        lat2, lon2 = points[i + 1]
        total += haversine_km(lat1, lon1, lat2, lon2)
    return total


def normalize_point(point: List[float], decimals: int = 7) -> List[float]:
    return [round(float(point[0]), decimals), round(float(point[1]), decimals)]


def build_trajectory_hash(trajectory: List[List[float]]) -> str:
    payload = {
        "trajectory_original": [normalize_point(p) for p in trajectory],
    }
    canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def to_bytes32_hex(raw_hash: str) -> str:
    h = raw_hash.lower().replace("0x", "")
    if len(h) != 64:
        raise ValueError("hash_trajetoria_original deve ter 64 chars hex")
    int(h, 16)
    return "0x" + h


def generate_random_offset(max_radius_km: float, ref_lat: float) -> Tuple[float, float, float, float]:
    angle = random.uniform(0.0, 2.0 * math.pi)
    distance_km = math.sqrt(random.uniform(0.0, 1.0)) * max_radius_km

    dx_km = distance_km * math.cos(angle)
    dy_km = distance_km * math.sin(angle)

    offset_lat = dx_km / 111.32
    cos_lat = math.cos(math.radians(ref_lat))
    offset_lon = dy_km / (111.32 * cos_lat) if cos_lat != 0 else 0.0

    return offset_lat, offset_lon, distance_km, math.degrees(angle)


def apply_offset(points: List[List[float]], offset_lat: float, offset_lon: float) -> List[List[float]]:
    return [[p[0] + offset_lat, p[1] + offset_lon] for p in points]


def get_road_graph(center_lat: float, center_lon: float, search_radius_m: int):
    if not MAP_MATCHING_AVAILABLE:
        return None
    t0 = time.perf_counter()
    logger.info(
        "[map_matching] consultando Overpass API: centro=(%.6f, %.6f) raio=%sm",
        center_lat, center_lon, search_radius_m,
    )
    graph = ox.graph_from_point(
        (center_lat, center_lon),
        dist=search_radius_m,
        network_type="drive",
        simplify=False,
    )
    elapsed = time.perf_counter() - t0
    logger.info(
        "[map_matching] grafo obtido em %.2fs: %d nos, %d arestas",
        elapsed,
        len(graph.nodes),
        len(graph.edges),
    )
    return graph


def snap_point_to_road(graph, lat: float, lon: float) -> List[float]:
    if graph is None or not MAP_MATCHING_AVAILABLE:
        return [lat, lon]

    try:
        u, v, key = ox.distance.nearest_edges(graph, X=lon, Y=lat)
        edge_geom = graph.edges[u, v, key].get("geometry")
        if edge_geom is not None:
            projected = edge_geom.interpolate(edge_geom.project(Point(lon, lat)))
            return [float(projected.y), float(projected.x)]

        node = ox.distance.nearest_nodes(graph, X=lon, Y=lat)
        return [float(graph.nodes[node]["y"]), float(graph.nodes[node]["x"])]
    except Exception as exc:
        logger.warning("[map_matching] snap_point_to_road falhou em (%.6f, %.6f): %s", lat, lon, exc)
        return [lat, lon]


def maybe_map_match(points: List[List[float]], enabled: bool, search_radius_m: int) -> List[List[float]]:
    if not enabled or not points or not MAP_MATCHING_AVAILABLE:
        return points

    center_lat = sum(p[0] for p in points) / len(points)
    center_lon = sum(p[1] for p in points) / len(points)

    try:
        graph = get_road_graph(center_lat, center_lon, search_radius_m)
    except Exception as exc:
        logger.warning(
            "[map_matching] get_road_graph falhou (centro=(%.6f, %.6f) raio=%sm): %s",
            center_lat, center_lon, search_radius_m, exc,
        )
        return points

    return [snap_point_to_road(graph, p[0], p[1]) for p in points]


def privacy_diff_percent(orig_km: float, private_km: float) -> float:
    if orig_km <= 0:
        return 0.0
    return ((private_km - orig_km) / orig_km) * 100.0


def simulate_e1_value(contract_params: Dict[str, int]) -> int:
    road_gas_micro = int(contract_params.get("roadGasoline", 0))
    city_gas_micro = int(contract_params.get("cityGasoline", 0))
    price_micro = int(contract_params.get("carbonPricePerTon", 0))
    if road_gas_micro <= 0 or city_gas_micro <= 0 or price_micro <= 0:
        return 0

    highway_micro = int(contract_params.get("highwayDistance", 0))
    city_micro = int(contract_params.get("cityDistance", 0))
    real_co2_micro = int(contract_params.get("realCO2Emissions", 0))

    highway_km = highway_micro / 1e6
    city_km = city_micro / 1e6
    road_gas = road_gas_micro / 1e6
    city_gas = city_gas_micro / 1e6
    real_co2 = real_co2_micro / 1e6
    price = price_micro / 1e6

    emission_factor = 2310.0
    meta_highway = (highway_km / road_gas * emission_factor) if road_gas > 0 else 0.0
    meta_city = (city_km / city_gas * emission_factor) if city_gas > 0 else 0.0
    meta = meta_highway + meta_city

    diff = max(0.0, meta - real_co2)
    e1_brl = diff * price / 1_000_000.0
    return int(e1_brl * 1e6)


def compute_meta_diff(contract_params: Dict[str, int]) -> Tuple[int, int]:
    road_gas_micro = int(contract_params.get("roadGasoline", 0))
    city_gas_micro = int(contract_params.get("cityGasoline", 0))
    if road_gas_micro <= 0 or city_gas_micro <= 0:
        return 0, 0

    highway_micro = int(contract_params.get("highwayDistance", 0))
    city_micro = int(contract_params.get("cityDistance", 0))
    real_co2_micro = int(contract_params.get("realCO2Emissions", 0))

    highway_km = highway_micro / 1e6
    city_km = city_micro / 1e6
    road_gas = road_gas_micro / 1e6
    city_gas = city_gas_micro / 1e6
    real_co2 = real_co2_micro / 1e6

    emission_factor = 2310.0
    meta_highway = (highway_km / road_gas * emission_factor) if road_gas > 0 else 0.0
    meta_city = (city_km / city_gas * emission_factor) if city_gas > 0 else 0.0
    meta = meta_highway + meta_city

    diff = max(0.0, meta - real_co2)
    return int(meta * 1e6), int(diff * 1e6)


def split_city_highway(total_km: float) -> Tuple[float, float]:
    return total_km * 0.4, total_km * 0.6


def build_contract_params_from_trajectory(
    trajectory: List[List[float]],
    override: Optional[ContractParamsInput],
) -> Dict[str, int]:
    total_km = trajectory_distance_km(trajectory)
    city_km, highway_km = split_city_highway(total_km)

    default_real_co2_g = max(total_km * 120.0, 1.0)

    params = {
        "highwayDistance": int(highway_km * 1e6),
        "cityDistance": int(city_km * 1e6),
        "ethanolPercent": 0,
        "roadGasoline": int(DEFAULT_ROAD_GASOLINE_KM_L * 1e6),
        "roadEthanol": 0,
        "cityGasoline": int(DEFAULT_CITY_GASOLINE_KM_L * 1e6),
        "cityEthanol": 0,
        "realCO2Emissions": int(default_real_co2_g * 1e6),
        "carbonPricePerTon": int(DEFAULT_CARBON_PRICE_BRL_TON * 1e6),
    }

    if override is None:
        return params

    raw = override.model_dump(exclude_none=True)
    params.update({k: int(v) for k, v in raw.items()})
    return params


def derive_private_real_co2(original_real_co2: int, private_km: float, original_km: float) -> int:
    if original_km <= 0:
        return original_real_co2
    ratio = private_km / original_km
    return max(1, int(original_real_co2 * ratio))


def capped_private_value(original_value: int, private_diff_abs_percent: float, private_raw_value: int) -> int:
    base_cap = original_value * 0.9
    distance_penalty_ratio = max(0.0, 1.0 - (private_diff_abs_percent / 100.0))
    cap_rule = int(base_cap * distance_penalty_ratio)
    return max(0, min(private_raw_value, cap_rule))


def is_zk_enabled() -> bool:
    value = os.environ.get("ORACLE_ZKP_ENABLED", "1").strip().lower()
    return value not in ("0", "false", "no")


@app.get("/health")
def health() -> Dict[str, Any]:
    pending = len(PENDING_SELECTIONS)
    issues = validate_environment()
    logger.info("[oraculo] healthcheck pending_requests=%s config_issues=%s", pending, len(issues))
    return {
        "status": "ok" if not issues else "degraded",
        "pending_requests": pending,
        "config_issues": issues,
    }


@app.post("/processar_trajeto")
def processar_trajeto(req: ProcessarTrajetoRequest) -> Dict[str, Any]:
    started_at = time.perf_counter()
    logger.info(
        "[oraculo] inicio /processar_trajeto vehicle=%s attempts=%s top_k=%s map_matching_enabled=%s",
        req.vehicle_id,
        req.attempts,
        req.top_k,
        req.enable_map_matching,
    )

    if req.attempts <= 0:
        raise HTTPException(status_code=400, detail="attempts deve ser > 0")
    if req.top_k <= 0:
        raise HTTPException(status_code=400, detail="top_k deve ser > 0")

    log_map_matching_status(req.enable_map_matching, req.search_radius_m)

    trajectory = [[float(p[0]), float(p[1])] for p in req.trajetoria]
    if len(trajectory) < 2:
        raise HTTPException(status_code=400, detail="trajetoria precisa de ao menos 2 pontos")

    # Hash calculado internamente pelo oraculo — nao mais enviado pelo cliente
    computed_hash = build_trajectory_hash(trajectory)

    original_km = trajectory_distance_km(trajectory)
    contract_params_original = build_contract_params_from_trajectory(trajectory, req.contract_params)
    original_value = simulate_e1_value(contract_params_original)

    default_real_co2_g = max(original_km * 120.0, 1.0)
    co2_source = "estimado"
    if req.contract_params is not None and req.contract_params.realCO2Emissions is not None:
        co2_source = "cliente"
    real_co2_g = contract_params_original["realCO2Emissions"] / 1e6
    meta_micro, diff_micro = compute_meta_diff(contract_params_original)
    diff_raw_micro = meta_micro - int(contract_params_original["realCO2Emissions"])
    logger.info(
        "[oraculo] co2_real_g=%.6f fonte=%s co2_estimado_g=%.6f meta_g=%.6f diff_g=%.6f diff_raw_g=%.6f",
        real_co2_g,
        co2_source,
        default_real_co2_g,
        meta_micro / 1e6,
        diff_micro / 1e6,
        diff_raw_micro / 1e6,
    )

    ref_lat = sum(p[0] for p in trajectory) / len(trajectory)
    tries: List[Dict[str, Any]] = []

    for i in range(1, req.attempts + 1):
        offset_lat, offset_lon, offset_dist_km, offset_angle_deg = generate_random_offset(req.max_radius_km, ref_lat)
        offset_points = apply_offset(trajectory, offset_lat, offset_lon)
        private_points = maybe_map_match(offset_points, req.enable_map_matching, req.search_radius_m)

        private_km = trajectory_distance_km(private_points)
        diff_percent = privacy_diff_percent(original_km, private_km)
        abs_diff_percent = abs(diff_percent)

        private_params = dict(contract_params_original)
        private_params["realCO2Emissions"] = derive_private_real_co2(
            contract_params_original["realCO2Emissions"],
            private_km,
            original_km,
        )

        private_raw_value = simulate_e1_value(private_params)
        private_capped_value = capped_private_value(original_value, abs_diff_percent, private_raw_value)

        tries.append(
            {
                "attempt": i,
                "distance": {
                    "original_km": original_km,
                    "private_km": private_km,
                    "diff_percent": diff_percent,
                    "abs_diff_percent": abs_diff_percent,
                },
                "offset": {
                    "offset_lat_deg": offset_lat,
                    "offset_lon_deg": offset_lon,
                    "distance_km": offset_dist_km,
                    "angle_deg": offset_angle_deg,
                },
                "trajectory_private": [normalize_point(p) for p in private_points],
                "contract_params": private_params,
                "monetizacao": {
                    "original_e1_micro": int(original_value),
                    "private_raw_e1_micro": int(private_raw_value),
                    "private_final_e1_micro": int(private_capped_value),
                    "original_e1_reais": round(original_value / 1e6, 6),
                    "private_raw_e1_reais": round(private_raw_value / 1e6, 6),
                    "private_final_e1_reais": round(private_capped_value / 1e6, 6),
                },
            }
        )

        if i == 1 or i == req.attempts or i % 5 == 0:
            logger.info(
                "[oraculo] progresso vehicle=%s tentativa=%s/%s diff_abs=%.6f private_km=%.6f",
                req.vehicle_id,
                i,
                req.attempts,
                abs_diff_percent,
                private_km,
            )

    top_k = min(req.top_k, len(tries))
    best_options = sorted(tries, key=lambda x: x["distance"]["abs_diff_percent"])[:top_k]

    request_id = str(uuid.uuid4())
    PENDING_SELECTIONS[request_id] = {
        "request_id": request_id,
        "vehicle_id": req.vehicle_id,
        "original_hash": to_bytes32_hex(computed_hash),
        "original_trajectory": [normalize_point(p) for p in trajectory],
        "original_contract_params": contract_params_original,
        "original_e1_micro": int(original_value),
        "options": best_options,
    }

    elapsed = time.perf_counter() - started_at
    logger.info(
        "[oraculo] fim /processar_trajeto request_id=%s vehicle=%s attempts=%s map_matching_enabled=%s map_matching_available=%s elapsed=%.3fs",
        request_id,
        req.vehicle_id,
        req.attempts,
        req.enable_map_matching,
        MAP_MATCHING_AVAILABLE,
        elapsed,
    )

    return {
        "request_id": request_id,
        "vehicle_id": req.vehicle_id,
        "original": {
            "hash": computed_hash,
            "distance_km": original_km,
            "e1_micro": int(original_value),
            "e1_reais": round(original_value / 1e6, 6),
        },
        "opcoes": [
            {
                "option_index": idx,
                "attempt": opt["attempt"],
                "distance": opt["distance"],
                "offset": opt["offset"],
                "monetizacao": opt["monetizacao"],
            }
            for idx, opt in enumerate(best_options, start=1)
        ],
        "diagnostico": {
            "map_matching_enabled": req.enable_map_matching,
            "map_matching_available": MAP_MATCHING_AVAILABLE,
            "processing_seconds": round(elapsed, 6),
        },
    }


class RegistrarTrajetoRequest(BaseModel):
    trajetoria: List[List[float]] = Field(..., min_length=2)
    vehicle_id: Optional[str] = "veh0"
    contract_params: Optional[ContractParamsInput] = None
    min_value_micro: Optional[int] = None


@app.post("/registrar_trajeto")
def registrar_trajeto(req: RegistrarTrajetoRequest) -> Dict[str, Any]:
    """
    Registra o trajeto original na blockchain SEM ofuscacao.
    Calcula a monetizacao e faz o mint com ZKP, igual ao fluxo
    /processar_trajeto + /confirmar_opcao, mas usando o trajeto
    original diretamente (sem gerar opcoes de offset).
    """
    started_at = time.perf_counter()
    logger.info(
        "[oraculo] inicio /registrar_trajeto vehicle=%s",
        req.vehicle_id,
    )

    trajectory = [[float(p[0]), float(p[1])] for p in req.trajetoria]
    if len(trajectory) < 2:
        raise HTTPException(status_code=400, detail="trajetoria precisa de ao menos 2 pontos")

    # Hash calculado internamente pelo oraculo — nao mais enviado pelo cliente
    computed_hash = build_trajectory_hash(trajectory)

    contract_params = build_contract_params_from_trajectory(trajectory, req.contract_params)
    original_value = simulate_e1_value(contract_params)

    final_micro = int(original_value)
    if final_micro <= 0:
        if req.min_value_micro is not None and req.min_value_micro > 0:
            logger.warning("[oraculo] /registrar_trajeto monetizacao zero; aplicando minimo=%s", req.min_value_micro)
            final_micro = int(req.min_value_micro)
        else:
            raise HTTPException(status_code=400, detail="Valor de monetizacao calculado e zero")

    deployment_file = os.environ.get("ORACLE_DEPLOYMENT_FILE", "").strip()
    oracle_private_key = os.environ.get("ORACLE_PRIVATE_KEY", "").strip()

    if not deployment_file:
        raise HTTPException(status_code=500, detail="ORACLE_DEPLOYMENT_FILE nao definido")
    if not os.path.exists(deployment_file):
        raise HTTPException(status_code=500, detail=f"ORACLE_DEPLOYMENT_FILE nao encontrado: {deployment_file}")
    if not oracle_private_key:
        raise HTTPException(status_code=500, detail="ORACLE_PRIVATE_KEY nao definida")

    oracle_address = Account.from_key(oracle_private_key).address
    original_hash_bytes32 = to_bytes32_hex(computed_hash)

    # Montar CalculationParams para enviar ao contrato
    params_tuple = [
        int(contract_params.get("highwayDistance",   0)),
        int(contract_params.get("cityDistance",      0)),
        int(contract_params.get("ethanolPercent",    0)),
        int(contract_params.get("roadGasoline",      0)),
        int(contract_params.get("roadEthanol",       0)),
        int(contract_params.get("cityGasoline",      0)),
        int(contract_params.get("cityEthanol",       0)),
        int(contract_params.get("realCO2Emissions",  0)),
        int(contract_params.get("carbonPricePerTon", 0)),
    ]

    # Gerar prova ZKP
    zkp_enabled = is_zk_enabled()
    if not zkp_enabled:
        raise HTTPException(status_code=400, detail="ZKP obrigatorio para /registrar_trajeto")

    zk_nonce = int(time.time_ns())
    zk_start = time.perf_counter()
    try:
        zk_result = generate_zk_proof(
            trajectory=trajectory,
            recipient=oracle_address,
            nonce=zk_nonce,
        )
    except Exception as exc:
        logger.error("[oraculo] /registrar_trajeto falha ZK: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Erro ao gerar prova ZK: {exc}") from exc
    zk_proof_seconds = time.perf_counter() - zk_start

    def parse_uint(value: Any) -> int:
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            return int(value, 0)
        raise ValueError(f"Valor numerico invalido: {value}")

    try:
        proof = zk_result["proof"]
        proof_a = [parse_uint(x) for x in proof["a"]]
        proof_b = [
            [parse_uint(x) for x in proof["b"][0]],
            [parse_uint(x) for x in proof["b"][1]],
        ]
        proof_c = [parse_uint(x) for x in proof["c"]]
        poseidon_root = zk_result["poseidon_root"]
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail=f"Resposta ZK invalida: {exc}") from exc

    payload: List[Dict[str, Any]] = [
        {
            "vehicle_id":    req.vehicle_id,
            "params":        params_tuple,
            "recipient":     oracle_address,
            "original_hash": original_hash_bytes32,
            "poseidon_root": poseidon_root,
            "zk_nonce":      zk_nonce,
            "proof_a":       proof_a,
            "proof_b":       proof_b,
            "proof_c":       proof_c,
        }
    ]

    tx_wait_seconds = 0.0
    try:
        tx_start = time.perf_counter()
        tx_hashes = send_oracle_results(
            results=payload,
            deployment_file=deployment_file,
            private_key=oracle_private_key,
            method_name="calculateAndMintWithZK",
            method_args_spec=[
                "$.params", "$.recipient", "$.original_hash",
                "$.poseidon_root", "$.zk_nonce",
                "$.proof_a", "$.proof_b", "$.proof_c",
            ],
        )
        tx_wait_seconds = time.perf_counter() - tx_start
    except Exception as exc:
        logger.error(
            "[oraculo] /registrar_trajeto falha ao enviar transacao: %s\n%s",
            exc, traceback.format_exc(),
        )
        raise HTTPException(status_code=500, detail=f"Erro ao enviar transacao: {exc}") from exc

    elapsed = time.perf_counter() - started_at
    logger.info(
        "[oraculo] fim /registrar_trajeto vehicle=%s elapsed=%.3fs",
        req.vehicle_id,
        elapsed,
    )

    return {
        "status": "registrado",
        "vehicle_id": req.vehicle_id,
        "hash_original": original_hash_bytes32,
        "poseidon_root": poseidon_root,
        "zk_nonce": zk_nonce,
        "zkp_enabled": zkp_enabled,
        "zk_proof_seconds": round(zk_proof_seconds, 6),
        "tx_wait_seconds": round(tx_wait_seconds, 6),
        "tx_hashes": tx_hashes,
    }


@app.post("/confirmar_opcao")
def confirmar_opcao(req: ConfirmarOpcaoRequest) -> Dict[str, Any]:
    logger.info(
        "[oraculo] inicio /confirmar_opcao request_id=%s option_index=%s",
        req.request_id,
        req.option_index,
    )

    if req.request_id not in PENDING_SELECTIONS:
        raise HTTPException(status_code=404, detail="request_id nao encontrado")

    pending = PENDING_SELECTIONS[req.request_id]
    options = pending["options"]
    if req.option_index < 1 or req.option_index > len(options):
        raise HTTPException(status_code=400, detail="option_index invalido")

    selected = options[req.option_index - 1]

    min_value_micro = req.min_value_micro
    if min_value_micro is not None:
        try:
            min_value_micro = int(min_value_micro)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="min_value_micro invalido") from exc
        if min_value_micro < 0:
            raise HTTPException(status_code=400, detail="min_value_micro invalido")

    deployment_file = os.environ.get("ORACLE_DEPLOYMENT_FILE", "").strip()
    oracle_private_key = os.environ.get("ORACLE_PRIVATE_KEY", "").strip()

    if not deployment_file:
        logger.error("[oraculo] ORACLE_DEPLOYMENT_FILE nao definido")
        raise HTTPException(status_code=500, detail="ORACLE_DEPLOYMENT_FILE nao definido")
    if not os.path.exists(deployment_file):
        logger.error("[oraculo] ORACLE_DEPLOYMENT_FILE nao encontrado: %s", deployment_file)
        raise HTTPException(
            status_code=500,
            detail=f"ORACLE_DEPLOYMENT_FILE nao encontrado: {deployment_file}",
        )
    if not oracle_private_key:
        logger.error("[oraculo] ORACLE_PRIVATE_KEY nao definida")
        raise HTTPException(status_code=500, detail="ORACLE_PRIVATE_KEY nao definida")

    oracle_address = Account.from_key(oracle_private_key).address

    # Montar CalculationParams da opcao selecionada
    cp = selected["contract_params"]
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

    # Gerar prova ZKP (obrigatoria para calculateAndMintWithZK)
    zkp_enabled = is_zk_enabled()
    if not zkp_enabled:
        raise HTTPException(status_code=400, detail="ZKP obrigatorio para /confirmar_opcao")

    zk_nonce = int(time.time_ns())
    zk_start = time.perf_counter()
    try:
        zk_result = generate_zk_proof(
            trajectory=pending["original_trajectory"],
            recipient=oracle_address,
            nonce=zk_nonce,
        )
    except Exception as exc:
        logger.error("[oraculo] Falha ao gerar prova ZK: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Erro ao gerar prova ZK: {exc}") from exc
    zk_proof_seconds = time.perf_counter() - zk_start

    def parse_uint(value: Any) -> int:
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            return int(value, 0)
        raise ValueError(f"Valor numerico invalido: {value}")

    try:
        proof = zk_result["proof"]
        proof_a = [parse_uint(x) for x in proof["a"]]
        proof_b = [
            [parse_uint(x) for x in proof["b"][0]],
            [parse_uint(x) for x in proof["b"][1]],
        ]
        proof_c = [parse_uint(x) for x in proof["c"]]
        poseidon_root = zk_result["poseidon_root"]
        public_signals = zk_result.get("public_signals", {})
        ps_root = public_signals.get("root")
        ps_recipient = public_signals.get("recipient")
        ps_nonce = public_signals.get("nonce")
        if ps_root is not None:
            try:
                root_hex = hex(int(ps_root))
            except (TypeError, ValueError):
                root_hex = str(ps_root)
        else:
            root_hex = None
        logger.info(
            "[oraculo] zk_public raw0=%s raw1=%s raw2=%s",
            root_hex, ps_recipient, ps_nonce,
        )
        logger.info(
            "[oraculo] zk_expected raw0=%s raw1=%s raw2=%s",
            int(oracle_address, 16), zk_nonce, poseidon_root,
        )
    except (KeyError, ValueError, TypeError) as exc:
        logger.error("[oraculo] Resposta ZK invalida: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Resposta ZK invalida: {exc}") from exc

    payload: List[Dict[str, Any]] = [
        {
            "vehicle_id":    pending.get("vehicle_id", "veh0"),
            "params":        params_tuple,
            "recipient":     oracle_address,
            "original_hash": pending["original_hash"],
            "poseidon_root": poseidon_root,
            "zk_nonce":      zk_nonce,
            "proof_a":       proof_a,
            "proof_b":       proof_b,
            "proof_c":       proof_c,
        }
    ]

    tx_wait_seconds = 0.0
    try:
        tx_start = time.perf_counter()
        tx_hashes = send_oracle_results(
            results=payload,
            deployment_file=deployment_file,
            private_key=oracle_private_key,
            method_name="calculateAndMintWithZK",
            method_args_spec=[
                "$.params", "$.recipient", "$.original_hash",
                "$.poseidon_root", "$.zk_nonce",
                "$.proof_a", "$.proof_b", "$.proof_c",
            ],
        )
        tx_wait_seconds = time.perf_counter() - tx_start
    except Exception as exc:
        logger.error(
            "[oraculo] Falha ao enviar transacao: %s\n%s", exc, traceback.format_exc()
        )
        raise HTTPException(status_code=500, detail=f"Erro ao enviar transacao: {exc}") from exc

    # ------------------------------------------------------------------
    # Salvar copia do trajeto ofuscado (CSV e JSON) — controlado por
    # SAVE_OBFUSCATED_TRIPS no topo deste arquivo.
    # ------------------------------------------------------------------
    saved_files = None
    if SAVE_OBFUSCATED_TRIPS:
        saved_files = save_obfuscated_trip(
            vehicle_id=str(pending.get("vehicle_id", "veh0")),
            request_id=req.request_id,
            original_trajectory=pending["original_trajectory"],
            private_trajectory=selected["trajectory_private"],
            original_km=selected["distance"]["original_km"],
            private_km=selected["distance"]["private_km"],
            contract_params=selected["contract_params"],
            e1_reais=0.0,  # calculado pelo contrato
        )
        logger.info("[oraculo] arquivos ofuscados salvos: %s", saved_files)
    else:
        logger.debug("[oraculo] SAVE_OBFUSCATED_TRIPS=False; arquivos nao salvos.")

    PENDING_SELECTIONS.pop(req.request_id, None)

    logger.info(
        "[oraculo] fim /confirmar_opcao request_id=%s option_index=%s",
        req.request_id,
        req.option_index,
    )

    return {
        "status": "confirmado",
        "request_id": req.request_id,
        "option_index": req.option_index,
        "carteira_oraculo": oracle_address,
        "hash_original": pending["original_hash"],
        "poseidon_root": poseidon_root,
        "zk_nonce": zk_nonce,
        "zkp_enabled": zkp_enabled,
        "zk_proof_seconds": round(zk_proof_seconds, 6),
        "tx_wait_seconds": round(tx_wait_seconds, 6),
        "tx_hashes": tx_hashes,
        "arquivos_ofuscados": saved_files,
        "aviso": "e1Value calculado pelo contrato via calculateAndMintWithZK",
    }


def _get_obfuscated_output_dir() -> str:
    """Retorna o caminho absoluto para data/trajetos_ofuscados/."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(script_dir, "..", "data", "trajetos_ofuscados"))


def _next_trip_number(output_dir: str) -> int:
    """
    Retorna o proximo numero sequencial disponivel na pasta output_dir,
    baseado nos arquivos trajeto_NNN.csv ja existentes.
    Funciona mesmo apos reinicializacao do oraculo.
    """
    existing = [
        f for f in os.listdir(output_dir)
        if f.startswith("trajeto_") and f.endswith(".csv")
    ]
    numbers = []
    for name in existing:
        stem = name[len("trajeto_"):-len(".csv")]
        if stem.isdigit():
            numbers.append(int(stem))
    return (max(numbers) + 1) if numbers else 1


def save_obfuscated_trip(
    vehicle_id: str,
    request_id: str,
    original_trajectory: List[List[float]],
    private_trajectory: List[List[float]],
    original_km: float,
    private_km: float,
    contract_params: Dict[str, int],
    e1_reais: float,
) -> Dict[str, str]:
    """
    Salva uma copia do trajeto ofuscado em data/trajetos_ofuscados/:
      - <vehicle_id>_<request_id_curto>.csv  : pontos do trajeto ofuscado (lat, lon)
      - <vehicle_id>_<request_id_curto>.json : formato esperado pelo visualize_trips.py

    So e chamada quando SAVE_OBFUSCATED_TRIPS = True.
    Retorna um dict com os caminhos dos arquivos salvos.
    """
    output_dir = _get_obfuscated_output_dir()
    os.makedirs(output_dir, exist_ok=True)

    trip_number = _next_trip_number(output_dir)
    base_name = f"trajeto_{trip_number:03d}"

    # ------------------------------------------------------------------
    # 1. CSV — pontos do trajeto ofuscado
    # ------------------------------------------------------------------
    csv_path = os.path.join(output_dir, f"{base_name}.csv")
    try:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["lat", "lon"])
            for point in private_trajectory:
                writer.writerow([point[0], point[1]])
        logger.info("[oraculo] CSV ofuscado salvo: %s", csv_path)
    except Exception as exc:
        logger.warning("[oraculo] Falha ao salvar CSV ofuscado: %s", exc)
        csv_path = None

    # ------------------------------------------------------------------
    # 2. JSON — formato esperado pelo visualize_trips.py
    # ------------------------------------------------------------------
    real_co2_g = contract_params.get("realCO2Emissions", 0) / 1e6
    emission_factor = 2310.0
    road_gas = contract_params.get("roadGasoline", 1) / 1e6 or 1.0
    city_gas = contract_params.get("cityGasoline", 1) / 1e6 or 1.0
    highway_km = contract_params.get("highwayDistance", 0) / 1e6
    city_km_val = contract_params.get("cityDistance", 0) / 1e6
    meta_g = (highway_km / road_gas * emission_factor) + (city_km_val / city_gas * emission_factor)
    delta_co2_g = max(0.0, meta_g - real_co2_g)

    trip_record = {
        "vin": vehicle_id,
        "model": vehicle_id,
        "trajectory_id": base_name,
        "total_distance_km": round(private_km, 6),
        "co2_real_g": round(real_co2_g, 6),
        "delta_co2_g": round(delta_co2_g, 6),
        "valor_e1_reais": round(e1_reais, 6),
        "trajectory_original": [[round(p[0], 7), round(p[1], 7)] for p in original_trajectory],
        "trajectory_private": [[round(p[0], 7), round(p[1], 7)] for p in private_trajectory],
        "meta": {
            "request_id": request_id,
            "original_km": round(original_km, 6),
            "private_km": round(private_km, 6),
        },
    }

    json_path = os.path.join(output_dir, f"{base_name}.json")
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump([trip_record], f, ensure_ascii=False, indent=2)
        logger.info("[oraculo] JSON ofuscado salvo: %s", json_path)
    except Exception as exc:
        logger.warning("[oraculo] Falha ao salvar JSON ofuscado: %s", exc)
        json_path = None

    return {
        "csv": csv_path,
        "json": json_path,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Servidor API do Oraculo")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host bind da API")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Porta da API")
    args = parser.parse_args()

    log_path = setup_file_logging()
    if log_path:
        print(f"[oraculo] logs gravados em: {log_path}", flush=True)

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()