#!/usr/bin/env python3
"""
Cliente local do usuario para interagir com o oraculo e com a blockchain.

0xc87509a1c067bbde78beb793e6fa76530b6382a4c0241e5e4a9ec0a0f44dc0d3

python3 usuario.py ../data/trajetos/vehicles_step_sim_1.csv \
  --oracle-url http://127.0.0.1:5001 \
  --deployment-file deployment_info.json \
  --user-private-key 0xc87509a1c067bbde78beb793e6fa76530b6382a4c0241e5e4a9ec0a0f44dc0d3

python3 usuario.py ../data/trajetos/vehicles_step_sim_1.csv \
	--oracle-url http://127.0.0.1:5001 \
	--deployment-file deployment_info.json \
	--user-private-key 0xc87509a1c067bbde78beb793e6fa76530b6382a4c0241e5e4a9ec0a0f44dc0d3 \
	--pseudonym-seed-file ./seed.txt \
	--pseudonym-hd-index 0

python3 usuario.py ../data/trajetos/vehicles_step_sim_1.csv \
  --oracle-url http://127.0.0.1:5001 \
  --deployment-file ../deployment_info.json \
  --user-private-key 0xc87509a1c067bbde78beb793e6fa76530b6382a4c0241e5e4a9ec0a0f44dc0d3 \
  --enable-map-matching \
  --search-radius-m 1500

Fluxo:
1) Le CSV local e detecta colunas automaticamente
2) Pergunta se deseja aplicar ofuscacao por offset
3) Se sim: chama API do oraculo, recebe top 5, usuario escolhe, confirma
4) Se nao: envia trajeto original direto para blockchain com carteira do usuario
"""

import argparse
import hashlib
import json
import math
import os
import subprocess
import tempfile
import time
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
from eth_account import Account
from web3 import Web3

from blockchain_sender import load_deployment_info, send_oracle_results
from hd_wallet import DEFAULT_ACCOUNT_PATH_TEMPLATE, derive_account_from_mnemonic, load_mnemonic_from_file


EARTH_RADIUS_KM = 6371.0

DEFAULT_CITY_GASOLINE_KM_L = 7.8
DEFAULT_ROAD_GASOLINE_KM_L = 8.5
DEFAULT_CARBON_PRICE_BRL_TON = 67.13 * 6.17

DEFAULT_ZK_MAX_POINTS = 500
DEFAULT_ZK_INPUT_SCALE = 1e7


def progress_print(message: str) -> None:
	print(message, flush=True)


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
		raise ValueError("Hash deve ter 64 caracteres hex")
	int(h, 16)
	return "0x" + h


def get_web3_for_user(rpc_url: str) -> Web3:
	return Web3(Web3.HTTPProvider(rpc_url))


def get_contract_instance(deployment_file: str):
	deployment = load_deployment_info(deployment_file)
	rpc_url = deployment.get("rpc_url", "http://localhost:8545")
	w3 = get_web3_for_user(rpc_url)
	try:
		_ = w3.eth.chain_id
		_ = w3.eth.block_number
	except Exception as exc:
		raise ConnectionError(f"Nao foi possivel conectar ao RPC: {rpc_url} ({exc})") from exc
	contract = w3.eth.contract(address=deployment["contract_address"], abi=deployment["abi"])
	return w3, contract


def resolve_pseudonym_private_key(seed_file: str, hd_index: int) -> tuple[str, str]:
	if hd_index < 0:
		raise ValueError(f"Indice HD invalido (<0): {hd_index}")
	mnemonic = load_mnemonic_from_file(seed_file)
	account_path = DEFAULT_ACCOUNT_PATH_TEMPLATE.format(index=hd_index)
	address, private_key = derive_account_from_mnemonic(mnemonic, account_path)
	return address, private_key


def resolve_zk_dir(custom_dir: Optional[str]) -> str:
	if custom_dir:
		return os.path.abspath(custom_dir)
	script_dir = os.path.dirname(os.path.abspath(__file__))
	default_dir = os.path.abspath(os.path.join(script_dir, "..", "zkp"))
	return os.environ.get("ORACLE_ZKP_DIR", default_dir)


