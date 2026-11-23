"""API y página web local, para usar el sistema desde el navegador.

Uso:  uv run lastmile-api     y luego abrir  http://localhost:8000

Corre en tu propio equipo: no necesita internet (salvo la llamada al modelo),
ni GitHub, ni ningún servicio de despliegue.
"""

import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from lastmile_report.evals import CASOS, cargar_casos
from lastmile_report.metrics import calcular_alertas, calcular_metricas, cargar_dia

app = FastAPI(title="Reporte diario de última milla")


def _responder(archivo: Path, historico: list[float], solo_metricas: bool) -> dict:
    try:
        metricas = calcular_metricas(cargar_dia(archivo))
    except ValueError as e:  # archivo inválido: se le explica a la persona, no se llama al modelo
        raise HTTPException(status_code=422, detail=str(e)) from e
    alertas = calcular_alertas(metricas, historico)
    salida = {"metricas": metricas.model_dump(), "alertas_calculadas": [a.model_dump() for a in alertas]}
    if not solo_metricas:
        from lastmile_report.llm import generar_reporte

        salida |= generar_reporte(metricas, alertas).model_dump()
    return salida


def _tasas(texto: str) -> list[float]:
    try:
        return [float(x) for x in texto.replace(";", ",").split(",") if x.strip()]
    except ValueError as e:
        raise HTTPException(status_code=422, detail="El histórico debe ser una lista de números") from e


@app.get("/salud")
def salud() -> dict:
    return {"estado": "ok"}


@app.get("/casos")
def casos() -> list[dict]:
    """Los 50 casos de ejemplo, para probar sin tener un archivo propio."""
    return [{"id": c["id"], "tipo": c["tipo"], "origen": c["origen"]} for c in cargar_casos()]


@app.post("/reporte/caso/{caso_id}")
def reporte_de_caso(caso_id: str, solo_metricas: bool = False) -> dict:
    caso = next((c for c in cargar_casos() if c["id"] == caso_id), None)
    if caso is None:
        raise HTTPException(status_code=404, detail="Ese caso no existe")
    return _responder(CASOS / caso["archivo"], caso["historico_tasas"], solo_metricas)


@app.post("/reporte")
def reporte_de_archivo(
    archivo: UploadFile,
    historico: Annotated[str, Form()] = "",  # % de fallidos de días anteriores, separados por coma
    solo_metricas: Annotated[bool, Form()] = False,
) -> dict:
    sufijo = Path(archivo.filename or "dia.csv").suffix or ".csv"
    with tempfile.TemporaryDirectory() as carpeta:
        destino = Path(carpeta) / f"dia{sufijo}"
        destino.write_bytes(archivo.file.read())
        return _responder(destino, _tasas(historico), solo_metricas)


@app.get("/", response_class=HTMLResponse)
def pagina() -> str:
    return PAGINA


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)


