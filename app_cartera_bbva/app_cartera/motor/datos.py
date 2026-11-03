"""Carga de df_diario (precios diarios OHLCV de los valores del Dow Jones)."""
import ast
import os

import numpy as np
import pandas as pd


def _leer(ruta):
    ext = os.path.splitext(ruta)[1].lower()
    if ext == ".parquet":
        return pd.read_parquet(ruta)
    if ext in (".pkl", ".pickle"):
        return pd.read_pickle(ruta)
    if ext == ".csv":
        return pd.read_csv(ruta, header=[0, 1], index_col=0, parse_dates=True)
    raise ValueError(f"Formato de datos no soportado: {ruta}")


def cargar_precios(ruta, campo="close"):
    """
    Devuelve un DataFrame (fechas x tickers) con el precio `campo`.
    Acepta columnas MultiIndex (ticker, campo) o nombres tipo "('AAPL', 'close')".
    """
    df = _leer(ruta)
    if "date" in df.columns:
        df = df.set_index("date")
    if not isinstance(df.columns, pd.MultiIndex):
        tuplas = [ast.literal_eval(c) if isinstance(c, str) and c.startswith("(") else c
                  for c in df.columns]
        df.columns = pd.MultiIndex.from_tuples(tuplas)
    # Detecta en qué nivel está el campo (close/open...)
    nivel = 1 if campo in df.columns.get_level_values(1) else 0
    precios = df.xs(campo, axis=1, level=nivel)
    precios.index = pd.to_datetime(precios.index)
    precios = precios.sort_index().astype(float)
    precios.columns = [str(c).upper() for c in precios.columns]
    return precios.replace([np.inf, -np.inf], np.nan)