def generate_zk_proof(
	trajectory: List[List[float]],
	recipient: str,
	nonce: int,
	zk_dir: str,
) -> Dict[str, Any]:
	if len(trajectory) > DEFAULT_ZK_MAX_POINTS:
		raise ValueError(
			f"Trajetoria excede maximo de {DEFAULT_ZK_MAX_POINTS} pontos para ZK"
		)

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
			)
		except subprocess.CalledProcessError as exc:
			raise RuntimeError(
				f"Falha ao gerar prova ZK (codigo {exc.returncode}). Veja logs acima."
			) from exc

		with open(output_path, "r", encoding="utf-8") as f:
			return json.load(f)


def read_hash_onchain(deployment_file: str, token_id: int) -> str:
	_, contract = get_contract_instance(deployment_file)
	onchain_hash = contract.functions.getOriginalTrajectoryHash(token_id).call()
	if isinstance(onchain_hash, (bytes, bytearray)):
		return "0x" + bytes(onchain_hash).hex()
	return str(onchain_hash)


def verify_hash_onchain(deployment_file: str, token_id: int, local_hash: str) -> bool:
	_, contract = get_contract_instance(deployment_file)
	provided_hash = to_bytes32_hex(local_hash)
	return bool(contract.functions.verifyOriginalTrajectoryHash(token_id, provided_hash).call())


def get_next_token_id_onchain(deployment_file: str) -> int:
	_, contract = get_contract_instance(deployment_file)
	return int(contract.functions.nextTokenId().call())


def is_hash_registered_onchain(deployment_file: str, local_hash: str) -> bool:
	_, contract = get_contract_instance(deployment_file)
	provided_hash = to_bytes32_hex(local_hash)
	return bool(contract.functions.isTrajectoryHashRegistered(provided_hash).call())


def detect_columns(df: pd.DataFrame) -> Dict[str, Optional[str]]:
	cols = set(df.columns)

	def pick(candidates: List[str]) -> Optional[str]:
		for c in candidates:
			if c in cols:
				return c
		return None

	return {
		"vehicle_id": pick(["vehicle_id", "veh_id", "vehicle", "id", "vin"]),
		"time": pick(["time", "timestamp", "start_time", "step"]),
		"end_time": pick(["end_time"]),
		"lat": pick(["lat", "latitude", "start_lat"]),
		"lon": pick(["lon", "lng", "longitude", "start_lon"]),
		"end_lat": pick(["end_lat"]),
		"end_lon": pick(["end_lon"]),
		"distance_city": pick(["distance_city", "city_distance", "cidade_km"]),
		"distance_highway": pick(["distance_highway", "highway_distance", "estrada_km"]),
		"co2": pick(["CO2", "co2", "co2_g", "co2_emissions", "emissoes_co2"]),
		"fuel_type": pick(["fuel_type", "fuel", "combustivel"]),
	}


def build_trajectory_from_group(group: pd.DataFrame, columns: Dict[str, Optional[str]]) -> List[List[float]]:
	lat_col = columns["lat"]
	lon_col = columns["lon"]
	end_lat_col = columns["end_lat"]
	end_lon_col = columns["end_lon"]

	if lat_col is None or lon_col is None:
		return []

	points: List[List[float]] = []
	for _, row in group.iterrows():
		lat = row.get(lat_col)
		lon = row.get(lon_col)
		if pd.notna(lat) and pd.notna(lon):
			points.append([float(lat), float(lon)])

	if end_lat_col and end_lon_col and not group.empty:
		last = group.iloc[-1]
		end_lat = last.get(end_lat_col)
		end_lon = last.get(end_lon_col)
		if pd.notna(end_lat) and pd.notna(end_lon):
			end_point = [float(end_lat), float(end_lon)]
			if not points or points[-1] != end_point:
				points.append(end_point)

	return points


def split_city_highway(total_km: float) -> tuple[float, float]:
	return total_km * 0.4, total_km * 0.6


def pick_delta_sum_numeric(group: pd.DataFrame, col_name: Optional[str]) -> Optional[float]:
	if not col_name or col_name not in group.columns:
		return None
	series = pd.to_numeric(group[col_name], errors="coerce").dropna()
	if series.empty:
		return None
	delta = series.diff().fillna(series.iloc[0]).clip(lower=0)
	return float(delta.sum())


def pick_last_numeric(group: pd.DataFrame, col_name: Optional[str]) -> Optional[float]:
	if not col_name or col_name not in group.columns:
		return None
	series = pd.to_numeric(group[col_name], errors="coerce").dropna()
	if series.empty:
		return None
	return float(series.iloc[-1])


