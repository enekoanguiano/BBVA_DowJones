/* Simulador de carteras – front-end */
const $ = (s) => document.querySelector(s);
const css = (v) => getComputedStyle($('.viz-root')).getPropertyValue(v).trim();
const COLORES = () => [css('--series-1'), css('--series-2'), css('--series-3'), css('--series-4')];
const MAX_CARTERAS = 4;

const fmtEur = (x) => x.toLocaleString('es-ES', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0, useGrouping: 'always' });
const fmtPerdida = (x) => (x > 0 ? fmtEur(x) : 'Sin pérdida');
const fmtPct = (x, d = 1) => (x == null ? '—' : (100 * x).toLocaleString('es-ES', { maximumFractionDigits: d, minimumFractionDigits: d }) + ' %');
const fmtNum = (x, d = 2) => (x == null ? '—' : x.toLocaleString('es-ES', { maximumFractionDigits: d, minimumFractionDigits: d }));
const signo = (x) => (x >= 0 ? 'pos' : 'neg');

let carteras = [];
let ultimo = null;   // última respuesta de /api/simular
let TICKERS = [];

/* ------------------------------------------------------------------ */
/*  Plotly: estilo común                                              */
/* ------------------------------------------------------------------ */
function layoutBase(extra = {}) {
  return Object.assign({
    paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
    font: { family: 'Schibsted Grotesk, system-ui, -apple-system, Segoe UI, sans-serif', size: 12, color: css('--text-secondary') },
    margin: { l: 64, r: 16, t: 10, b: 44 },
    xaxis: { gridcolor: css('--grid'), linecolor: css('--axis'), zeroline: false },
    yaxis: { gridcolor: css('--grid'), linecolor: css('--axis'), zeroline: false },
    legend: { orientation: 'h', y: -0.18, font: { color: css('--text-primary') } },
    hoverlabel: { bgcolor: css('--surface-1'), bordercolor: css('--axis'), font: { color: css('--text-primary') } },
    hovermode: 'x unified',
  }, extra);
}
const CFG = { displaylogo: false, responsive: true, modeBarButtonsToRemove: ['lasso2d', 'select2d'] };
const alpha = (hex, a) => {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
};

