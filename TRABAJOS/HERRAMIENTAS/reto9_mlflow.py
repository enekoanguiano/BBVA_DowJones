"""
reto9_mlflow.py - Evaluación grupal Herramientas 2
Reto 9: red recurrente (GRU) en PyTorch que predice el payoff de la call
asiática sobre 3 activos, con seguimiento de los entrenamientos en MLflow.

Se entrenan varias arquitecturas variando el número de neuronas de cada
capa (capa recurrente y capa densa) y cada una queda registrada como un
"run" en MLflow.
"""
import copy
import os
import time

import mlflow
import mlflow.pytorch
import numpy as np
import torch
from scipy.stats.mstats import gmean
from sklearn import metrics
from torch.utils.data import DataLoader, TensorDataset


# Configuración
# --------------------------------------------------

GRUPO = "MORADO"         # nombre (color) del grupo

DATA_PATH = (r"C:\Users\aiala\OneDrive - Mondragon Unibertsitatea\Escritorio"
             r"\RETO09_MORADO\26-27_3_R9_EQUIPO_MORADO\DATOS\TRANSFORMADOS"
             r"\datos_sinteticos.npy")
N_SIMS = 20000           # simulaciones usadas (sube para más calidad)
BATCH_SIZE = 256
LR = 0.001
EPOCHS = 40
PATIENCE = 5
CELL = 'gru'
SEED = 0

MU, TTM, N_PASOS, E = 0.01, 5, 20, 3.0
DT = TTM / N_PASOS

# Arquitecturas a probar: (neuronas capa recurrente, neuronas capa densa)
ARQUITECTURAS = [(4, 2), (8, 4), (16, 8), (32, 16), (64, 32)]


# Funciones del Reto 9
# --------------------------------------------------

def payoff(X):
    """V_T = (suma de las 3 medias geométricas - E)^+"""
    return np.maximum(gmean(X, axis=1).sum(axis=1) - E, 0.0)


def prima(V_T):
    """Prima en t0: payoff descontado."""
    return np.exp(-MU * N_PASOS * DT) * V_T


def cargar_datos():
    """Carga las simulaciones del Reto 9. Si no encuentra el fichero,
    genera trayectorias sintéticas (movimiento browniano geométrico)."""
    if os.path.exists(DATA_PATH):
        print(f'Datos cargados de {DATA_PATH}')
        data = np.load(DATA_PATH)
    else:
        print(f'No se encuentra {DATA_PATH}: se generan datos sintéticos')
        rng = np.random.default_rng(SEED)
        sigma = 0.2
        z = rng.standard_normal((100000, N_PASOS, 3))
        incr = (MU - 0.5 * sigma ** 2) * DT + sigma * np.sqrt(DT) * z
        paths = 100 * np.exp(np.cumsum(incr, axis=1))
        data = np.concatenate([np.full((100000, 1, 3), 100.0), paths], axis=1)
    return data


class Red(torch.nn.Module):
    """Capa recurrente -> capa densa -> salida (payoff)."""

    def __init__(self, cell, units_rnn, units_dense):
        super().__init__()
        Cell = {'rnn': torch.nn.RNN, 'lstm': torch.nn.LSTM, 'gru': torch.nn.GRU}[cell]
        self.rnn = Cell(3, units_rnn, batch_first=True)
        self.dense = torch.nn.Linear(units_rnn, units_dense)
        self.act = torch.nn.ReLU()
        self.dropout = torch.nn.Dropout(0.05)
        self.out = torch.nn.Linear(units_dense, 1)

    def forward(self, x):
        h, _ = self.rnn(x)
        z = self.act(self.dense(h[:, -1]))
        return self.out(self.dropout(z)).squeeze(-1)


def evaluar(model, X_te, y_te, ys):
    with torch.no_grad():
        pred = model(X_te).numpy() * ys
    pred = np.maximum(pred, 0.0)
    real = y_te.numpy() * ys
    rmse = np.sqrt(metrics.mean_squared_error(real, pred))
    mae = metrics.mean_absolute_error(real, pred)
    r2 = metrics.r2_score(real, pred)
    p_real, p_pred = prima(real).mean(), prima(pred).mean()
    err_prima = 100 * (p_pred - p_real) / p_real
    return dict(rmse=rmse, mae=mae, r2=r2, err_prima=err_prima)


# Programa principal
# --------------------------------------------------