def compute_meta_co2_csv_scale(
	group: pd.DataFrame,
	columns: Dict[str, Optional[str]],
) -> Optional[float]:
	"""Calcula a meta de CO2 na mesma escala/unidade do CSV (igual ao test_adapted.py).

	Para cada linha calcula:
	  meta_linha = (delta_city / city_consumption + delta_highway / highway_consumption) * emission_factor

	onde os deltas de distância são incrementais (diff + clip), exatamente como
	o test_adapted.py faz com delta_distance_city e delta_distance_highway.
	"""
	city_col = columns.get("distance_city")
	highway_col = columns.get("distance_highway")
	fuel_col = columns.get("fuel_type")

	if city_col is None and highway_col is None:
		return None

	# Consumo e fator de emissão por tipo de combustível (mesmos valores do test_adapted.py)
	CONSUMO = {
		"Gasoline": {"city": DEFAULT_CITY_GASOLINE_KM_L, "highway": DEFAULT_ROAD_GASOLINE_KM_L, "emission_factor": 2310},
	}
	DEFAULT_FUEL_KEY = "Gasoline"

	# Deltas incrementais de distância (acumulado → incremental)
	if city_col and city_col in group.columns:
		city_series = pd.to_numeric(group[city_col], errors="coerce").fillna(0)
		delta_city = city_series.diff().fillna(city_series.iloc[0]).clip(lower=0)
	else:
		delta_city = pd.Series([0.0] * len(group), index=group.index)

	if highway_col and highway_col in group.columns:
		highway_series = pd.to_numeric(group[highway_col], errors="coerce").fillna(0)
		delta_highway = highway_series.diff().fillna(highway_series.iloc[0]).clip(lower=0)
	else:
		delta_highway = pd.Series([0.0] * len(group), index=group.index)

	meta_total = 0.0
	for i, (idx, row) in enumerate(group.iterrows()):
		if fuel_col and fuel_col in group.columns:
			fuel = str(row.get(fuel_col, DEFAULT_FUEL_KEY))
		else:
			fuel = DEFAULT_FUEL_KEY

		params_fuel = CONSUMO.get(fuel, CONSUMO[DEFAULT_FUEL_KEY])
		city_cons = params_fuel["city"]
		highway_cons = params_fuel["highway"]
		ef = params_fuel["emission_factor"]

		dc = float(delta_city.iloc[i])
		dh = float(delta_highway.iloc[i])

		city_em = (dc / city_cons * ef) if city_cons > 0 else 0.0
		highway_em = (dh / highway_cons * ef) if highway_cons > 0 else 0.0
		meta_total += city_em + highway_em

	return meta_total


def build_contract_params_from_group(group: pd.DataFrame, columns: Dict[str, Optional[str]], trajectory: List[List[float]]) -> Dict[str, int]:
	total_km = trajectory_distance_km(trajectory)
	city_km_default, highway_km_default = split_city_highway(total_km)

	city_km = pick_delta_sum_numeric(group, columns["distance_city"])
	highway_km = pick_delta_sum_numeric(group, columns["distance_highway"])

	# CO2 real: soma dos deltas incrementais do CSV (igual ao CO2_delta do test_adapted.py)
	co2_delta_sum = pick_delta_sum_numeric(group, columns["co2"])

	if city_km is None:
		city_km = city_km_default
	if highway_km is None:
		highway_km = highway_km_default

	# Meta de CO2 calculada na mesma escala/unidade do CSV (igual ao test_adapted.py)
	meta_csv = compute_meta_co2_csv_scale(group, columns)

	# Diff na escala do CSV
	if meta_csv is not None and co2_delta_sum is not None:
		diff_csv = max(0.0, meta_csv - co2_delta_sum)
		co2_source = "csv"
		co2_raw = f"{co2_delta_sum:.6f}"
	elif co2_delta_sum is not None:
		# Sem colunas de distância para calcular meta — diff zero
		diff_csv = 0.0
		meta_csv = co2_delta_sum
		co2_source = "csv"
		co2_raw = f"{co2_delta_sum:.6f}"
	else:
		# Sem CO2 no CSV — estima pela distância em gramas reais
		default_real_co2_g = total_km * 120.0
		meta_g = city_km / DEFAULT_CITY_GASOLINE_KM_L * 2310 + highway_km / DEFAULT_ROAD_GASOLINE_KM_L * 2310
		diff_csv = max(0.0, meta_g - default_real_co2_g)
		meta_csv = meta_g
		co2_delta_sum = default_real_co2_g
		co2_source = "estimado"
		co2_raw = "n/a"

	# Monetização e1 na escala do CSV:
	#   e1_brl = diff_csv * REAL_PRICE / 1_000_000
	# (igual à fórmula do test_adapted.py)
	e1_brl = diff_csv * DEFAULT_CARBON_PRICE_BRL_TON / 1_000_000.0

	progress_print(
		"[co2] fonte={source} csv_raw={raw} meta_csv={meta:.6f} diff_csv={diff:.6f} e1_estimado={e1:.6f} BRL".format(
			source=co2_source,
			raw=co2_raw,
			meta=meta_csv,
			diff=diff_csv,
			e1=e1_brl,
		)
	)

	# Para o contrato, escalonamos por 1e6 (micros).
	# realCO2Emissions = soma dos deltas de CO2 do CSV * 1e6
	# A meta e diff no contrato são recalculados internamente a partir das distâncias
	# e dos fatores de consumo — por isso apenas armazenamos as distâncias e o CO2 real.
	params = {
		"highwayDistance": int(highway_km * 1e6),
		"cityDistance": int(city_km * 1e6),
		"ethanolPercent": 0,
		"roadGasoline": int(DEFAULT_ROAD_GASOLINE_KM_L * 1e6),
		"roadEthanol": 0,
		"cityGasoline": int(DEFAULT_CITY_GASOLINE_KM_L * 1e6),
		"cityEthanol": 0,
		"realCO2Emissions": int(co2_delta_sum * 1e6),
		"carbonPricePerTon": int(DEFAULT_CARBON_PRICE_BRL_TON * 1e6),
		# Campo auxiliar local (não enviado ao contrato): e1 estimado em micros de BRL
		"_e1_estimado_micro": int(e1_brl * 1e6),
	}

	return params


