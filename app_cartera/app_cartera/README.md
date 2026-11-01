# Simulador de carteras · Reto 9

Aplicación Flask que, introduciendo **tickers y pesos**, proyecta el comportamiento futuro
de una o varias carteras (hasta 4 a la vez) y usa las redes **RNN / GRU / LSTM** de
`red_NN.ipynb` para valorar la call asiática sobre 3 activos.

## Puesta en marcha

```bash
pip install -r requirements.txt
python gestionar_admins.py crear admin     # te pide la contraseña (mín. 8 caracteres)
python app.py                              # abre http://127.0.0.1:5000
```

## Acceso solo para administradores

Toda la aplicación (páginas y API) exige iniciar sesión. Las cuentas se gestionan desde la terminal:

```bash
python gestionar_admins.py crear <usuario>    # crea uno o cambia su contraseña
python gestionar_admins.py borrar <usuario>
python gestionar_admins.py listar
```

- Las contraseñas se guardan cifradas (hash scrypt) en `admins.json`, nunca en texto plano.
- Tras 5 intentos fallidos se bloquea ese usuario desde esa IP durante 5 minutos.
- Hay que iniciar sesión cada vez que se arranca la app, al cerrar el navegador y tras 30 minutos sin uso. Cookie `HttpOnly` y `SameSite=Lax`; formularios y API llevan token CSRF.
- La clave de firma de sesiones se genera sola en `instance/secret_key` (o usa la variable `SECRET_KEY`).
- Si publicas la app con HTTPS, arráncala con `COOKIE_SEGURA=1`.
- No compartas `admins.json` ni `instance/`.

Estructura:

```
app.py                      rutas Flask, validación y login
gestionar_admins.py         alta/baja de administradores
motor/auth.py               contraseñas, bloqueo por intentos, CSRF
motor/datos.py              lectura de df_diario.parquet (precios de cierre)
motor/simulacion.py         calibración, Monte Carlo, métricas de riesgo, frontera eficiente
motor/redes.py              carga de los .pt e inferencia RNN/GRU/LSTM en NumPy
motor/opcion.py             call asiática: Monte Carlo frente a las tres redes
templates/, static/         interfaz (Plotly y la fuente Schibsted Grotesk por CDN)
datos/df_diario.parquet     26 valores del Dow Jones, 2018-06 → 2025-06
modelos/best_model_*.pt     pesos entrenados en el notebook
exportar_normalizacion.py   genera modelos/normalizacion.json (ver abajo)
```

Rutas alternativas: `DATA_PATH=/ruta/df.parquet MODELOS_DIR=/ruta/modelos python app.py`.

## Qué hace

**Proyección.** Para cada cartera se estiman drift, volatilidades y correlaciones con los
log-retornos diarios de los últimos *N* años y se simulan trayectorias GBM correlacionadas
(Cholesky), el mismo modelo con el que se generan los datos sintéticos del notebook. Devuelve:
valor mediano y esperado, banda p5–p95, rentabilidad anual, volatilidad, Sharpe, probabilidad
de pérdida, VaR/CVaR 95 % y caída máxima. Se puede elegir comprar y mantener o rebalanceo.

La rentabilidad esperada puede ser:
- **Histórica**: la media de 2020–2025, que fue un periodo muy alcista, así que tiende a ser optimista.
- **Prudente**: la media entre la histórica y el 1 %.
- **Neutral al riesgo**: el 1 % para todos los activos (`MU` del notebook).

**Activos y riesgo.** Precio mediano y rango por activo, probabilidad de subir, contribución de
cada activo al riesgo y matriz de correlaciones.

**Histórico.** Evolución real de la cartera (base 100) en el periodo de calibración.

**Combinaciones óptimas.** Miles de combinaciones aleatorias de pesos, con las carteras de
máximo Sharpe y de mínima volatilidad. Un botón aplica esos pesos a la cartera.

**Red neuronal.** Con 3 tickers se simulan 20 000 trayectorias trimestrales a 5 años
(r = 1 %) con la volatilidad y la correlación reales de esos activos. Se calcula la prima exacta
por Monte Carlo y la que predicen RNN, GRU y LSTM, con error de prima, RMSE, MAE, R² y el
gráfico de payoff real frente al predicho.

## Importante: normalización de las redes

El notebook estandariza las entradas con `m`, `s` y el payoff con `ys`, calculados sobre
el conjunto de entrenamiento, pero **no los guarda**. Sin esos valores, la app estandariza con
las propias simulaciones y ajusta `ys` por mínimos cuadrados (avisándolo en pantalla). Así la
red pierde la información del nivel de volatilidad y la precisión baja: con AAPL/MSFT/KO
se obtiene un R² de entre 0,72 y 0,85, frente al 0,999 del notebook.

Para usar la normalización exacta, ejecuta una vez en tu equipo (necesita PyTorch y el
`datos_sinteticos.npy`):

```bash
python exportar_normalizacion.py ../DATOS/TRANSFORMADOS/datos_sinteticos.npy
```

El script reproduce la semilla, la permutación y el 70 % de entrenamiento del notebook y
escribe `modelos/normalizacion.json`. La app lo carga automáticamente al arrancar.

## Notas

- La inferencia de las redes está implementada en NumPy con las mismas ecuaciones que
  `torch.nn.RNN/GRU/LSTM`, así que el servidor no necesita PyTorch. Si está instalado, se usa
  `torch.load` para leer los pesos.
- Pesos negativos (posiciones cortas) no están permitidos; los pesos se normalizan a 100 %.
- Son proyecciones estadísticas basadas en el pasado, no una predicción segura.
