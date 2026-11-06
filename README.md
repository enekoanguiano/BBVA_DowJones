# 26-27_3_R9_EQUIPO_MORADO

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