def strip_aux_fields(contract_params: Dict[str, Any]) -> Dict[str, int]:
	"""Remove campos auxiliares (prefixo '_') antes de enviar ao contrato ou oraculo."""
	return {k: v for k, v in contract_params.items() if not k.startswith("_")}


def simulate_e1_value(contract_params: Dict[str, int]) -> int:
	"""Estima o valor e1 em micro-BRL.

	Usa o campo auxiliar _e1_estimado_micro calculado por build_contract_params_from_group
	na mesma escala/unidade do CSV (igual ao test_adapted.py).
	"""
	return int(contract_params.get("_e1_estimado_micro", 0))


def compute_meta_diff(contract_params: Dict[str, int]) -> tuple[int, int]:
	"""Retorna (meta_micro, diff_micro) usando a mesma lógica do test_adapted.py."""
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


def load_csv_first_vehicle(input_csv: str) -> Dict[str, Any]:
	df = pd.read_csv(input_csv)
	columns = detect_columns(df)

	if columns["lat"] is None or columns["lon"] is None:
		raise ValueError("Nao foi possivel detectar colunas de latitude/longitude")

	if columns["time"] is not None:
		df["_sort_time"] = pd.to_numeric(df[columns["time"]], errors="coerce")
	else:
		df["_sort_time"] = 0

	if columns["end_time"] is not None:
		df["_sort_end_time"] = pd.to_numeric(df[columns["end_time"]], errors="coerce")
	else:
		df["_sort_end_time"] = 0

	df["_row_order"] = range(len(df))

	vehicle_col = columns["vehicle_id"]
	if vehicle_col is None:
		df["_vehicle_id"] = "veh0"
		vehicle_col = "_vehicle_id"

	if df.empty:
		raise ValueError("CSV vazio")

	vehicle_id, group = next(iter(df.groupby(vehicle_col)))
	group = group.sort_values(by=["_sort_time", "_sort_end_time", "_row_order"], kind="mergesort")

	trajectory = build_trajectory_from_group(group, columns)
	if len(trajectory) < 2:
		raise ValueError("Trajetoria invalida (<2 pontos)")

	params = build_contract_params_from_group(group, columns, trajectory)
	traj_hash = build_trajectory_hash(trajectory)

	return {
		"vehicle_id": str(vehicle_id),
		"trajectory": trajectory,
		"hash": traj_hash,
		"contract_params": params,
	}


def print_options_table(options: List[Dict[str, Any]]) -> None:
	print("\nTop opcoes do oraculo:")
	print("idx | tentativa | diff_abs(%) | monetizacao_estimada_reais")
	print("----+----------+-------------+------------------")
	for opt in options:
		idx = opt["option_index"]
		att = opt["attempt"]
		diff_abs = opt["distance"]["abs_diff_percent"]
		reais = opt["monetizacao"]["private_final_e1_reais"]
		print(f"{idx:>3} | {att:>8} | {diff_abs:>11.4f} | {reais:>16.6f}")


