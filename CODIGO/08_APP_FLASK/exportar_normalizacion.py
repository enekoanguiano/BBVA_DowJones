"""
Guarda en modelos/normalizacion.json las constantes de normalización con las que
se entrenaron las redes de red_NN.ipynb (m, s de los log-retornos y ys del payoff).

El notebook no las guardaba, así que se recalculan reproduciendo exactamente sus
pasos: misma semilla, misma permutación y mismo 70 % de entrenamiento.

Uso (en el equipo donde está datos_sinteticos.npy y con PyTorch instalado):
    python exportar_normalizacion.py ../DATOS/TRANSFORMADOS/datos_sinteticos.npy
"""
import json
import os
import sys

import numpy as np
import torch
from scipy.stats.mstats import gmean

E, SEED, N_SIMS = 3.0, 0, 100000


def main(ruta_npy):
    torch.manual_seed(SEED)
    data = np.load(ruta_npy)
    idx = torch.randperm(len(data))[:N_SIMS].numpy()
    data = data[idx]
    X_ratio = data[:, 1:, :] / data[:, :1, :]
    y = np.maximum(gmean(X_ratio, axis=1).sum(axis=1) - E, 0.0)
    X = np.diff(np.log(X_ratio), axis=1, prepend=0.0)
    n_tr = int(.70 * len(X))
    m, s = X[:n_tr].mean((0, 1)), X[:n_tr].std((0, 1))
    ys = y[:n_tr].std()
    destino = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
        "..", "..", "DATOS", "MODELOS", "normalizacion.json"
    )
    with open(destino, "w") as f:
        json.dump({"m": m.tolist(), "s": s.tolist(), "ys": float(ys),
                   "origen": os.path.abspath(ruta_npy)}, f, indent=2)
    print(f"Guardado {destino}\n  m = {m}\n  s = {s}\n  ys = {ys:.6f}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else
         os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "..", "DATOS", "TRANSFORMADOS", "datos_sinteticos.npy"
        ))
