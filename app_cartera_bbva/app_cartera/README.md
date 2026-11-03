# Simulador de carteras · Reto 9

Aplicación Flask que, introduciendo **tickers y pesos**, proyecta el comportamiento futuro
de una o varias carteras (hasta 4 a la vez) y usa las redes **RNN / GRU / LSTM** de
`red_NN.ipynb` para valorar la call asiática sobre 3 activos.

## Puesta en marcha

```bash
pip install -r requirements.txt
python gestionar_admins.py crear admin     # te pide la contraseña (mín. 10 caracteres, letras y números)
python app.py                              # abre http://127.0.0.1:5000
```

Si ya tenías un `admins.json` de la versión anterior, sus cuentas se importan solas como
administradores al arrancar (el fichero queda renombrado a `admins.json.importado`) y
sus contraseñas siguen valiendo.

## Usuarios, seguridad y registro de conexiones

Toda la aplicación (páginas y API) exige iniciar sesión. Hay dos roles:

- **Administrador**: usa el simulador y entra en el panel de administración (`/admin`).
- **Analista**: solo usa el simulador.

### Panel de administración (`/admin`)

| Sección | Qué muestra |
|---|---|
| Resumen | Conectados ahora, accesos y fallos de las últimas 24 h, cuentas bloqueadas, gráfico de 14 días y aviso de IPs con 5 o más fallos (posible fuerza bruta). |
| Conexiones | Cada intento de acceso, correcto o fallido, y cada cierre de sesión: fecha, usuario, IP, motivo y navegador. Filtros por usuario, IP, resultado y fechas. Exportación a CSV (se abre en Excel). |
| Sesiones activas | Quién está dentro ahora, desde qué IP y navegador, y cuándo hizo algo por última vez. Botón para expulsar. |
| Usuarios | Alta con contraseña provisional, cambio de rol, activar/desactivar, desbloquear, restablecer contraseña, cerrar sesiones, borrar. Ficha con sus sesiones, conexiones y actividad. |
| Auditoría | Qué ha hecho cada usuario: simulaciones (con tickers, pesos y parámetros), frontera, valoración de la opción, cambios de usuarios, exportaciones y accesos denegados. Exportación a CSV. |

### Medidas de seguridad

- Contraseñas cifradas (hash scrypt), nunca en texto plano. Mínimo 10 caracteres con letras y números.
- Las cuentas creadas desde el panel reciben una contraseña provisional que hay que cambiar al entrar.
- 5 fallos con el mismo usuario desde la misma IP bloquean esa combinación 5 minutos; 10 fallos en una
  cuenta desde cualquier IP la bloquean 15 minutos; 30 fallos desde una IP en 15 minutos bloquean esa IP.
- El mensaje de error del login es siempre el mismo: no revela si el usuario existe, está desactivado o bloqueado.
- Las sesiones se guardan también en el servidor: se pueden cerrar a distancia, caducan tras 30 minutos
  sin uso, al cerrar el navegador y al reiniciar la app. Cambiar la contraseña, el rol o desactivar a
  alguien cierra sus sesiones.
- Cookie `HttpOnly` y `SameSite=Lax`; formularios y API llevan token CSRF.
- Siempre queda al menos un administrador activo, y nadie puede quitarse su propio rol ni desactivarse.

### Desde la terminal

```bash
python gestionar_admins.py crear <usuario> [--rol admin|analista]   # por defecto admin
python gestionar_admins.py clave <usuario>          # cambia la contraseña
python gestionar_admins.py rol <usuario> analista
python gestionar_admins.py desbloquear <usuario>
python gestionar_admins.py borrar <usuario>
python gestionar_admins.py listar
python gestionar_admins.py purgar 365               # borra registros de más de 365 días
```

### Datos y privacidad

- Todo se guarda en `instance/seguridad.db` (SQLite, sin dependencias nuevas). Junto con
  `instance/secret_key`, no se debe compartir ni subir a git.
- Las IPs y el historial de accesos son datos personales (RGPD): conviene fijar un plazo de
  conservación, ejecutar `purgar` periódicamente e informar a los usuarios.
- Las fechas se guardan en UTC y se muestran en la hora del servidor.

### Al publicarla

- Con HTTPS, arráncala con `COOKIE_SEGURA=1`.
- Si va detrás de un proxy (Nginx, etc.), arráncala con `DETRAS_DE_PROXY=1`; si no, todas las
  conexiones aparecerán con la IP del proxy. No lo actives sin proxy: cualquiera podría falsear su IP.
- Los contadores de intentos fallidos por IP viven en memoria: con varios procesos de Gunicorn,
  cada uno lleva su cuenta (el bloqueo por cuenta sí es global porque está en la base de datos).

Estructura:

```
app.py                      rutas Flask, validación, login y cambio de contraseña
panel.py                    panel de administración (/admin)
gestionar_admins.py         gestión de usuarios desde la terminal
motor/auth.py               usuarios, roles, sesiones, conexiones, auditoría, bloqueos, CSRF
motor/datos.py              lectura de df_diario.parquet (precios de cierre)
motor/simulacion.py         calibración, Monte Carlo, métricas de riesgo, frontera eficiente
motor/redes.py              carga de los .pt e inferencia RNN/GRU/LSTM en NumPy
motor/opcion.py             call asiática: Monte Carlo frente a las tres redes
templates/, static/         interfaz (templates/panel/: pantallas de administración) (Plotly y la fuente Schibsted Grotesk por CDN)
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
