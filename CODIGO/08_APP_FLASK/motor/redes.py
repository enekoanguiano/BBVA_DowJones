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
import torch

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


class ModeloTorch(torch.nn.Module):

    def __init__(self, cfg, input_dim):
        super().__init__()

        tipo = cfg["tipo"]
        units = cfg["units"]
        capas = cfg["capas"]
        bi = cfg.get("bi", False)
        dropout = cfg.get("dropout", 0.05)

        if tipo == "mlp":

            capas_red = [
                torch.nn.Flatten(),
                torch.nn.Linear(input_dim, units),
                torch.nn.ReLU(),
                torch.nn.Dropout(dropout)
            ]

            for _ in range(capas - 1):
                capas_red += [
                    torch.nn.Linear(units, units),
                    torch.nn.ReLU(),
                    torch.nn.Dropout(dropout)
                ]

            capas_red.append(torch.nn.Linear(units, 1))

            self.net = torch.nn.Sequential(*capas_red)

        else:

            Cell = {
                "rnn": torch.nn.RNN,
                "gru": torch.nn.GRU,
                "lstm": torch.nn.LSTM
            }[tipo]

            self.rnn = Cell(
                input_size=3,
                hidden_size=units,
                num_layers=capas,
                batch_first=True,
                bidirectional=bi,
                dropout=dropout if capas > 1 else 0.0
            )

            self.bi = bi
            self.dropout = torch.nn.Dropout(dropout)

            self.out = torch.nn.Linear(
                units * (2 if bi else 1),
                1
            )

    def forward(self, x):

        if hasattr(self, "net"):
            return self.net(x).squeeze(-1)

        _, h = self.rnn(x)

        if isinstance(h, tuple):
            h = h[0]

        if self.bi:
            h = torch.cat([h[-2], h[-1]], dim=1)
        else:
            h = h[-1]

        return self.out(self.dropout(h)).squeeze(-1)

class GestorRedes:

    def __init__(self, carpeta):

        self.carpeta = carpeta
        self.modelos = {}
        self.norm = None

        ruta = os.path.join(carpeta, "modelo_final.pt")

        if not os.path.isfile(ruta):
            raise FileNotFoundError(
                f"No se encuentra el modelo: {ruta}"
            )

        checkpoint = torch.load(
            ruta,
            map_location="cpu",
            weights_only=False
        )

        cfg = checkpoint["config"]
        nombre = checkpoint["modelo_nombre"]

        modelo = ModeloTorch(
            cfg,
            checkpoint["input_dim"]
        )

        modelo.load_state_dict(
            checkpoint["model_state_dict"]
        )

        modelo.eval()

        # Número de parámetros
        modelo.n_params = sum(
            p.numel() for p in modelo.parameters()
        )

        self.modelos[nombre] = modelo

        # Normalización del entrenamiento
        self.norm = {
            "m": np.asarray(checkpoint["media_X"], dtype=float),
            "s": np.asarray(checkpoint["std_X"], dtype=float),
            "ys": float(checkpoint["std_y"])
        }

        # Comprobar dimensiones
        self.num_pasos = checkpoint["num_pasos"]

        print(f"Modelo cargado: {nombre}")
        print(f"Arquitectura: {cfg}")
        print(f"Ruta: {ruta}")

    @property
    def disponibles(self):
        return list(self.modelos)

    def predecir(self, X_ratio, calib_frac=0.2, rng=None):

        X = features(X_ratio)

        if X.shape[1] != self.num_pasos:
            raise ValueError(
                f"Se esperaban {self.num_pasos} pasos "
                f"y se recibieron {X.shape[1]}"
            )

        Xs = (
            X - self.norm["m"]
        ) / self.norm["s"]

        X_tensor = torch.tensor(
            Xs,
            dtype=torch.float32
        )

        resultados = {}

        with torch.no_grad():

            for nombre, modelo in self.modelos.items():

                pred = modelo(X_tensor).cpu().numpy()

                pred = pred * self.norm["ys"]

                resultados[nombre] = np.maximum(
                    pred,
                    0.0
                )

        return resultados, {
            "modo": "exacta",
            "eval_idx": np.arange(len(X))
        }