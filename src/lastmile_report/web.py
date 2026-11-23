"""La página web (HTML + CSS + JavaScript en un solo texto, sin dependencias).

Tres pestañas:
  - Generar reporte: elegir datos, modelo y prompt; ver cifras, texto y verificación.
  - Evaluaciones:    la tabla de versiones medidas sobre los 50 casos.
  - Historial:       cada prueba hecha en esta sesión, para comparar experimentos.

Enlace directo:  /?caso=caso_21&auto=1   genera ese reporte al abrir.
                 /?tab=evals             abre la pestaña de evaluaciones.
"""

PAGINA = r"""<!doctype html><html lang="es"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Reporte de última milla</title>
<style>
:root{--plano:#f9f9f7;--sup:#fcfcfb;--tinta:#0b0b0b;--tinta2:#52514e;--mut:#898781;--linea:#e1e0d9;--serie:#2a78d6;--pista:#ecebe6;
--bien:#0ca30c;--bienTx:#006300;--aviso:#fab219;--critico:#d03b3b;--pri:#184f95}
@media(prefers-color-scheme:dark){:root{--plano:#0d0d0d;--sup:#1a1a19;--tinta:#f0efec;--tinta2:#c3c2b7;--linea:#2c2c2a;--serie:#3987e5;--pista:#2c2c2a;--bienTx:#0ca30c;--pri:#3987e5}}
*{box-sizing:border-box}body{margin:0;background:var(--plano);color:var(--tinta);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1040px;margin:0 auto;padding:22px 16px 60px}
header{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap}
h1{font-size:22px;margin:0}h2{font-size:15px;margin:0 0 10px}h3{font-size:13px;margin:16px 0 6px;color:var(--tinta2);font-weight:600}
.mut{color:var(--mut);font-size:13px}.sec{color:var(--tinta2)}
nav{display:flex;gap:4px;margin:16px 0 4px;border-bottom:1px solid var(--linea)}
nav button{background:none;border:0;border-bottom:2px solid transparent;color:var(--tinta2);padding:8px 12px;font:inherit;cursor:pointer;border-radius:0}
nav button.on{color:var(--tinta);border-color:var(--serie);font-weight:600}
.card{background:var(--sup);border:1px solid var(--linea);border-radius:10px;padding:16px;margin:14px 0}
.fila{display:flex;gap:10px;flex-wrap:wrap;align-items:end}label{font-size:12px;color:var(--tinta2);display:flex;flex-direction:column;gap:3px}
label.check{flex-direction:row;align-items:center;font-size:14px;color:var(--tinta)}
select,input[type=text],input[type=file]{font:inherit;padding:7px 8px;border:1px solid var(--linea);border-radius:7px;background:var(--plano);color:var(--tinta);max-width:100%}
.btn{font:inherit;padding:8px 14px;border:0;border-radius:7px;background:var(--pri);color:#fff;cursor:pointer}.btn:disabled{opacity:.5;cursor:wait}
.btn.sec2{background:none;border:1px solid var(--linea);color:var(--tinta)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px}
.kpi{border:1px solid var(--linea);border-radius:8px;padding:10px 12px}.kpi b{display:block;font-size:22px;font-weight:600;font-variant-numeric:tabular-nums}
.kpi span{font-size:12px;color:var(--tinta2)}
.tabla{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{padding:7px 8px;text-align:left;border-bottom:1px solid var(--linea);white-space:nowrap}th{color:var(--mut);font-weight:600;font-size:12px}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}td.txt{white-space:normal}
.pista{display:inline-block;width:110px;height:8px;background:var(--pista);border-radius:4px;vertical-align:middle;margin-right:8px}
.barra{display:block;height:8px;background:var(--serie);border-radius:4px}
.estado{display:inline-flex;align-items:center;gap:6px;font-weight:600}.punto{width:10px;height:10px;border-radius:50%;display:inline-block}
.alerta{border:1px solid var(--linea);border-left:4px solid var(--critico);border-radius:6px;padding:8px 12px;margin:8px 0}
.alerta.media{border-left-color:var(--aviso)}.chip{display:inline-block;border:1px solid var(--linea);border-radius:20px;padding:2px 10px;font-size:12px;margin:2px 4px 2px 0}
code{font-size:12px;word-break:break-all;color:var(--tinta2)}ul{margin:6px 0;padding-left:20px}
.dos{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:760px){.dos{grid-template-columns:1fr}}
.oculto{display:none}
</style><main>
<header><div><h1>Reporte diario de última milla</h1>
<div class="mut">El código calcula las cifras · el modelo redacta · un verificador comprueba cada número</div></div>
<div class="mut" id="sesion"></div></header>
<nav><button data-tab="reporte" class="on">Generar reporte</button><button data-tab="evals">Evaluaciones</button><button data-tab="historial">Historial de pruebas</button></nav>

<section id="tab-reporte">
<div class="card"><h2>1 · Datos del día y configuración</h2>
<div class="fila">
 <label>Caso de ejemplo<select id="caso"></select></label>
 <label>Modelo<select id="modelo"></select></label>
 <label>Prompt<select id="prompt"></select></label>
 <label>Reintentos<select id="reintentos"><option>0</option><option>1</option><option>2</option></select></label>
 <button class="btn" id="bCaso">Generar reporte</button>
</div>
<h3>O sube tu propio archivo (CSV o Excel con el mismo formato)</h3>
<div class="fila"><input type="file" id="archivo" accept=".csv,.xlsx">
 <label>Histórico de % fallidos (opcional)<input type="text" id="hist" placeholder="0.5, 0.7, 0.4" size="22"></label>
 <button class="btn sec2" id="bArchivo">Generar con mi archivo</button></div>
<p><label class="check"><input type="checkbox" id="solo">&nbsp;Solo métricas: no llama al modelo, no cuesta nada</label></p></div>
<div id="salida"><p class="mut">Elige un caso y pulsa "Generar reporte". Los casos 21 a 35 son días malos, con alertas.</p></div>
</section>

<section id="tab-evals" class="oculto"><div class="card"><h2>Versiones evaluadas sobre los 50 casos</h2>
<p class="mut">Un caso es acierto solo si las cifras del código coinciden con lo esperado, las alertas son exactamente las esperadas y el verificador no encuentra ningún error en el texto del modelo.</p>
<div class="tabla" id="evals"></div></div></section>

<section id="tab-historial" class="oculto"><div class="card"><h2>Pruebas hechas en esta sesión</h2>
<p class="mut">Repite el mismo caso con otro modelo o prompt y compara aquí el resultado, el costo y el tiempo.</p>
<div class="tabla" id="historial"><p class="mut">Todavía no has generado ningún reporte.</p></div></div></section>
</main>
<script>
const $=id=>document.getElementById(id), esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const num=(v,d=0)=>Number(v).toLocaleString('es-CO',{minimumFractionDigits:d,maximumFractionDigits:d});
const corta=id=>id.replace(/^RouteID_/,'').slice(0,8);
const pruebas=[]; let ultimo=null;
const barra=(v,max,t)=>`<span class="pista" title="${esc(t)}"><span class="barra" style="width:${Math.max(0,Math.min(100,100*v/max))}%"></span></span>`;
const estado=(ok,t)=>`<span class="estado"><span class="punto" style="background:var(${ok?'--bien':'--critico'})"></span>${ok?'✓':'✗'} ${esc(t)}</span>`;

document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>ver(b.dataset.tab));
function ver(tab){document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('on',b.dataset.tab===tab));
  ['reporte','evals','historial'].forEach(t=>$('tab-'+t).classList.toggle('oculto',t!==tab)); if(tab==='evals') cargarEvals();}

async function iniciar(){
  const [cs,op]=await Promise.all([fetch('/casos').then(r=>r.json()),fetch('/opciones').then(r=>r.json())]);
  $('caso').innerHTML=cs.map(c=>`<option value="${c.id}">${c.id} · ${c.tipo}${c.suciedad.length?' ('+c.suciedad.join(' + ')+')':''} · ${c.origen}</option>`).join('');
  $('modelo').innerHTML=op.modelos.map(m=>`<option${m===op.defecto.modelo?' selected':''}>${m}</option>`).join('');
  $('prompt').innerHTML=op.prompts.map(p=>`<option${p===op.defecto.prompt?' selected':''}>${p}</option>`).join('');
  $('reintentos').value=op.defecto.reintentos;
  const q=new URLSearchParams(location.search);
  for(const k of ['caso','modelo','prompt','reintentos']) if(q.get(k)) $(k).value=q.get(k);
  if(q.get('tab')) ver(q.get('tab'));
  if(q.get('auto')) $('bCaso').click();
}
const config=()=>({modelo:$('modelo').value,prompt:$('prompt').value,reintentos:$('reintentos').value,solo_metricas:$('solo').checked});

async function pedir(url,opts,origen){
  const out=$('salida');out.innerHTML='<div class="card">Procesando… el modelo tarda unos segundos.</div>';
  document.querySelectorAll('.btn').forEach(b=>b.disabled=true);
  try{const r=await fetch(url,opts);const d=await r.json();
    if(r.ok){ultimo=d;out.innerHTML=pintar(d);registrar(d,origen)}
    else out.innerHTML=`<div class="card">${estado(false,'Archivo rechazado')}<p>${esc(d.detail)}</p><p class="mut">El sistema no llama al modelo cuando el archivo no se puede leer con confianza.</p></div>`}
  catch(e){out.innerHTML=`<div class="card">${estado(false,'Error')}<p>${esc(e)}</p></div>`}
  document.querySelectorAll('.btn').forEach(b=>b.disabled=false);
}
$('bCaso').onclick=()=>{const c=config();pedir(`/reporte/caso/${$('caso').value}?`+new URLSearchParams(c),{method:'POST'},$('caso').value)};
$('bArchivo').onclick=()=>{const f=$('archivo').files[0];if(!f){alert('Elige un archivo primero');return}
  const fd=new FormData();fd.append('archivo',f);fd.append('historico',$('hist').value);for(const [k,v] of Object.entries(config())) fd.append(k,v);pedir('/reporte',{method:'POST',body:fd},f.name)};

function pintar(d){
  const m=d.metricas,q=m.calidad_datos,k=(v,t)=>`<div class="kpi"><b>${v}</b><span>${t}</span></div>`;
  const prom=d.historico.length?num(d.historico.reduce((a,b)=>a+b,0)/d.historico.length,2)+' %':'sin histórico';
  let h=`<div class="card"><h2>2 · Lo que calculó el código · estación ${esc(m.station_code)} · ${esc(m.date)}</h2><div class="kpis">`+
    k(num(m.paquetes),'paquetes')+k(num(m.entregados),'entregados')+k(num(m.intentos_fallidos),'intentos fallidos')+
    k(num(m.tasa_entrega_pct,2)+' %','tasa de entrega')+k(num(m.tasa_fallidos_pct,2)+' %','tasa de fallidos')+
    k(prom,'fallidos, promedio días previos')+k(num(m.rutas),'rutas')+k(num(m.ocupacion_promedio_pct,2)+' %','ocupación promedio')+`</div>`+
    `<h3>Alertas decididas por reglas</h3>${d.alertas_calculadas.map(a=>`<span class="chip">${esc(a.codigo)} · ${a.severidad}</span>`).join('')||'<span class="mut">Ninguna: día dentro de lo normal.</span>'}`+
    `<div class="dos"><div><h3>Rutas con más intentos fallidos</h3><div class="tabla"><table><tr><th>Ruta</th><th>Calidad</th><th class="n">Paquetes</th><th class="n">Fallidos</th><th class="n">Tasa</th><th>Ocupación</th></tr>`+
    (m.peores_rutas.map(r=>`<tr><td title="${esc(r.route_id)}"><code>${corta(r.route_id)}</code></td><td>${esc(r.route_score)}</td><td class="n">${r.paquetes}</td><td class="n">${r.fallidos}</td><td class="n">${num(r.tasa_fallidos_pct,2)} %</td><td>${barra(r.ocupacion_pct,100,r.ocupacion_pct+' % del vehículo')}${num(r.ocupacion_pct,1)} %</td></tr>`).join('')||'<tr><td colspan="6" class="mut">Ninguna ruta tuvo fallidos.</td></tr>')+
    `</table></div></div><div><h3>Zonas con más intentos fallidos</h3><div class="tabla"><table><tr><th>Zona</th><th class="n">Paquetes</th><th class="n">Fallidos</th></tr>`+
    (m.peores_zonas.map(z=>`<tr><td><code>${esc(z.zone_id)}</code></td><td class="n">${z.paquetes}</td><td class="n">${z.fallidos}</td></tr>`).join('')||'<tr><td colspan="3" class="mut">Ninguna.</td></tr>')+
    `</table></div><h3>Calidad del archivo</h3><p class="sec" style="margin:0;font-size:13.5px">${num(q.filas_leidas)} filas leídas · ${q.duplicados_eliminados} duplicadas · ${q.estados_desconocidos} con estado desconocido · ${q.dimensiones_invalidas} con dimensiones inválidas · ${q.recuperados_en_reintento} paquetes recuperados en reintento</p></div></div></div>`;
  if(!d.reporte) return h+'<p class="mut">Modo solo métricas: no se llamó al modelo.</p>';
  const r=d.reporte;
  h+=`<div class="card"><h2>3 · Lo que redactó el modelo</h2><p>${esc(r.resumen)}</p>`+
    (r.alertas.length?'<h3>Alertas</h3>'+r.alertas.map(a=>`<div class="alerta ${a.severidad}"><b>${a.severidad==='alta'?'▲':'●'} ${esc(a.codigo)}</b> · severidad ${a.severidad} · <code>${esc(a.entidad)}</code><br>${esc(a.mensaje)}</div>`).join(''):'')+
    `<h3>Recomendaciones</h3><ul>${r.recomendaciones.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`+
    `<h3>Lectura de los indicadores</h3><div class="tabla"><table>${r.indicadores.map(i=>`<tr><td><code>${esc(i.clave)}</code></td><td class="n">${i.valor}</td><td class="txt">${esc(i.lectura)}</td></tr>`).join('')}</table></div></div>`;
  h+=`<div class="card"><h2>4 · Verificación automática</h2><p>${d.errores.length?estado(false,'Reporte con errores'):estado(true,'Reporte fiel a los datos: ninguna cifra inventada')}</p>`+
    (d.errores.length?`<ul>${d.errores.map(e=>`<li><code>${esc(e)}</code></li>`).join('')}</ul>`:'')+
    `<div class="kpis">${k(esc(d.modelo),'modelo')}${k(esc(d.prompt),'prompt')}${k(d.intentos,'intentos')}${k(num(d.segundos,1)+' s','tiempo')}${k(num(d.costo_usd,5)+' USD','costo')}${k(num(d.tokens_entrada)+' / '+num(d.tokens_salida),'tokens entrada / salida')}</div>`+
    `<p style="margin-bottom:0"><button class="btn sec2" onclick="descargar()">Descargar reporte (.md)</button></p></div>`;
  return h;
}
function descargar(){const d=ultimo,m=d.metricas,r=d.reporte;
  const md=`# Reporte diario · ${m.station_code} · ${m.date}\n\n${r.resumen}\n\n## Indicadores\n\n| Indicador | Valor | Lectura |\n|---|---|---|\n`+
    r.indicadores.map(i=>`| ${i.clave} | ${i.valor} | ${i.lectura} |`).join('\n')+`\n\n## Alertas\n\n`+(r.alertas.map(a=>`- **${a.codigo}** (${a.severidad}, ${a.entidad}): ${a.mensaje}`).join('\n')||'Sin alertas.')+
    `\n\n## Recomendaciones\n\n`+r.recomendaciones.map(x=>`- ${x}`).join('\n')+`\n\n---\nGenerado con ${d.modelo}, prompt ${d.prompt}. Verificación: ${d.errores.length?d.errores.join(', '):'sin errores'}.\n`;
  const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([md],{type:'text/markdown'}));a.download=`reporte_${m.station_code}_${m.date}.md`;a.click();}
function registrar(d,origen){
  if(!d.reporte) return;
  pruebas.unshift({origen,modelo:d.modelo,prompt:d.prompt,intentos:d.intentos,ok:!d.errores.length,errores:d.errores,costo:d.costo_usd,seg:d.segundos});
  const total=pruebas.reduce((a,p)=>a+(p.costo||0),0);
  $('sesion').textContent=`${pruebas.length} reporte(s) en esta sesión · ${num(total,5)} USD`;
  $('historial').innerHTML=`<table><tr><th>Datos</th><th>Modelo</th><th>Prompt</th><th class="n">Intentos</th><th>Resultado</th><th class="n">Costo (USD)</th><th class="n">Tiempo (s)</th></tr>`+
    pruebas.map(p=>`<tr><td>${esc(p.origen)}</td><td>${esc(p.modelo)}</td><td>${esc(p.prompt)}</td><td class="n">${p.intentos}</td><td title="${esc(p.errores.join(', '))}">${estado(p.ok,p.ok?'fiel':p.errores.length+' error(es)')}</td><td class="n">${num(p.costo,5)}</td><td class="n">${num(p.seg,1)}</td></tr>`).join('')+`</table>`;
}
async function cargarEvals(){
  const fs=await fetch('/evals').then(r=>r.json());
  const maxC=Math.max(...fs.map(f=>f.costo_usd_por_reporte)),maxS=Math.max(...fs.map(f=>f.segundos_por_reporte));
  $('evals').innerHTML=`<table><tr><th>Versión</th><th>Modelo</th><th>Prompt</th><th class="n">Reintentos</th><th>Aciertos</th><th>Costo por reporte</th><th>Tiempo por reporte</th></tr>`+
    fs.map(f=>`<tr><td>${esc(f.etiqueta)}</td><td>${esc(f.modelo)}</td><td>${esc(f.prompt)}</td><td class="n">${f.reintentos??0}</td>`+
      `<td>${barra(f.aciertos_pct,100,f.aciertos_pct+' % de 50 casos')}${num(f.aciertos_pct,0)} %</td>`+
      `<td>${barra(f.costo_usd_por_reporte,maxC,f.costo_usd_por_reporte+' USD')}${num(f.costo_usd_por_reporte,5)} USD</td>`+
      `<td>${barra(f.segundos_por_reporte,maxS,f.segundos_por_reporte+' s')}${num(f.segundos_por_reporte,1)} s</td></tr>`).join('')+`</table>`;
}
iniciar();
</script></html>"""
