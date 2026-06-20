# ======================================================================
#                               ANÁLISES INICIAIS
# ======================================================================

import numpy as np
import pandas as pd

# Mostrar floats sem notação científica
pd.set_option("display.float_format", lambda v: f"{v:.6f}")

# ======================================================================
# PARTE 1 - IMPORTANDO E ARRUMANDO OS DADOS
# ======================================================================

df = pd.read_csv("../data/trajetos/vehicles_step_sim_1.csv")

city_gasoline = [10.3, 10.3, 10.3, 10.3, 12.15, 12.15, 12.15, 12.15, 12.6, 12.6, 12.6, 12.6, 11.8, 12.83, 12.83, 12.83, 12.83, 11.6, 11.6, 11.6, 11.6, 11.6, 11.6, 11.6, 11.6, 11.6, 11.6, 11.6, 11.6, 11.6, 11.6, 12.0, 12.0]
road_gasoline = [11.3, 11.3, 11.3, 11.3, 13.65, 13.65, 13.65, 13.65, 13.9, 13.9, 13.9, 13.9, 13.3, 14.44, 14.44, 14.44, 14.44, 14.1, 14.1, 14.1, 14.1, 14.1, 14.1, 14.1, 14.1, 14.1, 14.1, 14.1, 14.1, 14.1, 14.1, 14.4, 14.4]
city_ethanol  = [" ", " ", " ", " ", 8.2, 8.2, 8.2, 8.2, 8.9, 8.9, 8.9, 8.9, 8.1, 9.11, 9.11, 9.11, 9.11, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8.3, 8.3]
road_ethanol  = [" ", " ", " ", " ", 9.5, 9.5, 9.5, 9.5, 9.8, 9.8, 9.8, 9.8, 9.2, 10.26, 10.26, 10.26, 10.26, 9.8, 9.8, 9.8, 9.8, 9.8, 9.8, 9.8, 9.8, 9.8, 9.8, 9.8, 9.8, 9.8, 9.8, 10.0, 10.0]

def assign_series(vec, name):
    if len(vec) == 1:
        df[name] = vec[0]
    elif len(vec) == len(df):
        df[name] = pd.to_numeric(pd.Series(vec), errors="coerce").values
    else:
        raise ValueError(f"Comprimento de {name} ({len(vec)}) difere do n de linhas ({len(df)})")

assign_series(city_gasoline, "city_gasoline")
assign_series(road_gasoline, "road_gasoline")
assign_series(city_ethanol,  "city_ethanol")
assign_series(road_ethanol,  "road_ethanol")

for col in ["city_gasoline", "road_gasoline", "city_ethanol", "road_ethanol"]:
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

Carbon_Price_European = [67.13, 67.13, 67.69, 67.69, 67.13, 67.13, 67.13, 67.13, 80.91, 80.74, 69.88, 67.13, 68.98,
                         67.13, 67.13, 67.13, 67.13, 80.91, 80.91, 80.92, 78.64, 78.64, 78.64, 78.64, 78.64, 69.56,
                         68.69, 68.69, 67.13, 67.10, 67.69, 67.91, 65.25]
assign_series(Carbon_Price_European, "Carbon_Price_European")

Euro_price = [6.1708, 6.1708, 6.1447, 6.1447, 6.1708, 6.1708, 6.1708, 6.1708, 6.1031, 6.0524, 5.9424, 6.1708, 6.1315,
              6.1708, 6.1708, 6.1708, 6.1708, 6.1031, 6.1031, 5.9710, 5.9851, 5.9851, 5.9851, 5.9851, 5.9851,
              6.2429, 6.2070, 6.2070, 6.1708, 6.1708, 6.1447, 6.1031, 6.2200]
assign_series(Euro_price, "Euro_price")

df["Real_price"] = pd.to_numeric(df["Carbon_Price_European"], errors="coerce") * pd.to_numeric(df["Euro_price"], errors="coerce")

df["Tanque_gasoline"] = 100 - pd.to_numeric(df["ethanol (%)"], errors="coerce")

# ======================================================================
# PARTE 2 - CALCULANDO A META DE EMISSÃO
# ======================================================================

def safe_div(numerador, denominador):
    numerador = pd.to_numeric(numerador, errors="coerce")
    denominador = pd.to_numeric(denominador, errors="coerce")
    out = np.divide(numerador, denominador, out=np.zeros_like(numerador, dtype=float), where=(denominador!=0))
    out[~np.isfinite(out)] = 0.0
    return out

EMISSAO_GASOLINA = 1.720
EMISSAO_ETANOL   = 1.510

dist_highway = pd.to_numeric(df["highway (distance)"], errors="coerce")
dist_city    = pd.to_numeric(df["city (distance)"],    errors="coerce")

p_gas = pd.to_numeric(df["Tanque_gasoline"], errors="coerce")/100.0
p_etanol = pd.to_numeric(df["ethanol (%)"], errors="coerce")/100.0

parte_1_1 = dist_highway * ( safe_div(1, df["road_gasoline"]) * p_gas * EMISSAO_GASOLINA ) * 1000
parte_1_2 = dist_highway * ( safe_div(1, df["road_ethanol"])  * p_etanol * EMISSAO_ETANOL   ) * 1000
parte_1_1[~np.isfinite(parte_1_1)] = 0
parte_1_2[~np.isfinite(parte_1_2)] = 0
df["parte_1"] = parte_1_1 + parte_1_2

parte_2_1 = dist_city * ( safe_div(1, df["city_gasoline"]) * p_gas * EMISSAO_GASOLINA ) * 1000
parte_2_2 = dist_city * ( safe_div(1, df["city_ethanol"])  * p_etanol * EMISSAO_ETANOL ) * 1000
parte_2_1[~np.isfinite(parte_2_1)] = 0
parte_2_2[~np.isfinite(parte_2_2)] = 0
df["parte_2"] = parte_2_1 + parte_2_2

df["Meta_CO2"] = df["parte_1"] + df["parte_2"]

df["Diff"] = df["Meta_CO2"] - pd.to_numeric(df["17_etanol_original_gas_1720_flex"], errors="coerce")

df["e1"] = df["Diff"] * pd.to_numeric(df["Real_price"], errors="coerce") / 1_000_000.0


