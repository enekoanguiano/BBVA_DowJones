"""
Calibración y simulación Monte Carlo de carteras.

Cada activo sigue un movimiento browniano geométrico (GBM) con correlaciones
estimadas sobre los log-retornos diarios históricos:
    dS_i / S_i = mu_i dt + sigma_i dW_i ,   corr(dW_i, dW_j) = rho_ij
Es el mismo modelo que genera los datos sintéticos del notebook (S0 = 100,
MU = 0.01, 20 pasos trimestrales).
"""
import numpy as np
import pandas as pd

DIAS = 252
RF = 0.01  # MU del notebook, usado como tipo libre de riesgo


def calibrar(precios, tickers, anios_hist=5.0, fecha_fin=None):
    """Estima drift y covarianza anualizados de los log-retornos diarios."""
    p = precios[tickers]
    if fecha_fin is not None:
        p = p.loc[:fecha_fin]
    if anios_hist:
        inicio = p.index[-1] - pd.DateOffset(days=int(round(anios_hist * 365.25)))
        p = p.loc[inicio:]
    p = p.dropna()
    if len(p) < 60:
        raise ValueError("No hay suficientes datos comunes para esos activos (mínimo 60 sesiones).")
    lr = np.log(p).diff().dropna()
    mu_log = lr.mean().values * DIAS                     # drift de log-precio
    cov = lr.cov().values * DIAS
    sigma = np.sqrt(np.diag(cov))
    corr = cov / np.outer(sigma, sigma)
    return {
        "tickers": list(tickers),
        "mu_log": mu_log,
        "mu": mu_log + 0.5 * sigma ** 2,                 # drift aritmético del GBM
        "sigma": sigma,
        "cov": cov,
        "corr": corr,
        "precios": p,
        "ultimo": p.iloc[-1].values,
        "fecha_ini": p.index[0],
        "fecha_fin": p.index[-1],
    }


def _cholesky(corr):
    try:
        return np.linalg.cholesky(corr)
    except np.linalg.LinAlgError:  # por si la matriz no es definida positiva
        w, v = np.linalg.eigh(corr)
        c = v @ np.diag(np.clip(w, 1e-10, None)) @ v.T
        d = np.sqrt(np.diag(c))
        return np.linalg.cholesky(c / np.outer(d, d))


def simular_ratios(mu, sigma, corr, n_sims, n_pasos, dt, rng):
    """Trayectorias S_t/S_0 correlacionadas: (n_sims, n_pasos, n_activos), sin t0."""
    L = _cholesky(corr)
    z = rng.standard_normal((n_sims, n_pasos, len(mu))) @ L.T
    inc = (mu - 0.5 * sigma ** 2) * dt + sigma * np.sqrt(dt) * z
    return np.exp(np.cumsum(inc, axis=1))


def valor_cartera(ratios, pesos, rebalanceo):
    """Valor de 1€ invertido: (n_sims, n_pasos + 1) incluyendo t0."""
    n = ratios.shape[0]
    if not rebalanceo:                                   # comprar y mantener
        v = ratios @ pesos
    else:                                                # rebalanceo en cada paso
        prev = np.concatenate([np.ones((n, 1, ratios.shape[2])), ratios[:, :-1]], axis=1)
        r = ratios / prev - 1.0
        v = np.cumprod(1.0 + r @ pesos, axis=1)
    return np.concatenate([np.ones((n, 1)), v], axis=1)


def metricas_analiticas(cal, pesos):
    mu_p = float(pesos @ cal["mu"])
    vol_p = float(np.sqrt(pesos @ cal["cov"] @ pesos))
    contrib = pesos * (cal["cov"] @ pesos) / vol_p ** 2 if vol_p > 0 else pesos * 0
    return mu_p, vol_p, contrib