PAGINA = """<!doctype html><html lang="es"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Reporte de última milla</title>
<style>
:root{--bg:#f7f7f8;--card:#fff;--fg:#1a1a1a;--mut:#667;--line:#e2e2e6;--pri:#2456d6;--ok:#1a7f37;--mal:#c62828;--med:#b26a00}
@media(prefers-color-scheme:dark){:root{--bg:#131518;--card:#1c1f24;--fg:#e9e9ea;--mut:#9aa0aa;--line:#2c3038;--pri:#6f9bff;--ok:#4cc26a;--mal:#ff6b6b;--med:#f0b24a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
main{max-width:980px;margin:0 auto;padding:24px 16px}h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:0 0 10px}
.mut{color:var(--mut);font-size:13px}.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin:14px 0}
.fila{display:flex;gap:10px;flex-wrap:wrap;align-items:center}select,input[type=text],input[type=file]{font:inherit;padding:7px;border:1px solid var(--line);border-radius:7px;background:var(--bg);color:var(--fg);max-width:100%}
button{font:inherit;padding:8px 14px;border:0;border-radius:7px;background:var(--pri);color:#fff;cursor:pointer}button:disabled{opacity:.5}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px}.kpi{border:1px solid var(--line);border-radius:8px;padding:10px}
.kpi b{display:block;font-size:20px}.kpi span{font-size:12px;color:var(--mut)}
.alerta{border-left:4px solid var(--mal);padding:6px 10px;margin:8px 0}.alerta.media{border-color:var(--med)}
.ok{color:var(--ok);font-weight:700}.mal{color:var(--mal);font-weight:700}code{font-size:12px;word-break:break-all}
ul{margin:6px 0;padding-left:20px}pre{overflow:auto;font-size:12px;max-height:340px}
</style><main>
<h1>Reporte diario de última milla</h1>
<p class="mut">El código calcula las cifras, el modelo redacta y un verificador comprueba cada número.</p>
<div class="card"><h2>1. Elige los datos del día</h2>
<div class="fila"><label>Caso de ejemplo <select id="caso"></select></label><button id="bCaso">Generar reporte</button></div>
<p class="mut">o sube tu propio archivo (CSV o Excel con el mismo formato):</p>
<div class="fila"><input type="file" id="archivo" accept=".csv,.xlsx">
<input type="text" id="hist" placeholder="Histórico de % fallidos: 0.5, 0.7, 0.4" size="34">
<button id="bArchivo">Generar reporte</button></div>
<p><label><input type="checkbox" id="solo"> Solo métricas (no llama al modelo, gratis)</label></p></div>
<div id="salida"></div></main>
<script>
const $=id=>document.getElementById(id), esc=s=>String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
fetch('/casos').then(r=>r.json()).then(cs=>{$('caso').innerHTML=cs.map(c=>`<option value="${c.id}">${c.id} · ${c.tipo} · ${c.origen}</option>`).join('')});
async function pedir(url,opts){
  const out=$('salida');out.innerHTML='<div class="card">Procesando… (unos segundos si se llama al modelo)</div>';
  document.querySelectorAll('button').forEach(b=>b.disabled=true);
  try{const r=await fetch(url,opts);const d=await r.json();out.innerHTML=r.ok?pintar(d):`<div class="card"><span class="mal">Archivo rechazado:</span> ${esc(d.detail)}</div>`}
  catch(e){out.innerHTML=`<div class="card mal">Error: ${esc(e)}</div>`}
  document.querySelectorAll('button').forEach(b=>b.disabled=false);
}
function pintar(d){
  const m=d.metricas,k=(v,t)=>`<div class="kpi"><b>${v}</b><span>${t}</span></div>`;
  let h=`<div class="card"><h2>2. Lo que calculó el código · ${esc(m.station_code)} · ${esc(m.date)}</h2><div class="kpis">`+
    k(m.paquetes,'paquetes')+k(m.entregados,'entregados')+k(m.intentos_fallidos,'intentos fallidos')+k(m.tasa_entrega_pct+' %','tasa de entrega')+
    k(m.tasa_fallidos_pct+' %','tasa de fallidos')+k(m.rutas,'rutas')+k(m.ocupacion_promedio_pct+' %','ocupación promedio')+k(m.calidad_datos.recuperados_en_reintento,'recuperados en reintento')+
    `</div><p class="mut">Alertas calculadas: ${d.alertas_calculadas.map(a=>esc(a.codigo)).join(', ')||'ninguna'}</p></div>`;
  if(!d.reporte) return h+`<div class="card"><h2>Datos completos</h2><pre>${esc(JSON.stringify(d,null,2))}</pre></div>`;
  const r=d.reporte;
  h+=`<div class="card"><h2>3. Lo que redactó el modelo</h2><p>${esc(r.resumen)}</p>`+
    (r.alertas.length?'<h2>Alertas</h2>'+r.alertas.map(a=>`<div class="alerta ${a.severidad}"><b>${esc(a.codigo)}</b> · ${a.severidad} · <code>${esc(a.entidad)}</code><br>${esc(a.mensaje)}</div>`).join(''):'<p class="mut">Sin alertas hoy.</p>')+
    `<h2>Recomendaciones</h2><ul>${r.recomendaciones.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`;
  h+=`<div class="card"><h2>4. Verificación</h2><p>${d.errores.length?`<span class="mal">Con errores:</span> ${d.errores.map(esc).join(', ')}`:'<span class="ok">Reporte fiel a los datos: ninguna cifra inventada.</span>'}</p>
    <p class="mut">Modelo ${esc(d.modelo)} · prompt ${esc(d.prompt)} · ${d.intentos} intento(s) · ${d.segundos} s · ${d.costo_usd} USD · ${d.tokens_entrada} tokens de entrada, ${d.tokens_salida} de salida</p></div>`;
  return h;
}
$('bCaso').onclick=()=>pedir(`/reporte/caso/${$('caso').value}?solo_metricas=${$('solo').checked}`,{method:'POST'});
$('bArchivo').onclick=()=>{const f=$('archivo').files[0];if(!f){alert('Elige un archivo primero');return}
  const fd=new FormData();fd.append('archivo',f);fd.append('historico',$('hist').value);fd.append('solo_metricas',$('solo').checked);pedir('/reporte',{method:'POST',body:fd})};
</script></html>"""
