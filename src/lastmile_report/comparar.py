"""Eval en vivo: la misma prueba, con varios modelos, mostrando cada paso.

Uso (en tu terminal, para verlo correr en tiempo real):
    uv run lastmile-comparar data/daily/DSE5_2018-07-28.csv data/daily/DLA7_2018-08-01.csv
    uv run lastmile-comparar <archivos> --modelos gpt-4.1-mini gpt-4o-mini --repeticiones 3

Guarda los resultados en evals/resultados/ (JSON con todo el detalle + HTML para leer).
"""

import argparse
import html
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from lastmile_report.cli import procesar
from lastmile_report.llm import generar_reporte

MODELOS = ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1", "gpt-5-mini"]
SALIDA = Path("evals/resultados")


def decir(texto: str = "") -> None:
    print(texto, flush=True)


def una_corrida(modelo: str, archivo: Path, rep: int, metricas, alertas, prompt: str) -> dict:
    """Una llamada al modelo + su verificación. Nunca lanza excepción: la registra."""
    base = {"modelo": modelo, "archivo": archivo.name, "repeticion": rep}
    try:
        r = generar_reporte(metricas, alertas, modelo, prompt, reintentos=0)
    except Exception as e:  # noqa: BLE001 - en un eval, un fallo es un dato más
        return base | {"errores": [f"fallo_llamada:{type(e).__name__}"], "costo_usd": 0, "segundos": 0}
    return base | r.model_dump(exclude={"modelo"})


def resumir(corridas: list[dict]) -> list[dict]:
    """Una fila por modelo: lo que va a la tabla final."""
    filas = []
    for modelo in dict.fromkeys(c["modelo"] for c in corridas):
        suyas = [c for c in corridas if c["modelo"] == modelo]
        tipos = Counter(e.split(":")[0] for c in suyas for e in c["errores"])
        n = len(suyas)
        filas.append(
            {
                "modelo": modelo,
                "corridas": n,
                "aciertos_pct": round(100 * sum(not c["errores"] for c in suyas) / n, 1),
                "errores_por_reporte": round(sum(len(c["errores"]) for c in suyas) / n, 2),
                "errores_por_tipo": dict(tipos),
                "costo_usd_por_reporte": round(sum(c["costo_usd"] or 0 for c in suyas) / n, 5),
                "segundos_por_reporte": round(sum(c["segundos"] for c in suyas) / n, 1),
            }
        )
    return filas


