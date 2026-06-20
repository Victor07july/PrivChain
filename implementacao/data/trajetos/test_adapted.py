# ======================================================================
#                    ANÁLISE DE EMISSÕES E MONETIZAÇÃO
# ======================================================================

import numpy as np
import pandas as pd

# Mostrar floats sem notação científica
pd.set_option("display.float_format", lambda v: f"{v:.6f}")

# ======================================================================
# PARTE 1 - IMPORTANDO O CSV
# ======================================================================

input_csv = "vehicles_step_sim_1.csv"
df = pd.read_csv(input_csv)

# ======================================================================
# PARTE 2 - LIMPEZA E CONVERSÃO DOS DADOS
# ======================================================================

numeric_cols = [
    "distance",
    "distance_city",
    "distance_highway",
    "speed",
    "acceleration",
    "CO2",
    "NOx",
    "PMx"
]

for col in numeric_cols:
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

# ======================================================================
# PARTE 3 - CONFIGURAÇÕES DE CONSUMO
# ======================================================================

# Consumo médio estimado (km/L)

CONSUMO = {

    "Gasoline": {
        "city": 10.3,
        "highway": 11.3,
        "emission_factor": 2310
    },

}

# ======================================================================
# PARTE 4 - PREÇO DO CARBONO
# ======================================================================

CARBON_PRICE_EURO = 67.13
EURO_TO_BRL = 6.17

REAL_PRICE = CARBON_PRICE_EURO * EURO_TO_BRL

# ======================================================================
# PARTE 5 - FUNÇÃO SAFE_DIV
# ======================================================================

def safe_div(numerador, denominador):

    numerador = pd.to_numeric(numerador, errors="coerce")
    denominador = pd.to_numeric(denominador, errors="coerce")

    out = np.divide(
        numerador,
        denominador,
        out=np.zeros_like(numerador, dtype=float),
        where=(denominador != 0)
    )

    out[~np.isfinite(out)] = 0.0

    return out

# ======================================================================
# PARTE 6 - DISTÂNCIA INCREMENTAL
# ======================================================================

# O CSV parece usar distância acumulada.
# Então calculamos o delta incremental.

df["delta_distance_city"] = (
    df.groupby("vehicle_id")["distance_city"]
    .diff()
    .fillna(df["distance_city"])
)

df["delta_distance_highway"] = (
    df.groupby("vehicle_id")["distance_highway"]
    .diff()
    .fillna(df["distance_highway"])
)

# Garantir que não existam negativos

df["delta_distance_city"] = (
    df["delta_distance_city"]
    .clip(lower=0)
)

df["delta_distance_highway"] = (
    df["delta_distance_highway"]
    .clip(lower=0)
)

# ======================================================================
# PARTE 7 - CO2 INCREMENTAL
# ======================================================================

# O CO2 do CSV também parece acumulado.
# Então calculamos o delta incremental.

df["CO2_delta"] = (
    df.groupby("vehicle_id")["CO2"]
    .diff()
    .fillna(df["CO2"])
)

df["CO2_delta"] = (
    df["CO2_delta"]
    .clip(lower=0)
)

# ======================================================================
# PARTE 8 - CÁLCULO DA META DE EMISSÃO
# ======================================================================

meta_co2 = []

for idx, row in df.iterrows():

    fuel = row["fuel_type"]

    # Caso combustível não exista na tabela
    if fuel not in CONSUMO:

        meta_co2.append(0)
        continue

    city_consumption = CONSUMO[fuel]["city"]
    highway_consumption = CONSUMO[fuel]["highway"]
    emission_factor = CONSUMO[fuel]["emission_factor"]

    dist_city = row["delta_distance_city"]
    dist_highway = row["delta_distance_highway"]

    # Emissão urbana
    city_emission = (
        dist_city *
        safe_div(1, city_consumption) *
        emission_factor
    )

    # Emissão rodoviária
    highway_emission = (
        dist_highway *
        safe_div(1, highway_consumption) *
        emission_factor
    )

    total = city_emission + highway_emission

    if not np.isfinite(total):
        total = 0

    meta_co2.append(total)

df["Meta_CO2"] = meta_co2

# ======================================================================
# PARTE 9 - DIFERENÇA ENTRE REAL E ESTIMADO
# ======================================================================

df["Diff"] = (
    df["Meta_CO2"] -
    df["CO2_delta"]
)

# ======================================================================
# PARTE 10 - MONETIZAÇÃO
# ======================================================================

df["e1"] = (
    df["Diff"] *
    REAL_PRICE
) / 1_000_000.0

df["source_csv"] = input_csv

# ======================================================================
# PARTE 11 - ESTATÍSTICAS
# ======================================================================

print("\n================ ESTATÍSTICAS ================\n")

print("Meta_CO2")
print(df["Meta_CO2"].describe())

print("\nCO2_delta")
print(df["CO2_delta"].describe())

print("\nDiff")
print(df["Diff"].describe())

print("\ne1")
print(df["e1"].describe())

# ======================================================================
# PARTE 12 - RESUMO POR VEÍCULO
# ======================================================================

vehicle_summary = df.groupby("vehicle_id").agg({

    "Meta_CO2": "sum",
    "CO2_delta": "sum",
    "Diff": "sum",
    "e1": "sum",
    "distance": "max",
    "source_csv": "first",

}).reset_index()

print("\n================ RESUMO POR VEÍCULO ================\n")

print(vehicle_summary)

# ======================================================================
# PARTE 13 - EXPORTANDO RESULTADOS
# ======================================================================

df.to_csv("resultado_completo.csv", index=False)

vehicle_summary.to_csv("resultado_por_veiculo.csv", index=False)

print("\nArquivos exportados com sucesso!")