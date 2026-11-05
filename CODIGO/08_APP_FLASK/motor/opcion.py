"""
Módulo de redes neuronales: valoración de la call asiática del notebook sobre
3 activos reales, comparando Monte Carlo exacto con RNN / GRU / LSTM.
"""
import time

import numpy as np

from . import redes
from .simulacion import simular_ratios


def valorar(cal, gestor, n_sims=20000, semilla=0):
    if len(cal["tickers"]) != 3:
        raise ValueError("Las redes se entrenaron con exactamente 3 activos.")
    if not gestor.modelos:
        raise ValueError("No se encontraron modelos .pt en la carpeta de modelos.")
    rng = np.random.default_rng(semilla)

    # Medida neutral al riesgo, igual que los datos sintéticos (MU = 0.01, dt = 0.25)
    mu = np.full(3, redes.MU)
    t0 = time.perf_counter()
    X_ratio = simular_ratios(mu, cal["sigma"], cal["corr"], n_sims, redes.N_PASOS, redes.DT, rng)
    y = redes.payoff(X_ratio)
    t_mc = time.perf_counter() - t0

    t0 = time.perf_counter()
    preds, info = gestor.predecir(X_ratio, rng=rng)
    t_nn = (time.perf_counter() - t0) / max(1, len(preds))

    ev = info["eval_idx"]
    y_ev = y[ev]
    prima_mc = float(redes.descontar(y_ev).mean())
    err_mc = float(redes.descontar(y_ev).std() / np.sqrt(len(ev)))

    modelos = []
    muestra = rng.choice(len(ev), size=min(1500, len(ev)), replace=False)
    disp = {"real": y_ev[muestra].tolist()}
    for c, p in preds.items():
        p_ev = p[ev]
        rmse = float(np.sqrt(np.mean((p_ev - y_ev) ** 2)))
        mae = float(np.mean(np.abs(p_ev - y_ev)))
        ss = float(np.sum((y_ev - y_ev.mean()) ** 2))
        r2 = 1 - float(np.sum((p_ev - y_ev) ** 2)) / ss if ss > 0 else None
        prima = float(redes.descontar(p_ev).mean())
        modelos.append({
            "celda": c,
            "params": gestor.modelos[c].n_params,
            "prima": prima,
            "err_prima_pct": 100 * (prima - prima_mc) / prima_mc if prima_mc > 0 else None,
            "rmse": rmse, "mae": mae, "r2": r2,
        })
        disp[c] = p_ev[muestra].tolist()

    return {
        "tickers": cal["tickers"],
        "sigma": cal["sigma"].tolist(),
        "corr": cal["corr"].tolist(),
        "n_sims": n_sims,
        "n_eval": int(len(ev)),
        "normalizacion": info["modo"],
        "prima_mc": prima_mc,
        "err_estandar_mc": err_mc,
        "prob_ejercicio": float((y_ev > 0).mean()),
        "payoff_medio": float(y_ev.mean()),
        "tiempo_mc_ms": 1000 * t_mc,
        "tiempo_red_ms": 1000 * t_nn,
        "modelos": modelos,
        "dispersion": disp,
        "parametros": {"MU": redes.MU, "T": redes.TTM, "pasos": redes.N_PASOS, "E": redes.E},
    }