def simular_cartera(cal, pesos, capital, horizonte, n_sims, drift="historico",
                    rebalanceo=False, semilla=0):
    pesos = np.asarray(pesos, float)
    if drift == "neutral":
        mu = np.full(len(pesos), RF)
    elif drift == "contraido":   # media entre histórico y RF: más prudente
        mu = 0.5 * (cal["mu"] + RF)
    else:
        mu = cal["mu"]
    pasos_anio = 52 if horizonte <= 2 else 12
    n_pasos = max(2, int(round(horizonte * pasos_anio)))
    dt = horizonte / n_pasos
    rng = np.random.default_rng(semilla)
    ratios = simular_ratios(mu, cal["sigma"], cal["corr"], n_sims, n_pasos, dt, rng)
    v = valor_cartera(ratios, pesos, rebalanceo) * capital

    t = np.linspace(0, horizonte, n_pasos + 1)
    pct = np.percentile(v, [5, 25, 50, 75, 95], axis=0)
    final = v[:, -1]
    perdida = capital - final
    var95 = float(np.percentile(perdida, 95))
    cvar95 = float(perdida[perdida >= var95].mean())
    rent = final / capital
    cagr = rent ** (1 / horizonte) - 1
    # máximo drawdown por trayectoria
    dd = (v / np.maximum.accumulate(v, axis=1) - 1).min(axis=1)

    mu_p = float(pesos @ mu)
    vol_p = float(np.sqrt(pesos @ cal["cov"] @ pesos))
    contrib = pesos * (cal["cov"] @ pesos) / vol_p ** 2

    # Por activo (cada uno por separado)
    fin_activos = ratios[:, -1, :]
    activos = []
    for i, tk in enumerate(cal["tickers"]):
        activos.append({
            "ticker": tk,
            "peso": float(pesos[i]),
            "precio": float(cal["ultimo"][i]),
            "mu": float(mu[i]),
            "mu_hist": float(cal["mu"][i]),
            "sigma": float(cal["sigma"][i]),
            "contrib_riesgo": float(contrib[i]),
            "precio_mediana": float(cal["ultimo"][i] * np.median(fin_activos[:, i])),
            "precio_p5": float(cal["ultimo"][i] * np.percentile(fin_activos[:, i], 5)),
            "precio_p95": float(cal["ultimo"][i] * np.percentile(fin_activos[:, i], 95)),
            "prob_sube": float((fin_activos[:, i] > 1).mean()),
        })

    hist, bins = np.histogram(final, bins=50)
    idx_muestra = rng.choice(n_sims, size=min(25, n_sims), replace=False)
    return {
        "t": t.tolist(),
        "percentiles": {k: pct[i].tolist() for i, k in enumerate(["p5", "p25", "p50", "p75", "p95"])},
        "media": v.mean(axis=0).tolist(),
        "muestras": v[idx_muestra].tolist(),
        "hist": {"cuentas": hist.tolist(), "bordes": bins.tolist()},
        "resumen": {
            "capital": capital,
            "valor_esperado": float(final.mean()),
            "valor_mediano": float(np.median(final)),
            "p5": float(np.percentile(final, 5)),
            "p95": float(np.percentile(final, 95)),
            "rent_esperada_anual": float(np.mean(rent) ** (1 / horizonte) - 1),
            "cagr_mediano": float(np.median(cagr)),
            "mu_anual": mu_p,
            "vol_anual": vol_p,
            "sharpe": (mu_p - RF) / vol_p if vol_p > 0 else None,
            "prob_perdida": float((final < capital).mean()),
            "var95": var95,
            "cvar95": cvar95,
            "drawdown_mediano": float(np.median(dd)),
        },
        "activos": activos,
    }


def historico_cartera(cal, pesos, base=100.0):
    """Evolución histórica (comprar y mantener) de la cartera y de cada activo."""
    p = cal["precios"]
    norm = p / p.iloc[0]
    paso = max(1, len(norm) // 400)  # aligera el gráfico
    sub = norm.iloc[::paso]
    if sub.index[-1] != norm.index[-1]:
        sub = pd.concat([sub, norm.iloc[[-1]]])
    cartera = (sub.values @ np.asarray(pesos)) * base
    return {
        "fechas": [d.strftime("%Y-%m-%d") for d in sub.index],
        "cartera": cartera.tolist(),
        "activos": {tk: (sub[tk].values * base).tolist() for tk in cal["tickers"]},
    }


def frontera(cal, n=4000, semilla=0, max_peso=1.0):
    """Carteras aleatorias (solo largos) + mínima varianza y máximo Sharpe."""
    rng = np.random.default_rng(semilla)
    k = len(cal["tickers"])
    W = rng.dirichlet(np.ones(k) * 0.7, size=n)
    W = np.vstack([W, np.eye(k)])
    if max_peso < 1:
        W = W[(W <= max_peso + 1e-9).all(axis=1)]
    mu = W @ cal["mu"]
    vol = np.sqrt(np.einsum("ij,jk,ik->i", W, cal["cov"], W))
    sharpe = (mu - RF) / vol
    i_s, i_v = int(np.argmax(sharpe)), int(np.argmin(vol))
    return {
        "mu": mu.tolist(), "vol": vol.tolist(), "sharpe": sharpe.tolist(),
        "max_sharpe": {"pesos": W[i_s].tolist(), "mu": float(mu[i_s]), "vol": float(vol[i_s]),
                       "sharpe": float(sharpe[i_s])},
        "min_var": {"pesos": W[i_v].tolist(), "mu": float(mu[i_v]), "vol": float(vol[i_v]),
                    "sharpe": float(sharpe[i_v])},
        "activos": [{"ticker": t, "mu": float(cal["mu"][i]), "vol": float(cal["sigma"][i])}
                    for i, t in enumerate(cal["tickers"])],
    }