def send_direct_without_offset(
	deployment_file: str,
	private_key: str,
	recipient: str,
	contract_params: Dict[str, int],
	hash_original: str,
	vehicle_id: str,
	estimated_e1_micro: int = 0,
) -> Dict[str, Any]:
	# Chama calculateAndMintWithHash para que o CONTRATO calcule o e1Value
	# internamente a partir dos CalculationParams (distancias, consumos, CO2).
	next_token_before = get_next_token_id_onchain(deployment_file)

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

	payload = [
		{
			"vehicle_id":    vehicle_id,
			"params":        params_tuple,
			"recipient":     recipient,
			"original_hash": to_bytes32_hex(hash_original),
		}
	]

	tx_hashes = send_oracle_results(
		results=payload,
		deployment_file=deployment_file,
		private_key=private_key,
		method_name="calculateAndPay",
		method_args_spec=["$.params", "$.recipient", "$.original_hash"],
	)

	minted_token_id = int(next_token_before)
	hash_match = verify_hash_onchain(deployment_file, minted_token_id, hash_original)
	onchain_hash = read_hash_onchain(deployment_file, minted_token_id)

	return {
		"estimated_e1_micro": estimated_e1_micro,
		"estimated_e1_reais": round(estimated_e1_micro / 1e6, 6),
		"minted_token_id": minted_token_id,
		"hash_match": hash_match,
		"onchain_hash": onchain_hash,
		"tx_hashes": tx_hashes,
	}


def redeem_with_zk(
	deployment_file: str,
	private_key: str,
	trajectory: List[List[float]],
	vehicle_id: str,
	zk_dir: str,
) -> Dict[str, Any]:
	def parse_uint(value: Any) -> int:
		if isinstance(value, int):
			return value
		if isinstance(value, str):
			return int(value, 0)
		raise ValueError(f"Valor numerico invalido: {value}")

	recipient = Account.from_key(private_key).address
	zk_nonce = int(time.time_ns())
	zk_result = generate_zk_proof(
		trajectory=trajectory,
		recipient=recipient,
		nonce=zk_nonce,
		zk_dir=zk_dir,
	)

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
		raise ValueError(f"Resposta ZK invalida: {exc}") from exc

	w3, contract = get_contract_instance(deployment_file)
	if not hasattr(contract.functions, "isPoseidonRootRegistered"):
		raise RuntimeError("Contrato nao suporta resgate ZK. Recompile e redeploy o E1 atualizado.")

	registered = contract.functions.isPoseidonRootRegistered(poseidon_root).call()
	if not registered:
		raise RuntimeError("poseidonRoot nao registrado. Gere o mint com ZK antes de resgatar.")

	if hasattr(contract.functions, "redeemedPoseidonRoots"):
		already_redeemed = contract.functions.redeemedPoseidonRoots(poseidon_root).call()
		if already_redeemed:
			raise RuntimeError("poseidonRoot ja resgatado.")

	verifier = contract.functions.zkVerifier().call()
	if verifier == "0x0000000000000000000000000000000000000000":
		raise RuntimeError("ZK verifier nao configurado no contrato.")

	token_id = contract.functions.poseidonRootToTokenId(poseidon_root).call()
	if int(token_id) == 0:
		raise RuntimeError("tokenId nao encontrado para o poseidonRoot.")

	calc = contract.functions.getCalculationDetails(int(token_id)).call()
	try:
		amount = int(calc[5])
	except Exception:
		amount = int(calc["e1Value"]) if isinstance(calc, dict) else 0
	if amount <= 0:
		raise RuntimeError("Valor de resgate invalido (e1Value=0).")

	contract_balance = w3.eth.get_balance(contract.address)
	if contract_balance < amount:
		raise RuntimeError("Saldo insuficiente no contrato para resgate.")

	payload = [
		{
			"vehicle_id": vehicle_id,
			"poseidon_root": poseidon_root,
			"zk_nonce": zk_nonce,
			"proof_a": proof_a,
			"proof_b": proof_b,
			"proof_c": proof_c,
		}
	]

	tx_hashes = send_oracle_results(
		results=payload,
		deployment_file=deployment_file,
		private_key=private_key,
		method_name="redeemWithZK",
		method_args_spec=[
			"$.poseidon_root",
			"$.zk_nonce",
			"$.proof_a",
			"$.proof_b",
			"$.proof_c",
		],
	)

	return {
		"requester": recipient,
		"poseidon_root": poseidon_root,
		"tx_hashes": tx_hashes,
	}