if __name__ == '__main__':

    # Conexión con MLflow
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment(f"Reto 9 - Grupo {GRUPO}")

    # Datos
    torch.manual_seed(SEED)
    data = cargar_datos()
    idx = torch.randperm(len(data))[:N_SIMS].numpy()
    data = data[idx]
    X_ratio = data[:, 1:, :] / data[:, :1, :]
    y = payoff(X_ratio)
    X = np.diff(np.log(X_ratio), axis=1, prepend=0.0)
    print(f'Simulaciones: {len(X)} | % payoffs = 0: {100 * np.mean(y == 0):.1f}%')

    n_tr, n_val = int(.70 * len(X)), int(.15 * len(X))
    sl_tr = slice(0, n_tr)
    sl_val = slice(n_tr, n_tr + n_val)
    sl_te = slice(n_tr + n_val, None)

    m, s = X[sl_tr].mean((0, 1)), X[sl_tr].std((0, 1))
    ys = y[sl_tr].std()
    to_t = lambda a: torch.tensor(a, dtype=torch.float32)
    X_s, y_s = to_t((X - m) / s), to_t(y / ys)

    dataloader_train = DataLoader(
        TensorDataset(X_s[sl_tr], y_s[sl_tr]), batch_size=BATCH_SIZE, shuffle=True)
    dataloader_val = DataLoader(
        TensorDataset(X_s[sl_val], y_s[sl_val]), batch_size=BATCH_SIZE)
    X_te, y_te = X_s[sl_te], y_s[sl_te]

    resultados = []

    # Un run de MLflow por cada arquitectura
    for u_rnn, u_dense in ARQUITECTURAS:

        with mlflow.start_run(run_name=f"{CELL}_{u_rnn}_{u_dense}"):

            torch.manual_seed(SEED)
            model = Red(CELL, u_rnn, u_dense)
            criterion = torch.nn.MSELoss()
            optimizer = torch.optim.Adam(model.parameters(), lr=LR)
            scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
                optimizer, factor=0.5, patience=3)
            n_par = sum(p.numel() for p in model.parameters())

            # Parámetros: arquitectura e hiperparámetros
            mlflow.log_params({
                "neuronas_capa_recurrente": u_rnn,
                "neuronas_capa_densa": u_dense,
                "tipo_celda": CELL,
                "n_parametros": n_par,
                "learning_rate": LR,
                "batch_size": BATCH_SIZE,
                "epochs_max": EPOCHS,
                "patience": PATIENCE,
                "n_simulaciones": N_SIMS
            })
            mlflow.set_tag("grupo", GRUPO)
            mlflow.set_tag("algoritmo", "GRU (PyTorch)")

            # Entrenamiento (bucle equivalente al model.fit de Keras)
            inicio = time.perf_counter()
            min_val_loss = float('inf')
            mejor_estado = copy.deepcopy(model.state_dict())
            count = 0

            for epoch in range(EPOCHS):
                model.train()
                training_loss = 0.
                for inputs, targets in dataloader_train:
                    optimizer.zero_grad()
                    loss = criterion(model(inputs), targets)
                    loss.backward()
                    optimizer.step()
                    training_loss += loss.item() * inputs.size(0)
                training_loss /= len(dataloader_train.dataset)

                model.eval()
                val_loss = 0.
                with torch.no_grad():
                    for inputs, targets in dataloader_val:
                        val_loss += criterion(model(inputs), targets).item() * inputs.size(0)
                val_loss /= len(dataloader_val.dataset)
                scheduler.step(val_loss)

                # Pérdida por época en MLflow
                mlflow.log_metrics(
                    {"train_loss": training_loss, "val_loss": val_loss},
                    step=epoch + 1)

                if val_loss <= min_val_loss:
                    min_val_loss = val_loss
                    mejor_estado = copy.deepcopy(model.state_dict())
                    count = 0
                else:
                    count += 1
                    if count >= PATIENCE:
                        break

            tiempo_entrenamiento = time.perf_counter() - inicio
            model.load_state_dict(mejor_estado)
            model.eval()

            # Evaluación en test
            r = evaluar(model, X_te, y_te, ys)

            mlflow.log_metrics({
                "rmse_test": r["rmse"],
                "mae_test": r["mae"],
                "r2_test": r["r2"],
                "error_prima_pct": r["err_prima"],
                "mejor_val_loss": min_val_loss,
                "epocas_entrenadas": epoch + 1,
                "tiempo_entrenamiento_segundos": tiempo_entrenamiento
            })

            # Guardar el modelo en MLflow
            mlflow.pytorch.log_model(model, name="modelo")

            resultados.append((u_rnn, u_dense, n_par, r, tiempo_entrenamiento))
            print(f"\nArquitectura {u_rnn}-{u_dense} | params: {n_par}")
            print(f"RMSE: {r['rmse']:.4f} | MAE: {r['mae']:.4f} | "
                  f"R2: {r['r2']:.4f} | Err prima: {r['err_prima']:.2f}% | "
                  f"Tiempo: {tiempo_entrenamiento:.1f}s")

    # Resumen final
    print(f"\n{'Arq.':<8} {'Params':>7} {'RMSE':>8} {'MAE':>8} {'R2':>7} {'Err prima':>10}")
    for u1, u2, n_par, r, t in resultados:
        print(f"{u1}-{u2:<6} {n_par:>7} {r['rmse']:>8.4f} {r['mae']:>8.4f} "
              f"{r['r2']:>7.3f} {r['err_prima']:>9.2f}%")
