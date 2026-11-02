"""
Inferencia de las redes recurrentes entrenadas en red_NN.ipynb (RNN, GRU, LSTM).

Las redes estiman el payoff de una call asiática sobre 3 activos:
    V_T = ( sum_i  media_geométrica_t( S_i(t) / S_i(0) )  -  E )^+     con E = 3
a partir de los 20 log-retornos trimestrales (T = 5 años) de cada activo.

La inferencia se hace en NumPy (no hace falta PyTorch en el servidor). Si PyTorch
está instalado se usa torch.load para leer los pesos; si no, se usa un lector
propio del formato .pt (zip + pickle).
"""
import json
import os
import pickle
import zipfile
from collections import OrderedDict

import numpy as np

# Parámetros del notebook
MU, TTM, N_PASOS, E = 0.01, 5, 20, 3.0
DT = TTM / N_PASOS
CELDAS = ("rnn", "gru", "lstm")


# --------------------------------------------------------------------------- #
#  Carga de pesos
# --------------------------------------------------------------------------- #
_DTYPES = {
    "FloatStorage": np.float32, "DoubleStorage": np.float64,
    "HalfStorage": np.float16, "LongStorage": np.int64,
    "IntStorage": np.int32, "BoolStorage": np.bool_,
}


def _rebuild_tensor(storage, offset, size, stride, *args):
    itemsize = storage.itemsize
    arr = np.lib.stride_tricks.as_strided(
        storage[offset:], shape=tuple(size),
        strides=tuple(s * itemsize for s in stride))
    return np.array(arr)


class _TorchUnpickler(pickle.Unpickler):
    def __init__(self, f, zf, prefix):
        super().__init__(f)
        self.zf, self.prefix = zf, prefix

    def find_class(self, module, name):
        if module == "torch._utils" and name == "_rebuild_tensor_v2":
            return _rebuild_tensor
        if module == "torch" and name in _DTYPES:
            return _DTYPES[name]
        if module == "collections" and name == "OrderedDict":
            return OrderedDict
        if module == "torch._utils" and name == "_rebuild_parameter":
            return lambda data, *a: data
        raise pickle.UnpicklingError(f"Clase no permitida en el checkpoint: {module}.{name}")

    def persistent_load(self, pid):
        _, dtype, key, _loc, _n = pid
        raw = self.zf.read(f"{self.prefix}/data/{key}")
        return np.frombuffer(raw, dtype=dtype)


def cargar_state_dict(path):
    """Devuelve {nombre: np.ndarray} a partir de un .pt guardado con torch.save."""
    try:
        import torch  # noqa: F401
        sd = torch.load(path, map_location="cpu", weights_only=True)
        return {k: v.detach().cpu().numpy() for k, v in sd.items()}
    except ImportError:
        pass
    with zipfile.ZipFile(path) as zf:
        pkl = [n for n in zf.namelist() if n.endswith("data.pkl")][0]
        prefix = pkl.rsplit("/", 1)[0]
        with zf.open(pkl) as f:
            return dict(_TorchUnpickler(f, zf, prefix).load())


# --------------------------------------------------------------------------- #
#  Forward en NumPy (mismo cálculo que torch.nn.RNN / GRU / LSTM, eval mode)
# --------------------------------------------------------------------------- #
def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


