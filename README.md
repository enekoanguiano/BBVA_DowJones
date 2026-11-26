# 26-27_3_R9_EQUIPO_MORADO

*Versión en español: [más abajo](#versión-en-español)*

Financial analysis project covering portfolio construction and the valuation of a geometric Asian option on Dow Jones stocks. The work is developed in Python notebooks and completed with a Flask web application to simulate portfolios, explore an efficient frontier and compare valuation methods.

## Project overview

The analysis starts from historical market files, which are cleaned and transformed into a daily series. From that data, return and risk are studied, combinations of assets are compared and Monte Carlo simulations are run. The derivatives part simulates the option with Monte Carlo and trains neural networks to approximate the *payoff* of a geometric Asian option. Time series of the selected assets are also analysed.

| File | Content |
| --- | --- |
| [`01_LIMPIEZA.ipynb`](CODIGO/01_LIMPIEZA.ipynb) | Import of market CSV files, filtering of trading sessions and preparation of the daily dataset. |
| [`02_CARTERA.ipynb`](CODIGO/02_CARTERA.ipynb) | Comparison of asset combinations, correlations, Sharpe ratio and efficient frontier. |
| [`03_FINANZAS.ipynb`](CODIGO/03_FINANZAS.ipynb) | Returns, volatility, Sharpe, Sortino, drawdown, correlations, and quantitative and qualitative analysis. |
| [`04_MONTE_CARLO.ipynb`](CODIGO/04_MONTE_CARLO.ipynb) | Generation of simulated paths, geometric Brownian motion and payoff calculation. |
| [`05_VALORACION_OPCION.ipynb`](CODIGO/05_VALORACION_OPCION.ipynb) | Valuation of a geometric Asian option by Monte Carlo; generation of synthetic data. |
| [`06_RED_NEURONAL.ipynb`](CODIGO/06_RED_NEURONAL.ipynb) | Comparison of MLP, RNN, GRU and LSTM; metrics, cross-validation and saving of PyTorch models. |
| [`07_SERIES_TEMPORALES.ipynb`](CODIGO/07_SERIES_TEMPORALES.ipynb) | Processing and analysis of the time series of CAT, GS and MSFT. |
| [`08_APP_FLASK/`](CODIGO/08_APP_FLASK/) | Web application with portfolio simulation, option valuation and user management. |

## Folder structure

```text
REPOSITORY/
├── CODIGO/
│   ├── 01_LIMPIEZA.ipynb
│   ├── 02_CARTERA.ipynb
│   ├── 03_FINANZAS.ipynb
│   ├── 04_MONTE_CARLO.ipynb
│   ├── 05_VALORACION_OPCION.ipynb
│   ├── 06_RED_NEURONAL.ipynb
│   ├── 07_SERIES_TEMPORALES.ipynb
│   └── 08_APP_FLASK/
│       ├── app.py
│       ├── gestionar_admins.py
│       ├── motor/
│       ├── static/
│       └── templates/
├── DATOS/
│   ├── ORIGINALES/
│   ├── TRANSFORMADOS/
│   │   ├── df_diario.parquet
│   │   └── datos_sinteticos.npy
│   ├── MODELOS/
│   │   └── modelo_final.pt
│   └── GRAFICOS/
├── R9_MORADO_ENTORNO.yml
└── README.md
```

Folder and file names are in Spanish: `CODIGO` = code, `DATOS` = data, `ORIGINALES` = original files, `TRANSFORMADOS` = transformed data, `MODELOS` = models, `GRAFICOS` = charts, `LIMPIEZA` = cleaning, `CARTERA` = portfolio, `FINANZAS` = finance, `VALORACION_OPCION` = option valuation, `RED_NEURONAL` = neural network, `SERIES_TEMPORALES` = time series.

The `DATOS/` folder is created automatically when [`01_LIMPIEZA.ipynb`](CODIGO/01_LIMPIEZA.ipynb) is run. The first run will fail because the original data has not yet been placed in `DATOS/ORIGINALES/`: run it once, add the original data to that folder and run [`01_LIMPIEZA.ipynb`](CODIGO/01_LIMPIEZA.ipynb) again.

## Virtual environment setup

From **Anaconda Prompt**, at the root of the repository:

```bat
conda env create -f R9_MORADO_ENTORNO.yml
conda activate R9_M
```

### Main dependencies

The project uses NumPy, pandas, SciPy, Matplotlib, Seaborn, Plotly, scikit-learn, PyTorch, statsmodels, yfinance and Flask, among other libraries included in the environment file. Reading and writing Parquet requires an engine such as `pyarrow`; exporting Plotly charts to PNG uses Kaleido.

## Preparing and running the notebooks

1. Place the original CSV files in `DATOS/ORIGINALES/`. The cleaning notebook looks for files whose name ends in `_marketstack.csv`.
2. Run `01_LIMPIEZA.ipynb` to generate `DATOS/TRANSFORMADOS/df_diario.parquet`.
3. Run the portfolio and finance analyses (`02_CARTERA.ipynb` and `03_FINANZAS.ipynb`).
4. Run `04_MONTE_CARLO.ipynb` to study the simulated paths. Its synthetic output is saved as `datos_sinteticos2.npy`.
5. Run `05_VALORACION_OPCION.ipynb` to simulate the valuation and generate `DATOS/TRANSFORMADOS/datos_sinteticos.npy`.
6. Run `06_RED_NEURONAL.ipynb` to train and evaluate the architectures. It generates tables and charts and saves `DATOS/MODELOS/modelo_final.pt`, along with other checkpoints.
7. Run `07_SERIES_TEMPORALES.ipynb` for the time-series analysis of CAT, GS and MSFT.

Some notebooks download external financial data while running. Results may vary depending on the query date, the available data and the simulation seeds.

## Flask web application

The application is in [`CODIGO/08_APP_FLASK`](CODIGO/08_APP_FLASK). It lets you define and compare portfolios, simulate scenarios with Monte Carlo, explore an efficient frontier and value an option on three assets. It includes user login, administrator and analyst roles, connection logging and an admin panel.

**Before starting it**, the following files must exist:

```text
DATOS/TRANSFORMADOS/df_diario.parquet
DATOS/MODELOS/modelo_final.pt
```

`app.py` builds the paths from the location of the script itself up to the `DATOS/` folder at the root of the repository. They can be overridden with the environment variables `DATA_PATH` and `MODELOS_DIR`.

From Anaconda Prompt:

```bat
conda activate R9_M
cd CODIGO\08_APP_FLASK
python app.py
```

Open in your browser:

**http://127.0.0.1:5000**

To stop the server, press `Ctrl + C` in the terminal.

### Initial access and security

On an **empty database**, the code creates a provisional administrator with username `admin` and password `admin` and forces a password change at first login. **These credentials are intended for local testing only**; do not deploy the server with them or leave the account unchanged.

User and session data are stored in `CODIGO/08_APP_FLASK/instance/seguridad.db`, and the session key in `instance/secret_key`.

## Generated results

- `DATOS/TRANSFORMADOS/`: daily series, synthetic data and analysis tables.
- `DATOS/GRAFICOS/`: figures exported by the notebooks, including portfolio, financial analysis, neural network and time-series charts.
- `DATOS/MODELOS/`: trained models in `.pt` format.

---

## Versión en español

Proyecto de análisis financiero, construcción de carteras y valoración de una opción asiática geométrica sobre acciones del Dow Jones. El trabajo se desarrolla en notebooks de Python y se completa con una aplicación web en Flask para simular carteras, consultar una frontera eficiente y comparar métodos de valoración.

## Contenido del proyecto

El análisis parte de archivos históricos de mercado, que se limpian y transforman en una serie diaria. A partir de esos datos se estudian la rentabilidad y el riesgo, se comparan combinaciones de activos y se realizan simulaciones mediante Monte Carlo. La parte de derivados simula la opción mediante Monte Carlo y entrena redes neuronales para aproximar el *payoff* de una opción asiática geométrica. También se estudian series temporales de los activos seleccionados.

| Archivo | Contenido |
| --- | --- |
| [`01_LIMPIEZA.ipynb`](CODIGO/01_LIMPIEZA.ipynb) | Importación de CSV de mercado, filtrado de sesiones y preparación del conjunto diario. |
| [`02_CARTERA.ipynb`](CODIGO/02_CARTERA.ipynb) | Comparación de combinaciones de activos, correlaciones, ratio de Sharpe y frontera eficiente. |
| [`03_FINANZAS.ipynb`](CODIGO/03_FINANZAS.ipynb) | Rentabilidades, volatilidad, Sharpe, Sortino, drawdown, correlaciones y análisis cuantitativo y cualitativo. |
| [`04_MONTE_CARLO.ipynb`](CODIGO/04_MONTE_CARLO.ipynb) | Generación de trayectorias simuladas, movimiento browniano geométrico y cálculo del payoff. |
| [`05_VALORACION_OPCION.ipynb`](CODIGO/05_VALORACION_OPCION.ipynb) | Valoración de una opción asiática geométrica mediante Monte Carlo; generación de datos sintéticos. |
| [`06_RED_NEURONAL.ipynb`](CODIGO/06_RED_NEURONAL.ipynb) | Comparación de MLP, RNN, GRU y LSTM; métricas, validación cruzada y guardado de modelos PyTorch. |
| [`07_SERIES_TEMPORALES.ipynb`](CODIGO/07_SERIES_TEMPORALES.ipynb) | Tratamiento y análisis de series temporales de CAT, GS y MSFT. |
| [`08_APP_FLASK/`](CODIGO/08_APP_FLASK/) | Aplicación web con simulación de carteras, valoración de opciones y gestión de usuarios. |

## Organización de carpetas

```text
REPOSITORIO/
├── CODIGO/
│   ├── 01_LIMPIEZA.ipynb
│   ├── 02_CARTERA.ipynb
│   ├── 03_FINANZAS.ipynb
│   ├── 04_MONTE_CARLO.ipynb
│   ├── 05_VALORACION_OPCION.ipynb
│   ├── 06_RED_NEURONAL.ipynb
│   ├── 07_SERIES_TEMPORALES.ipynb
│   └── 08_APP_FLASK/
│       ├── app.py
│       ├── gestionar_admins.py
│       ├── motor/
│       ├── static/
│       └── templates/
├── DATOS/
│   ├── ORIGINALES/
│   ├── TRANSFORMADOS/
│   │   ├── df_diario.parquet
│   │   └── datos_sinteticos.npy
│   ├── MODELOS/
│   │   └── modelo_final.pt
│   └── GRAFICOS/
├── R9_MORADO_ENTORNO.yml
└── README.md
```

La carpeta `DATOS/` se creará automáticamente al ejecutar el script [`01_LIMPIEZA.ipynb`](CODIGO/01_LIMPIEZA.ipynb). Dará error, porque los datos no están importado a la carpeta `DATOS/ORIGINALES/` por ello, es necesario ejecutar primero, añadir los datos originales a la carpeta correspondiente y volver a ejecutar el script de [`01_LIMPIEZA.ipynb`](CODIGO/01_LIMPIEZA.ipynb).

## Instalación del entorno virtual

Desde **Anaconda Prompt**, situado en la raíz del repositorio:

```bat
conda env create -f R9_MORADO_ENTORNO.yml
conda activate R9_M
```

### Dependencias principales

El proyecto utiliza NumPy, pandas, SciPy, Matplotlib, Seaborn, Plotly, scikit-learn, PyTorch, statsmodels, yfinance y Flask, entre otras librerías incluidas en el archivo de entorno. La lectura y escritura de Parquet requiere un motor como `pyarrow`; la exportación de gráficos Plotly a PNG utiliza Kaleido.

## Preparación y ejecución de los notebooks

1. Coloca los archivos CSV originales en `DATOS/ORIGINALES/`. El notebook de limpieza busca archivos con nombre terminado en `_marketstack.csv`.
2. Ejecuta `01_LIMPIEZA.ipynb` para generar `DATOS/TRANSFORMADOS/df_diario.parquet`.
3. Ejecuta los análisis de cartera y finanzas (`02_CARTERA.ipynb` y `03_FINANZAS.ipynb`).
4. Ejecuta `04_MONTE_CARLO.ipynb` para estudiar las trayectorias simuladas. Su salida sintética se guarda con el nombre `datos_sinteticos2.npy`.
5. Ejecuta `05_VALORACION_OPCION.ipynb` para simular la valoración y generar `DATOS/TRANSFORMADOS/datos_sinteticos.npy`.
6. Ejecuta `06_RED_NEURONAL.ipynb` para entrenar y evaluar las arquitecturas. Genera tablas y gráficos y guarda `DATOS/MODELOS/modelo_final.pt`, además de otros checkpoints.
7. Ejecuta `07_SERIES_TEMPORALES.ipynb` para el análisis temporal de CAT, GS y MSFT.

Algunos notebooks descargan información financiera externa durante la ejecución. Los resultados pueden variar según la fecha de consulta, los datos disponibles y las semillas de simulación.

## Aplicación web Flask

La aplicación está en [`CODIGO/08_APP_FLASK`](CODIGO/08_APP_FLASK). Permite definir y comparar carteras, simular escenarios por Monte Carlo, consultar una frontera eficiente y valorar una opción sobre tres activos. Dispone de acceso con usuarios, roles de administrador y analista, registro de conexiones y panel administrativo.

**Antes de iniciarla**, deben existir los siguientes archivos:

```text
DATOS/TRANSFORMADOS/df_diario.parquet
DATOS/MODELOS/modelo_final.pt
```

`app.py` construye las rutas desde la ubicación del propio script hasta la carpeta `DATOS/` de la raíz del repositorio. Se pueden sustituir mediante las variables de entorno `DATA_PATH` y `MODELOS_DIR`.

Desde Anaconda Prompt:

```bat
conda activate R9_M
cd CODIGO\08_APP_FLASK
python app.py
```

Abre en el navegador:

**http://127.0.0.1:5000**

Para detener el servidor, pulsa `Ctrl + C` en la terminal.

### Acceso inicial y seguridad

En una **base de datos vacía**, el código crea un administrador provisional con usuario `admin` y contraseña `admin` y obliga a cambiarla al iniciar sesión. **Estas credenciales están previstas exclusivamente para pruebas locales**; no se debe publicar el servidor con ellas ni dejar la cuenta sin cambiar.

Los datos de usuarios y sesiones se almacenan en `CODIGO/08_APP_FLASK/instance/seguridad.db`, y la clave de sesión en `instance/secret_key`.

## Resultados generados

- `DATOS/TRANSFORMADOS/`: serie diaria, datos sintéticos y tablas de análisis.
- `DATOS/GRAFICOS/`: figuras exportadas por los notebooks, incluidas las de cartera, análisis financiero, redes neuronales y series temporales.
- `DATOS/MODELOS/`: modelos entrenados en formato `.pt`.