def main() -> None:
	parser = argparse.ArgumentParser(description="Cliente local do usuario para fluxo de privacidade")
	parser.add_argument("input_csv", nargs="?", help="CSV local com trajetoria (necessario no modo enviar)")
	parser.add_argument("--oracle-url", default="http://127.0.0.1:5000", help="URL base da API do oraculo")
	parser.add_argument("--deployment-file", required=True, help="deployment_info.json")
	parser.add_argument("--user-private-key", required=True, help="Chave privada da carteira do usuario")
	parser.add_argument("--pseudonym-private-key", default=None, help="Chave privada da carteira pseudonima")
	parser.add_argument("--pseudonym-seed-file", default=None, help="Arquivo local com a seed/mnemonic da carteira pseudonima")
	parser.add_argument("--pseudonym-hd-index", type=int, default=0, help="Indice HD usado para derivar a carteira pseudonima")
	parser.add_argument("--attempts", type=int, default=20, help="N tentativas para o oraculo")
	parser.add_argument("--enable-map-matching", action="store_true", help="Ativa map matching via OSM no oraculo")
	parser.add_argument("--search-radius-m", type=int, default=1500, help="Raio de busca para map matching no oraculo")
	parser.add_argument("--audit-token-id", type=int, default=None, help="Executa apenas auditoria de hash para um tokenId")
	parser.add_argument("--zkp-dir", default=None, help="Diretorio ZKP (padrao ../zkp ou ORACLE_ZKP_DIR)")
	args = parser.parse_args()

	progress_print("=" * 70)
	progress_print("CLIENTE USUARIO")
	progress_print("=" * 70)

	mode = input("Escolha a operacao: Enviar dados ou Resgatar? (E/R): ").strip().lower()
	if mode in ("r", "resgatar", "resgate"):
		if not args.input_csv:
			raise ValueError("No modo resgatar, informe o arquivo CSV da trajetoria original")

		data = load_csv_first_vehicle(args.input_csv)
		progress_print(f"VIN: {data['vehicle_id']}")
		progress_print(f"Pontos: {len(data['trajectory'])}")
		progress_print(f"Hash: {data['hash']}")

		wallet_mode = input("Resgatar com carteira Real ou Pseudonimo? (R/P): ").strip().lower()
		if wallet_mode in ("p", "pseudonimo", "pseudonimo"):
			if args.pseudonym_seed_file:
				pseudonym_address, chosen_key = resolve_pseudonym_private_key(
					seed_file=args.pseudonym_seed_file,
					hd_index=args.pseudonym_hd_index,
				)
				progress_print(
					f"Carteira pseudonima derivada da seed no indice {args.pseudonym_hd_index}: {pseudonym_address}"
				)
			else:
				chosen_key = args.pseudonym_private_key
				if not chosen_key:
					chosen_key = input("Informe a chave privada da carteira pseudonima: ").strip()
				if not chosen_key:
					raise ValueError("Chave privada da carteira pseudonima nao informada")
		else:
			chosen_key = args.user_private_key

		zk_dir = resolve_zk_dir(args.zkp_dir)
		redeem_result = redeem_with_zk(
			deployment_file=args.deployment_file,
			private_key=chosen_key,
			trajectory=data["trajectory"],
			vehicle_id=data["vehicle_id"],
			zk_dir=zk_dir,
		)

		progress_print("\nResgate ZK enviado com sucesso")
		progress_print(f"Carteira emissora: {redeem_result['requester']}")
		progress_print(f"Poseidon root: {redeem_result['poseidon_root']}")
		progress_print(f"TX: {', '.join(redeem_result['tx_hashes'])}")
		return

	if not args.input_csv:
		raise ValueError("No modo enviar, informe o arquivo CSV")

	data = load_csv_first_vehicle(args.input_csv)
	user_address = Account.from_key(args.user_private_key).address
	progress_print(f"VIN: {data['vehicle_id']}")
	progress_print(f"Pontos: {len(data['trajectory'])}")
	progress_print(f"Hash: {data['hash']}")

	if args.audit_token_id is not None:
		onchain_hash = read_hash_onchain(args.deployment_file, args.audit_token_id)
		match = verify_hash_onchain(args.deployment_file, args.audit_token_id, data["hash"])
		progress_print("\nAUDITORIA MANUAL")
		progress_print(f"Token ID: {args.audit_token_id}")
		progress_print(f"Hash local:   {to_bytes32_hex(data['hash'])}")
		progress_print(f"Hash on-chain:{onchain_hash}")
		progress_print(f"Hash bate? {'SIM' if match else 'NAO'}")
		return

	progress_print("\nEscolha o modo de envio:")
	progress_print("  1 - Com ofuscacao  : oraculo gera opcoes de trajeto deslocado, voce escolhe")
	progress_print("  2 - Sem ofuscacao  : oraculo registra o trajeto original diretamente (com ZKP)")
	progress_print("  3 - Direto         : envia sem passar pelo oraculo (sem ZKP)")
	answer = input("Opcao (1/2/3): ").strip()

	if answer == "1":
		progress_print(
			"Modo offset: "
			+ ("map matching OSM ATIVADO" if args.enable_map_matching else "map matching OSM DESATIVADO")
		)
		payload = {
			"trajetoria": data["trajectory"],
			"vehicle_id": data["vehicle_id"],
			"attempts": args.attempts,
			"top_k": 5,
			"enable_map_matching": args.enable_map_matching,
			"search_radius_m": args.search_radius_m,
			"contract_params": strip_aux_fields(data["contract_params"]),
		}
		progress_print("Consultando oraculo para gerar opcoes...")
		start_process = time.perf_counter()
		try:
			resp = requests.post(
				f"{args.oracle_url}/processar_trajeto",
				json=payload,
				timeout=None,
			)
		except requests.exceptions.ReadTimeout as exc:
			raise RuntimeError("Timeout inesperado em /processar_trajeto") from exc
		except requests.exceptions.RequestException as exc:
			raise RuntimeError(f"Erro de comunicacao com o oraculo em /processar_trajeto: {exc}") from exc
		elapsed_process = time.perf_counter() - start_process
		progress_print(f"Oraculo respondeu em {elapsed_process:.3f}s")
		if resp.status_code != 200:
			raise RuntimeError(f"Erro no oraculo: {resp.status_code} - {resp.text}")

		body = resp.json()
		diag = body.get("diagnostico", {})
		if diag:
			progress_print(
				f"Diagnostico oraculo: map_matching_enabled={diag.get('map_matching_enabled')} "
				f"map_matching_available={diag.get('map_matching_available')} "
				f"processing_seconds={diag.get('processing_seconds')}"
			)
		progress_print("\nOpcao sem offset (referencia):")
		progress_print(f"Monetizacao original estimada: {body['original']['e1_reais']:.6f} BRL")
		progress_print("Valores das opcoes abaixo sao estimativas ate a confirmacao on-chain.")
		print_options_table(body["opcoes"])

		while True:
			selected = input("Escolha a opcao desejada (1-5): ").strip()
			try:
				selected_idx = int(selected)
			except ValueError:
				progress_print("Opcao invalida. Tente novamente.")
				continue
			if selected_idx < 1 or selected_idx > len(body["opcoes"]):
				progress_print("Opcao invalida. Tente novamente.")
				continue
			break

		final_micro = int(body["opcoes"][selected_idx - 1]["monetizacao"]["private_final_e1_micro"])
		min_value_micro = None
		if final_micro <= 0:
			progress_print("Saldo final calculado = 0.")
			bump = input("Deseja aumentar para 1 micro (0.000001 BRL)? (S/N): ").strip().lower()
			if bump in ("s", "sim", "y", "yes"):
				min_value_micro = 1
			else:
				progress_print("Operacao cancelada: monetizacao zero.")
				return

		confirm_payload = {
			"request_id": body["request_id"],
			"option_index": selected_idx,
		}
		if min_value_micro is not None:
			confirm_payload["min_value_micro"] = min_value_micro
		progress_print("Confirmando opcao com o oraculo...")
		start_confirm = time.perf_counter()
		try:
			conf = requests.post(
				f"{args.oracle_url}/confirmar_opcao",
				json=confirm_payload,
				timeout=None,
			)
		except requests.exceptions.ReadTimeout as exc:
			raise RuntimeError("Timeout inesperado em /confirmar_opcao") from exc
		except requests.exceptions.RequestException as exc:
			raise RuntimeError(f"Erro de comunicacao com o oraculo em /confirmar_opcao: {exc}") from exc
		elapsed_confirm = time.perf_counter() - start_confirm
		progress_print(f"Confirmacao recebida em {elapsed_confirm:.3f}s")
		if conf.status_code != 200:
			raise RuntimeError(f"Erro ao confirmar: {conf.status_code} - {conf.text}")

		conf_body = conf.json()
		progress_print("\nSelecao confirmada e armazenada na blockchain pelo oraculo")
		progress_print(f"Carteira do oraculo: {conf_body['carteira_oraculo']}")
		progress_print(f"Hash original armazenado: {conf_body['hash_original']}")
		progress_print(f"Monetizado: {conf_body['monetizacao_e1_reais']:.6f} BRL")
		progress_print(f"TX: {', '.join(conf_body['tx_hashes'])}")

		token_guess = input("Se quiser auditar agora, informe tokenId (Enter para pular): ").strip()
		if token_guess:
			try:
				token_id = int(token_guess)
				onchain_hash = read_hash_onchain(args.deployment_file, token_id)
				match = verify_hash_onchain(args.deployment_file, token_id, data["hash"])
				progress_print(f"Hash local:    {to_bytes32_hex(data['hash'])}")
				progress_print(f"Hash on-chain: {onchain_hash}")
				progress_print(f"Hash bate? {'SIM' if match else 'NAO'}")
			except ValueError:
				progress_print("tokenId invalido; pulando auditoria manual")
	elif answer == "2":
		# Modo sem ofuscacao via oraculo: registra trajeto original com ZKP
		progress_print("\nEnviando trajeto original ao oraculo para registro com ZKP (sem ofuscacao)...")
		payload = {
			"trajetoria": data["trajectory"],
			"vehicle_id": data["vehicle_id"],
			"contract_params": strip_aux_fields(data["contract_params"]),
		}
		start_reg = time.perf_counter()
		try:
			resp = requests.post(
				f"{args.oracle_url}/registrar_trajeto",
				json=payload,
				timeout=None,
			)
		except requests.exceptions.RequestException as exc:
			raise RuntimeError(f"Erro de comunicacao com o oraculo em /registrar_trajeto: {exc}") from exc
		elapsed_reg = time.perf_counter() - start_reg
		progress_print(f"Oraculo respondeu em {elapsed_reg:.3f}s")
		if resp.status_code != 200:
			raise RuntimeError(f"Erro no oraculo: {resp.status_code} - {resp.text}")

		reg_body = resp.json()
		progress_print("\nTrajeto registrado na blockchain pelo oraculo (sem ofuscacao)")
		progress_print(f"Hash original armazenado: {reg_body['hash_original']}")
		progress_print(f"Poseidon root: {reg_body.get('poseidon_root', 'N/A')}")
		progress_print(f"ZKP habilitado: {reg_body.get('zkp_enabled')}")
		progress_print(f"Monetizacao: {reg_body['monetizacao_e1_reais']:.6f} BRL")
		progress_print(f"TX: {', '.join(reg_body['tx_hashes'])}")
	else:
		# Modo 3 ou qualquer outro: envia sem passar pelo oraculo
		progress_print("\nUsuario optou por envio direto (sem oraculo)")
		progress_print("Dados confirmados do trajeto original:")
		progress_print(f"VIN: {data['vehicle_id']}")
		progress_print(f"Hash original: {data['hash']}")
		progress_print(f"Distancia aprox: {trajectory_distance_km(data['trajectory']):.4f} km")

		direct = send_direct_without_offset(
			deployment_file=args.deployment_file,
			private_key=args.user_private_key,
			recipient=user_address,
			contract_params=strip_aux_fields(data["contract_params"]),
			hash_original=data["hash"],
			vehicle_id=data["vehicle_id"],
			estimated_e1_micro=simulate_e1_value(data["contract_params"]),
		)

		progress_print("\nEnvio direto concluido")
		progress_print(f"Carteira do usuario: {user_address}")
		progress_print(f"Monetizacao estimada: {direct['estimated_e1_reais']:.6f} BRL")
		progress_print(f"Token mintado: {direct['minted_token_id']}")
		progress_print(f"Hash on-chain: {direct['onchain_hash']}")
		progress_print(f"Hash bate? {'SIM' if direct['hash_match'] else 'NAO'}")
		progress_print(f"TX: {', '.join(direct['tx_hashes'])}")


if __name__ == "__main__":
	main()