class RedRecurrente:
    def __init__(self, celda, state_dict):
        self.celda = celda
        p = {k: v.astype(np.float64) for k, v in state_dict.items()}
        self.W_ih, self.W_hh = p["rnn.weight_ih_l0"], p["rnn.weight_hh_l0"]
        self.b_ih, self.b_hh = p["rnn.bias_ih_l0"], p["rnn.bias_hh_l0"]
        self.W_out, self.b_out = p["out.weight"], p["out.bias"]
        self.units = self.W_hh.shape[1]
        self.n_params = int(sum(v.size for v in state_dict.values()))

    def __call__(self, x):
        """x: (n, pasos, 3) ya estandarizado -> (n,) payoff escalado."""
        n, T, _ = x.shape
        H = self.units
        h = np.zeros((n, H))
        c = np.zeros((n, H))
        gx_all = x @ self.W_ih.T + self.b_ih          # (n, T, k*H)
        for t in range(T):
            gx = gx_all[:, t]
            gh = h @ self.W_hh.T + self.b_hh
            if self.celda == "rnn":
                h = np.tanh(gx + gh)
            elif self.celda == "gru":
                r = _sigmoid(gx[:, :H] + gh[:, :H])
                z = _sigmoid(gx[:, H:2 * H] + gh[:, H:2 * H])
                nn_ = np.tanh(gx[:, 2 * H:] + r * gh[:, 2 * H:])
                h = (1.0 - z) * nn_ + z * h
            else:  # lstm: i, f, g, o
                g = gx + gh
                i = _sigmoid(g[:, :H])
                f = _sigmoid(g[:, H:2 * H])
                gg = np.tanh(g[:, 2 * H:3 * H])
                o = _sigmoid(g[:, 3 * H:])
                c = f * c + i * gg
                h = o * np.tanh(c)
        return (h @ self.W_out.T + self.b_out)[:, 0]


# --------------------------------------------------------------------------- #
#  Funciones del notebook
# --------------------------------------------------------------------------- #
def payoff(X_ratio):
    """V_T = (suma de las 3 medias geométricas - E)^+ ; X_ratio: (n, 20, 3) = S_t / S_0."""
    gmean = np.exp(np.log(X_ratio).mean(axis=1))
    return np.maximum(gmean.sum(axis=1) - E, 0.0)


def descontar(v):
    return np.exp(-MU * N_PASOS * DT) * v


def features(X_ratio):
    """Log-retornos por paso, igual que en el notebook."""
    return np.diff(np.log(X_ratio), axis=1, prepend=0.0)


class GestorRedes:
    """Carga los tres modelos y la normalización usada en el entrenamiento."""

    def __init__(self, carpeta):
        self.carpeta = carpeta
        self.modelos = {}
        for c in CELDAS:
            ruta = os.path.join(carpeta, f"best_model_{c}.pt")
            if os.path.exists(ruta):
                self.modelos[c] = RedRecurrente(c, cargar_state_dict(ruta))
        self.norm = None
        ruta_norm = os.path.join(carpeta, "normalizacion.json")
        if os.path.exists(ruta_norm):
            with open(ruta_norm) as f:
                d = json.load(f)
            self.norm = {"m": np.array(d["m"]), "s": np.array(d["s"]), "ys": float(d["ys"])}

    @property
    def disponibles(self):
        return list(self.modelos)

    def predecir(self, X_ratio, calib_frac=0.2, rng=None):
        """
        Devuelve {celda: payoff_predicho} y el modo de normalización usado.

        - Con normalizacion.json (m, s, ys exactos del entrenamiento) la predicción
          es directa.
        - Sin él, se estandariza con las estadísticas de las propias simulaciones y
          la escala del payoff (ys) se ajusta por mínimos cuadrados sobre una
          fracción de calibración de las trayectorias. Esa fracción se excluye
          al medir el error.
        """
        X = features(X_ratio)
        n = len(X)
        out = {}
        if self.norm is not None:
            Xs = (X - self.norm["m"]) / self.norm["s"]
            for c, mdl in self.modelos.items():
                out[c] = np.maximum(mdl(Xs) * self.norm["ys"], 0.0)
            return out, {"modo": "exacta", "eval_idx": np.arange(n)}

        rng = rng or np.random.default_rng(0)
        perm = rng.permutation(n)
        n_cal = max(200, int(calib_frac * n))
        cal, ev = perm[:n_cal], perm[n_cal:]
        m, s = X.mean((0, 1)), X.std((0, 1))
        Xs = (X - m) / s
        y_cal = payoff(X_ratio[cal])
        for c, mdl in self.modelos.items():
            raw = mdl(Xs)
            ys = float(raw[cal] @ y_cal / max(raw[cal] @ raw[cal], 1e-12))
            out[c] = np.maximum(raw * ys, 0.0)
        return out, {"modo": "calibrada", "eval_idx": ev}