def a_html(resumen: list[dict], corridas: list[dict], prompt: str) -> str:
    def e(x) -> str:
        return html.escape(str(x))

    filas = "".join(
        f"<tr><td><b>{e(f['modelo'])}</b></td><td>{f['aciertos_pct']} %</td><td>{f['errores_por_reporte']}</td>"
        f"<td>{e(', '.join(f'{k}: {v}' for k, v in f['errores_por_tipo'].items()) or '—')}</td>"
        f"<td>{f['costo_usd_por_reporte']:.5f}</td><td>{f['segundos_por_reporte']}</td></tr>"
        for f in resumen
    )
    detalle = ""
    for c in corridas:
        ok = not c["errores"]
        errores = "".join(f"<li>{e(x)}</li>" for x in c["errores"]) or "<li>ninguno</li>"
        texto = e(c.get("reporte", {}).get("resumen", "(sin respuesta)"))
        alertas = "".join(
            f"<li><code>{e(a['codigo'])}</code> {e(a['mensaje'])}</li>"
            for a in c.get("reporte", {}).get("alertas", [])
        )
        detalle += (
            f"<details><summary><span class='{'ok' if ok else 'mal'}'>{'CORRECTO' if ok else 'CON ERRORES'}</span> "
            f"{e(c['modelo'])} · {e(c['archivo'])} · intento {c['repeticion']} · "
            f"{c['segundos']} s · {c['costo_usd'] or 0:.5f} USD</summary>"
            f"<p><b>Errores detectados por el verificador</b></p><ul>{errores}</ul>"
            f"<p><b>Resumen que escribió el modelo</b></p><p>{texto}</p>"
            f"<p><b>Alertas que escribió</b></p><ul>{alertas or '<li>ninguna</li>'}</ul></details>"
        )
    return f"""<!doctype html><html lang="es"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Comparación de modelos</title>
<style>
:root{{--bg:#fff;--fg:#1a1a1a;--mut:#666;--line:#ddd;--ok:#1a7f37;--mal:#c62828;--card:#f6f6f6}}
@media(prefers-color-scheme:dark){{:root{{--bg:#16181c;--fg:#e8e8e8;--mut:#9aa;--line:#333;--ok:#4cc26a;--mal:#ff6b6b;--card:#1f2228}}}}
body{{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;max-width:1000px;margin:0 auto;padding:24px 16px}}
table{{border-collapse:collapse;width:100%;margin:12px 0}}th,td{{border-bottom:1px solid var(--line);padding:8px;text-align:left}}
th{{color:var(--mut);font-weight:600;font-size:13px}}.ok{{color:var(--ok);font-weight:700}}.mal{{color:var(--mal);font-weight:700}}
details{{background:var(--card);border-radius:8px;padding:10px 14px;margin:8px 0}}summary{{cursor:pointer}}
.tabla{{overflow-x:auto}}p.nota{{color:var(--mut)}}
</style>
<h1>Comparación de modelos</h1>
<p class="nota">Prompt {e(prompt)} · {len(corridas)} corridas · misma entrada para todos los modelos.
Un reporte cuenta como acierto solo si el verificador no encuentra ningún error.</p>
<div class="tabla"><table><tr><th>Modelo</th><th>Aciertos</th><th>Errores por reporte</th><th>Tipos de error</th>
<th>Costo por reporte (USD)</th><th>Tiempo por reporte (s)</th></tr>{filas}</table></div>
<h2>Detalle de cada corrida</h2>{detalle}</html>"""


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Compara modelos sobre los mismos archivos")
    p.add_argument("archivos", nargs="+", type=Path)
    p.add_argument("--modelos", nargs="+", default=MODELOS)
    p.add_argument("--repeticiones", type=int, default=3)
    p.add_argument("--prompt", default="v1")
    args = p.parse_args()

    decir("PASO 1 · El código calcula métricas y alertas (sin modelo, cuesta 0)")
    casos = {}
    for archivo in args.archivos:
        m, alertas = procesar(archivo)
        casos[archivo] = (m, alertas)
        decir(
            f"  {archivo.name}: {m.paquetes} paquetes, {m.tasa_fallidos_pct}% fallidos, "
            f"alertas esperadas: {[a.codigo for a in alertas] or 'ninguna'}"
        )

    total = len(casos) * len(args.modelos) * args.repeticiones
    decir(
        f"\nPASO 2 · Se envía la MISMA entrada a {len(args.modelos)} modelos, {args.repeticiones} veces cada uno"
    )
    decir(f"  ({total} llamadas; se repite porque un modelo no responde igual dos veces)")
    decir("\nPASO 3 · Cada respuesta pasa por el verificador apenas llega\n")

    corridas = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        tareas = [
            pool.submit(una_corrida, modelo, archivo, rep, m, alertas, args.prompt)
            for archivo, (m, alertas) in casos.items()
            for modelo in args.modelos
            for rep in range(1, args.repeticiones + 1)
        ]
        for i, tarea in enumerate(as_completed(tareas), 1):
            c = tarea.result()
            corridas.append(c)
            estado = "OK   " if not c["errores"] else "FALLA"
            decir(
                f"  [{i:>2}/{total}] {estado} {c['modelo']:<14} {c['archivo']:<22} "
                f"{c['segundos']:>5}s  ${c['costo_usd'] or 0:.5f}  {c['errores'] or ''}"
            )

    corridas.sort(key=lambda c: (args.modelos.index(c["modelo"]), c["archivo"], c["repeticion"]))
    resumen = resumir(corridas)
    decir("\nPASO 4 · Tabla final\n")
    decir(f"  {'modelo':<14} {'aciertos':>9} {'err/rep':>8} {'USD/rep':>9} {'seg/rep':>8}")
    for f in resumen:
        decir(
            f"  {f['modelo']:<14} {f['aciertos_pct']:>8}% {f['errores_por_reporte']:>8} "
            f"{f['costo_usd_por_reporte']:>9.5f} {f['segundos_por_reporte']:>8}"
        )

    SALIDA.mkdir(parents=True, exist_ok=True)
    nombre = f"comparacion_{args.prompt}_{datetime.now():%Y%m%d_%H%M%S}"
    (SALIDA / f"{nombre}.json").write_text(
        json.dumps(
            {"prompt": args.prompt, "resumen": resumen, "corridas": corridas}, indent=2, ensure_ascii=False
        ),
        encoding="utf-8",
    )
    (SALIDA / f"{nombre}.html").write_text(a_html(resumen, corridas, args.prompt), encoding="utf-8")
    decir(f"\nGuardado en {SALIDA / nombre}.json y .html")


if __name__ == "__main__":
    main()