const CSRF = document.querySelector('meta[name="csrf-token"]').content;
async function api(url, body) {
  const r = await fetch(url, body
    ? { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': CSRF }, body: JSON.stringify(body) }
    : {});
  if (r.status === 401) { window.location.href = '/login'; throw new Error('Sesión caducada'); }
  const j = await r.json().catch(() => ({ error: 'Respuesta no válida del servidor' }));
  if (!r.ok) throw new Error(j.error || 'Error en el servidor');
  return j;
}

/* ------------------------------------------------------------------ */
/*  Editor de carteras                                                 */
/* ------------------------------------------------------------------ */
function nuevaCartera(nombre, filas) {
  return { nombre: nombre || `Cartera ${carteras.length + 1}`, filas: filas || [{ ticker: '', peso: '' }] };
}

function textoSuma(c) {
  const s = c.filas.reduce((a, f) => a + (parseFloat(f.peso) || 0), 0);
  return s > 0 ? `Suman ${fmtNum(s, 1)}: se ajustan a 100 %` : 'Sin pesos: partes iguales';
}

function pesosNormalizados(c) {
  const vals = c.filas.map((f) => Math.max(0, parseFloat(f.peso) || 0));
  const s = vals.reduce((a, x) => a + x, 0);
  return s > 0 ? vals.map((x) => x / s) : vals.map(() => 1 / c.filas.length);
}

function actualizarBarras(div, c) {
  const w = pesosNormalizados(c);
  div.querySelectorAll('.barra-peso i').forEach((b, k) => { b.style.width = `${100 * w[k]}%`; });
  div.querySelectorAll('.barra-peso').forEach((b, k) => { b.title = `${fmtPct(w[k])} de la cartera`; });
  div.querySelector('.suma').textContent = textoSuma(c);
}

function renderCarteras() {
  const cont = $('#carteras');
  cont.innerHTML = '';
  const cols = COLORES();
  carteras.forEach((c, ci) => {
    const div = document.createElement('div');
    div.className = 'cartera';
    div.style.setProperty('--c', cols[ci]);
    div.innerHTML = `
      <div class="cartera-cab">
        <input value="${c.nombre}" data-k="nombre" aria-label="Nombre de la cartera">
        ${carteras.length > 1 ? '<button class="x" data-acc="borrar" title="Eliminar cartera" aria-label="Eliminar cartera">✕</button>' : ''}
      </div>
      ${c.filas.map((f, fi) => `
        <div class="fila-activo">
          <input list="lista-tickers" value="${f.ticker}" data-f="${fi}" data-k="ticker" placeholder="Ticker" aria-label="Ticker">
          <input type="number" min="0" step="any" value="${f.peso}" data-f="${fi}" data-k="peso" placeholder="Peso" aria-label="Peso">
          <button class="x" data-acc="quitar" data-f="${fi}" title="Quitar activo" aria-label="Quitar activo">✕</button>
          <div class="barra-peso"><i></i></div>
        </div>`).join('')}
      <div class="cartera-pie">
        <button class="rail-link" data-acc="anadir">Añadir activo</button>
        <span class="suma"></span>
      </div>`;
    div.addEventListener('input', (e) => {
      const k = e.target.dataset.k; if (!k) return;
      if (k === 'nombre') { c.nombre = e.target.value; actualizarSelects(); return; }
      c.filas[+e.target.dataset.f][k] = k === 'ticker' ? e.target.value.toUpperCase() : e.target.value;
      actualizarBarras(div, c);
    });
    div.addEventListener('click', (e) => {
      const acc = e.target.dataset.acc; if (!acc) return;
      if (acc === 'anadir') c.filas.push({ ticker: '', peso: '' });
      if (acc === 'quitar') { c.filas.splice(+e.target.dataset.f, 1); if (!c.filas.length) c.filas.push({ ticker: '', peso: '' }); }
      if (acc === 'borrar') carteras.splice(ci, 1);
      renderCarteras();
      if (acc === 'anadir') cont.children[ci].querySelectorAll('input[data-k=ticker]')[c.filas.length - 1].focus();
    });
    cont.appendChild(div);
    actualizarBarras(div, c);
  });
  $('#btn-add-cartera').disabled = carteras.length >= MAX_CARTERAS;
  $('#btn-add-cartera').textContent = carteras.length >= MAX_CARTERAS ? 'Máximo 4 carteras' : 'Añadir cartera';
  actualizarSelects();
}

function carterasPayload() {
  return carteras.map((c) => {
    const filas = c.filas.filter((f) => f.ticker.trim());
    const algunPeso = filas.some((f) => f.peso !== '' && !isNaN(parseFloat(f.peso)));
    return {
      nombre: c.nombre,
      tickers: filas.map((f) => f.ticker.trim().toUpperCase()),
      pesos: algunPeso ? filas.map((f) => parseFloat(f.peso) || 0) : [],
    };
  }).filter((c) => c.tickers.length);
}

/* ------------------------------------------------------------------ */
/*  Simulación                                                         */
/* ------------------------------------------------------------------ */
async function simular() {
  $('#error').textContent = '';
  const cs = carterasPayload();
  if (!cs.length) { $('#error').textContent = 'Añade al menos un ticker.'; return; }
  const btn = $('#btn-simular'); btn.disabled = true; btn.textContent = 'Simulando…';
  try {
    ultimo = await api('/api/simular', {
      carteras: cs,
      capital: +$('#capital').value, horizonte: +$('#horizonte').value,
      n_sims: +$('#n_sims').value, anios_hist: +$('#anios_hist').value,
      drift: $('#drift').value, rebalanceo: $('#rebalanceo').checked,
    });
    $('#vacio').hidden = true; $('#resultado').hidden = false;
    document.querySelector('.tab[data-tab=proyeccion]').click();
    renderProyeccion(); actualizarSelects(); renderActivos(); renderHistorico();
    Plotly.purge('g-frontera'); $('#sugerencias').innerHTML = '';
  } catch (e) {
    $('#error').textContent = e.message;
  } finally {
    btn.disabled = false; btn.textContent = 'Simular carteras';
  }
}

function renderProyeccion() {
  const cols = COLORES();
  const H = ultimo.horizonte;
  // Resumen: una columna por cartera, con el rango p5–p95 en una escala común
  const lo = Math.min(...ultimo.carteras.map((c) => c.resumen.p5));
  const hi = Math.max(...ultimo.carteras.map((c) => c.resumen.p95));
  const pos = (x) => `${(100 * (x - lo)) / (hi - lo || 1)}%`;
  $('#kpis').innerHTML = ultimo.carteras.map((c, i) => {
    const r = c.resumen;
    const gan = r.valor_mediano - r.capital;
    return `<div class="kpi" style="--c:${cols[i]}">
      <div class="titulo"><span class="punto"></span>${c.nombre}</div>
      <div class="etiqueta">Valor probable en ${fmtNum(H, H % 1 ? 2 : 0)} años</div>
      <div class="grande">${fmtEur(r.valor_mediano)}</div>
      <div class="delta ${signo(gan)}">${gan >= 0 ? '+' : '−'}${fmtEur(Math.abs(gan))} (${fmtPct(r.cagr_mediano)} al año)</div>
      <div class="rango" title="Del 5 % al 95 % de los escenarios">
        <i style="left:${pos(r.p5)};right:calc(100% - ${pos(r.p95)})"></i><b style="left:${pos(r.valor_mediano)}"></b>
      </div>
      <div class="rango-ejes"><span>${fmtEur(r.p5)}</span><span>${fmtEur(r.p95)}</span></div>
      <div class="linea"><span>Volatilidad anual</span><b>${fmtPct(r.vol_anual)}</b></div>
      <div class="linea"><span>Prob. de perder dinero</span><b>${fmtPct(r.prob_perdida)}</b></div>
      <div class="linea"><span>Pérdida en el peor 5 %</span><b>${fmtPerdida(r.cvar95)}</b></div>
    </div>`;
  }).join('');

  // Abanico
  const trazas = [];
  ultimo.carteras.forEach((c, i) => {
    const col = cols[i];
    trazas.push({ x: c.t, y: c.percentiles.p95, mode: 'lines', line: { width: 0 }, hoverinfo: 'skip', showlegend: false, legendgroup: c.nombre });
    trazas.push({ x: c.t, y: c.percentiles.p5, mode: 'lines', line: { width: 0 }, fill: 'tonexty', fillcolor: alpha(col, 0.13),
      hoverinfo: 'skip', showlegend: false, legendgroup: c.nombre });
    trazas.push({ x: c.t, y: c.percentiles.p5, mode: 'lines', line: { color: col, width: 1, dash: 'dot' }, name: `${c.nombre} · p5`,
      legendgroup: c.nombre, showlegend: false, hovertemplate: '%{y:,.0f} €' });
    trazas.push({ x: c.t, y: c.percentiles.p95, mode: 'lines', line: { color: col, width: 1, dash: 'dot' }, name: `${c.nombre} · p95`,
      legendgroup: c.nombre, showlegend: false, hovertemplate: '%{y:,.0f} €' });
    trazas.push({ x: c.t, y: c.percentiles.p50, mode: 'lines', line: { color: col, width: 2.5 }, name: c.nombre,
      legendgroup: c.nombre, hovertemplate: '%{y:,.0f} €' });
  });
  const cap = ultimo.carteras[0].resumen.capital;
  Plotly.react('g-fan', trazas, layoutBase({
    xaxis: { title: 'Años', gridcolor: css('--grid'), linecolor: css('--axis'), zeroline: false },
    yaxis: { title: 'Valor (€)', gridcolor: css('--grid'), linecolor: css('--axis'), zeroline: false, tickformat: ',.0f' },
    shapes: [{ type: 'line', xref: 'paper', x0: 0, x1: 1, y0: cap, y1: cap, line: { color: css('--muted'), width: 1, dash: 'dash' } }],
    annotations: [{ xref: 'paper', x: 0, y: cap, text: 'Capital inicial', showarrow: false, xanchor: 'left', yanchor: 'bottom', font: { color: css('--muted'), size: 11 } }],
  }), CFG);

  // Histograma del valor final
  const ht = ultimo.carteras.map((c, i) => {
    const b = c.hist.bordes; const tot = c.hist.cuentas.reduce((a, x) => a + x, 0);
    return {
      type: 'bar', name: c.nombre, marker: { color: alpha(cols[i], 0.55), line: { color: cols[i], width: 1 } },
      x: c.hist.cuentas.map((_, k) => (b[k] + b[k + 1]) / 2), width: c.hist.cuentas.map((_, k) => b[k + 1] - b[k]),
      y: c.hist.cuentas.map((x) => x / tot),
      hovertemplate: `${c.nombre}<br>%{x:,.0f} €: %{y:.1%}<extra></extra>`,
    };
  });
  Plotly.react('g-hist', ht, layoutBase({
    barmode: 'overlay', hovermode: 'closest',
    xaxis: { title: 'Valor final (€)', gridcolor: css('--grid'), linecolor: css('--axis'), tickformat: ',.0f' },
    yaxis: { title: 'Frecuencia', gridcolor: css('--grid'), linecolor: css('--axis'), tickformat: '.0%' },
    shapes: [{ type: 'line', yref: 'paper', y0: 0, y1: 1, x0: cap, x1: cap, line: { color: css('--muted'), width: 1, dash: 'dash' } }],
  }), CFG);

  // Tabla comparativa
  const filas = [
    ['Composición', (c) => c.tickers.map((t, k) => `${t} ${fmtPct(c.pesos[k], 0)}`).join(', ')],
    ['Valor esperado (media)', (c) => fmtEur(c.resumen.valor_esperado)],
    ['Valor mediano', (c) => fmtEur(c.resumen.valor_mediano)],
    ['Rentabilidad anual esperada', (c) => fmtPct(c.resumen.rent_esperada_anual)],
    ['Rentabilidad anual mediana', (c) => fmtPct(c.resumen.cagr_mediano)],
    ['Volatilidad anual', (c) => fmtPct(c.resumen.vol_anual)],
    ['Ratio de Sharpe (rf 1 %)', (c) => fmtNum(c.resumen.sharpe)],
    ['Prob. de pérdida', (c) => fmtPct(c.resumen.prob_perdida)],
    ['VaR 95 % (pérdida)', (c) => fmtPerdida(c.resumen.var95)],
    ['CVaR 95 % (pérdida media en el peor 5 %)', (c) => fmtPerdida(c.resumen.cvar95)],
    ['Caída máxima mediana', (c) => fmtPct(c.resumen.drawdown_mediano)],
    ['Datos de calibración', (c) => `${c.periodo_calibracion[0]} → ${c.periodo_calibracion[1]}`],
  ];
  $('#tabla-comp').innerHTML = `<table><thead><tr><th></th>${ultimo.carteras.map((c, i) =>
    `<th><span class="punto" style="--c:${cols[i]}"></span>${c.nombre}</th>`).join('')}</tr></thead>
    <tbody>${filas.map(([n, f], k) => `<tr><td>${n}</td>${ultimo.carteras.map((c) => `<td${k === 0 ? ' class="wrap"' : ''}>${f(c)}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
}

/* ------------------------------------------------------------------ */
/*  Activos y riesgo                                                   */
/* ------------------------------------------------------------------ */
function actualizarSelects() {
  const nombres = ultimo ? ultimo.carteras.map((c) => c.nombre) : [];
  ['#sel-cartera-activos', '#sel-cartera-hist'].forEach((s) => {
    const prev = $(s).value;
    $(s).innerHTML = nombres.map((n, i) => `<option value="${i}">${n}</option>`).join('');
    if (prev && +prev < nombres.length) $(s).value = prev;
  });
  const prevF = $('#sel-cartera-front').value;
  $('#sel-cartera-front').innerHTML = carteras.map((c, i) => `<option value="${i}">${c.nombre}</option>`).join('');
  if (prevF && +prevF < carteras.length) $('#sel-cartera-front').value = prevF;
}

function renderActivos() {
  if (!ultimo) return;
  const c = ultimo.carteras[+$('#sel-cartera-activos').value || 0];
  const H = ultimo.horizonte;
  $('#tabla-activos').innerHTML = `<table><thead><tr>
      <th>Ticker</th><th>Peso</th><th>Precio actual</th><th>Rentab. anual usada</th><th>Volatilidad</th>
      <th>Precio mediano a ${fmtNum(H, H % 1 ? 2 : 0)} años</th><th>Rango 5 %–95 %</th><th>Prob. de subir</th><th>Contrib. al riesgo</th></tr></thead>
    <tbody>${c.activos.map((a) => `<tr>
      <td><b>${a.ticker}</b></td><td>${fmtPct(a.peso)}</td><td>${fmtNum(a.precio)} $</td>
      <td class="${signo(a.mu)}">${fmtPct(a.mu)}</td><td>${fmtPct(a.sigma)}</td>
      <td>${fmtNum(a.precio_mediana)} $</td><td>${fmtNum(a.precio_p5, 0)} – ${fmtNum(a.precio_p95, 0)} $</td>
      <td>${fmtPct(a.prob_sube, 0)}</td><td>${fmtPct(a.contrib_riesgo)}</td></tr>`).join('')}</tbody></table>`;

  const cols = COLORES();
  Plotly.react('g-riesgo', [
    { type: 'bar', name: 'Peso', x: c.tickers, y: c.activos.map((a) => a.peso), marker: { color: cols[0] }, hovertemplate: '%{y:.1%}' },
    { type: 'bar', name: 'Contribución al riesgo', x: c.tickers, y: c.activos.map((a) => a.contrib_riesgo), marker: { color: cols[1] }, hovertemplate: '%{y:.1%}' },
  ], layoutBase({ barmode: 'group', bargap: 0.3, bargroupgap: 0.08, yaxis: { tickformat: '.0%', gridcolor: css('--grid') } }), CFG);

  const z = c.corr;
  Plotly.react('g-corr', [{
    type: 'heatmap', z, x: c.tickers, y: c.tickers, zmin: -1, zmax: 1,
    colorscale: [[0, '#d03b3b'], [0.5, css('--grid')], [1, '#2a78d6']],
    text: z.map((r) => r.map((v) => v.toFixed(2))), texttemplate: z.length <= 8 ? '%{text}' : '',
    hovertemplate: '%{y} · %{x}: %{z:.2f}<extra></extra>', xgap: 2, ygap: 2,
    colorbar: { thickness: 10, outlinewidth: 0 },
  }], layoutBase({ hovermode: 'closest', margin: { l: 60, r: 10, t: 10, b: 50 }, yaxis: { autorange: 'reversed' } }), CFG);
}

/* ------------------------------------------------------------------ */
/*  Histórico                                                          */
/* ------------------------------------------------------------------ */
function renderHistorico() {
  if (!ultimo) return;
  const i = +$('#sel-cartera-hist').value || 0;
  const c = ultimo.carteras[i];
  const h = c.historico;
  const trazas = Object.entries(h.activos).map(([tk, y]) => ({
    x: h.fechas, y, mode: 'lines', name: tk, line: { color: css('--muted'), width: 1 }, opacity: 0.55,
    hovertemplate: `${tk}: %{y:.1f}<extra></extra>`,
  }));
  trazas.push({ x: h.fechas, y: h.cartera, mode: 'lines', name: c.nombre, line: { color: COLORES()[i], width: 3 },
    hovertemplate: `${c.nombre}: %{y:.1f}<extra></extra>` });
  const fin = h.fechas.length - 1;
  Plotly.react('g-historico', trazas, layoutBase({
    yaxis: { title: 'Base 100', gridcolor: css('--grid'), linecolor: css('--axis') },
    annotations: Object.entries(h.activos).map(([tk, y]) => ({ x: h.fechas[fin], y: y[fin], text: tk, showarrow: false, xanchor: 'left', font: { size: 10, color: css('--muted') } }))
      .concat([{ x: h.fechas[fin], y: h.cartera[fin], text: `<b>${c.nombre}</b>`, showarrow: false, xanchor: 'left', font: { size: 11, color: css('--text-primary') } }]),
    margin: { l: 56, r: 90, t: 10, b: 40 },
  }), CFG);
}

/* ------------------------------------------------------------------ */
/*  Frontera eficiente                                                 */
/* ------------------------------------------------------------------ */
async function calcularFrontera() {
  $('#error').textContent = '';
  const ci = +$('#sel-cartera-front').value || 0;
  const cp = carterasPayload();
  const c = carteras[ci];
  const tks = c.filas.map((f) => f.ticker.trim().toUpperCase()).filter(Boolean);
  try {
    const f = await api('/api/frontera', { tickers: tks, anios_hist: +$('#anios_hist').value });
    const actual = cp.find((x) => x.nombre === c.nombre);
    let wAct = actual && actual.pesos.length ? actual.pesos : tks.map(() => 1);
    const s = wAct.reduce((a, x) => a + x, 0); wAct = wAct.map((x) => x / s);
    const muA = f.activos.reduce((a, x, k) => a + wAct[k] * x.mu, 0);
    const blues = [[0, '#cde2fb'], [0.5, '#5598e7'], [1, '#0d366b']];
    const trazas = [
      { type: 'scattergl', mode: 'markers', x: f.vol, y: f.mu, name: 'Combinaciones aleatorias',
        marker: { size: 4, color: f.sharpe, colorscale: blues, colorbar: { title: 'Sharpe', thickness: 10, outlinewidth: 0 } },
        hovertemplate: 'Vol %{x:.1%} · Rentab. %{y:.1%}<extra></extra>' },
      { mode: 'markers+text', x: f.activos.map((a) => a.vol), y: f.activos.map((a) => a.mu), text: f.activos.map((a) => a.ticker),
        textposition: 'top center', name: 'Activos individuales', marker: { size: 9, color: css('--muted'), line: { color: css('--surface-1'), width: 2 } },
        hovertemplate: '%{text}: vol %{x:.1%} · rentab. %{y:.1%}<extra></extra>' },
      { mode: 'markers', x: [f.max_sharpe.vol], y: [f.max_sharpe.mu], name: 'Máximo Sharpe',
        marker: { size: 14, symbol: 'star', color: COLORES()[1], line: { color: css('--surface-1'), width: 2 } } },
      { mode: 'markers', x: [f.min_var.vol], y: [f.min_var.mu], name: 'Mínima volatilidad',
        marker: { size: 13, symbol: 'diamond', color: COLORES()[2], line: { color: css('--surface-1'), width: 2 } } },
    ];
    // posición de la cartera actual (volatilidad calculada en cliente no disponible: se pide al servidor via simulación previa)
    const sim = ultimo && ultimo.carteras.find((x) => x.nombre === c.nombre && x.tickers.join() === tks.join());
    if (sim) trazas.push({ mode: 'markers', x: [sim.resumen.vol_anual], y: [muA], name: `${c.nombre} (actual)`,
      marker: { size: 13, symbol: 'circle', color: COLORES()[ci], line: { color: css('--text-primary'), width: 2 } } });
    Plotly.react('g-frontera', trazas, layoutBase({
      hovermode: 'closest',
      xaxis: { title: 'Volatilidad anual', tickformat: '.0%', gridcolor: css('--grid'), linecolor: css('--axis') },
      yaxis: { title: 'Rentabilidad anual histórica', tickformat: '.0%', gridcolor: css('--grid'), linecolor: css('--axis') },
    }), CFG);
    const tarjeta = (titulo, desc, o, clave) => `<div class="sug"><h4>${titulo}</h4>
      <div class="hint">${desc}. Rentabilidad ${fmtPct(o.mu)}, volatilidad ${fmtPct(o.vol)}, Sharpe ${fmtNum(o.sharpe)}.</div>
      <div class="pesos">${f.tickers.map((t, k) => `<span>${t} <b>${fmtPct(o.pesos[k], 0)}</b></span>`).join('')}</div>
      <button class="btn-sec" data-aplicar="${clave}">Aplicar a ${c.nombre} y simular</button></div>`;
    $('#sugerencias').innerHTML = tarjeta('★ Máximo Sharpe', 'Mejor rentabilidad por unidad de riesgo', f.max_sharpe, 'max_sharpe')
      + tarjeta('◆ Mínima volatilidad', 'El reparto que menos oscila', f.min_var, 'min_var');
    $('#sugerencias').onclick = (e) => {
      const k = e.target.dataset.aplicar; if (!k) return;
      c.filas = f.tickers.map((t, j) => ({ ticker: t, peso: +(100 * f[k].pesos[j]).toFixed(1) }));
      renderCarteras(); simular();
    };
  } catch (e) {
    $('#sugerencias').innerHTML = `<div class="sug neg">${e.message}</div>`;
  }
}

/* ------------------------------------------------------------------ */
/*  Red neuronal                                                       */
/* ------------------------------------------------------------------ */
async function valorarRed() {
  const tks = $('#red-tickers').value.split(/[\s,;]+/).map((t) => t.trim().toUpperCase()).filter(Boolean);
  const btn = $('#btn-red'); btn.disabled = true; btn.textContent = 'Valorando…';
  $('#red-aviso').textContent = '';
  try {
    const r = await api('/api/opcion', { tickers: tks, anios_hist: +$('#anios_hist').value, n_sims: 20000 });
    $('#red-aviso').innerHTML = r.normalizacion === 'exacta'
      ? 'Normalización del entrenamiento cargada desde <code>modelos/normalizacion.json</code>.'
      : 'Aviso: no se encontró <code>modelos/normalizacion.json</code>. Las entradas se estandarizan con las propias simulaciones y la escala del payoff se ajusta con el 20 % de las trayectorias (excluidas del error). Ejecuta <code>python exportar_normalizacion.py</code> para usar la normalización exacta del notebook.';
    $('#red-kpis').innerHTML = `
      <div class="kpi"><div class="titulo">Prima por Monte Carlo</div><div class="grande">${fmtNum(r.prima_mc, 4)}</div>
        <div class="linea"><span>Error estándar</span><b>± ${fmtNum(r.err_estandar_mc, 4)}</b></div>
        <div class="linea"><span>Trayectorias evaluadas</span><b>${r.n_eval.toLocaleString('es-ES')}</b></div></div>
      <div class="kpi"><div class="titulo">Probabilidad de ejercicio</div><div class="grande">${fmtPct(r.prob_ejercicio)}</div>
        <div class="linea"><span>Payoff medio</span><b>${fmtNum(r.payoff_medio, 4)}</b></div></div>
      <div class="kpi"><div class="titulo">Volatilidad anual</div>
        ${r.tickers.map((t, k) => `<div class="linea"><span>${t}</span><b>${fmtPct(r.sigma[k])}</b></div>`).join('')}</div>`;
    $('#red-bloque-tabla').hidden = false; $('#red-bloque-graf').hidden = false;
    const cols = COLORES();
    $('#red-tabla').innerHTML = `<table><thead><tr><th>Modelo</th><th>Parámetros</th><th>Prima estimada</th><th>Error prima</th><th>RMSE</th><th>MAE</th><th>R²</th></tr></thead>
      <tbody>${r.modelos.map((m, i) => `<tr><td><span class="punto" style="--c:${cols[i]}"></span>${m.celda.toUpperCase()}</td>
        <td>${m.params.toLocaleString('es-ES')}</td><td>${fmtNum(m.prima, 4)}</td><td>${fmtNum(m.err_prima_pct, 2)} %</td>
        <td>${fmtNum(m.rmse, 4)}</td><td>${fmtNum(m.mae, 4)}</td><td>${fmtNum(m.r2, 3)}</td></tr>`).join('')}</tbody></table>`;
    const d = r.dispersion;
    const mx = Math.max(...d.real, ...r.modelos.flatMap((m) => d[m.celda]));
    const trazas = r.modelos.map((m, i) => ({
      type: 'scattergl', mode: 'markers', name: m.celda.toUpperCase(), x: d.real, y: d[m.celda],
      marker: { size: 5, color: alpha(cols[i], 0.5) }, hovertemplate: `${m.celda.toUpperCase()}<br>real %{x:.3f} · red %{y:.3f}<extra></extra>`,
    }));
    trazas.push({ mode: 'lines', x: [0, mx], y: [0, mx], name: 'Predicción perfecta', line: { color: css('--muted'), dash: 'dash', width: 1 }, hoverinfo: 'skip' });
    Plotly.react('g-red', trazas, layoutBase({
      hovermode: 'closest',
      xaxis: { title: 'Payoff real (Monte Carlo)', gridcolor: css('--grid'), linecolor: css('--axis') },
      yaxis: { title: 'Payoff predicho por la red', gridcolor: css('--grid'), linecolor: css('--axis') },
    }), CFG);
  } catch (e) {
    $('#red-aviso').innerHTML = `<span class="neg">${e.message}</span>`;
  } finally {
    btn.disabled = false; btn.textContent = 'Valorar';
  }
}

/* ------------------------------------------------------------------ */
/*  Arranque                                                           */
/* ------------------------------------------------------------------ */
document.querySelectorAll('.tab').forEach((t) => t.addEventListener('click', () => {
  document.querySelectorAll('.tab').forEach((x) => x.classList.toggle('activa', x === t));
  document.querySelectorAll('.panel').forEach((p) => p.classList.toggle('activo', p.id === `tab-${t.dataset.tab}`));
  window.dispatchEvent(new Event('resize'));  // Plotly recalcula tamaños
}));
$('#btn-simular').addEventListener('click', simular);
$('#btn-add-cartera').addEventListener('click', () => { if (carteras.length < MAX_CARTERAS) { carteras.push(nuevaCartera()); renderCarteras(); } });
$('#btn-ejemplo').addEventListener('click', () => {
  carteras = [
    nuevaCartera('Tecnológica', [{ ticker: 'AAPL', peso: 40 }, { ticker: 'MSFT', peso: 40 }, { ticker: 'CRM', peso: 20 }]),
    nuevaCartera('Defensiva', [{ ticker: 'KO', peso: 25 }, { ticker: 'PG', peso: 25 }, { ticker: 'JNJ', peso: 25 }, { ticker: 'MCD', peso: 25 }]),
    nuevaCartera('Mixta', [{ ticker: 'MSFT', peso: 30 }, { ticker: 'JPM', peso: 30 }, { ticker: 'KO', peso: 20 }, { ticker: 'CAT', peso: 20 }]),
  ];
  renderCarteras(); simular();
});
$('#sel-cartera-activos').addEventListener('change', renderActivos);
$('#sel-cartera-hist').addEventListener('change', renderHistorico);
$('#btn-frontera').addEventListener('click', calcularFrontera);
$('#btn-red').addEventListener('click', valorarRed);
$('#btn-red-usar').addEventListener('click', () => {
  $('#red-tickers').value = carteras[0].filas.map((f) => f.ticker).filter(Boolean).join(', ');
});

(async () => {
  carteras = [nuevaCartera('Cartera 1')];
  renderCarteras();
  try {
    const t = await api('/api/tickers');
    TICKERS = t.tickers;
    $('#lista-tickers').innerHTML = TICKERS.map((x) => `<option value="${x.ticker}">${x.ticker} · ${fmtNum(x.precio)} $</option>`).join('');
    const [yy, mm, dd] = t.fecha_datos.split('-');
    $('#info-datos').textContent = `${TICKERS.length} valores del Dow Jones hasta el ${+dd}/${+mm}/${yy}`;
  } catch (e) {
    $('#error').textContent = 'No se pudo cargar la lista de tickers: ' + e.message;
  }
})();
