"""Fase 3: corre los 50 casos y entrega aciertos, costo y tiempo por reporte.

Uso:
    uv run lastmile-eval                       # prompt v1, modelo por defecto
    uv run lastmile-eval --prompt v2 --modelo gpt-4o-mini --etiqueta v2
    uv run lastmile-eval --sin-modelo          # solo la parte de código (gratis)

Un caso es ACIERTO solo si se cumplen las tres cosas:
  1. cálculo:  las cifras del código coinciden con lo esperado
  2. alertas:  el código disparó exactamente las alertas esperadas
  3. reporte:  el verificador no encuentra ningún error en lo que escribió el modelo
"""

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from lastmile_report.metrics import calcular_alertas, calcular_metricas, cargar_dia

CASOS = Path("evals/casos")
RESULTADOS = Path("evals/resultados")


def cargar_casos(carpeta: Path = CASOS) -> list[dict]:
    return json.loads((carpeta / "casos.json").read_text(encoding="utf-8"))


def evaluar_codigo(caso: dict, carpeta: Path = CASOS):
    """Parte sin modelo. Devuelve (resultado, metricas, alertas)."""
    esperado = caso["esperado"]
    r = {"id": caso["id"], "tipo": caso["tipo"], "errores": [], "costo_usd": 0.0, "segundos": 0.0}
    try:
        m = calcular_metricas(cargar_dia(carpeta / caso["archivo"]))
    except ValueError as e:
        ok = "error" in esperado and esperado["error"] in str(e)
        return r | {"calculo_ok": ok, "alertas_ok": ok, "rechazado": True}, None, None
    if "error" in esperado:  # debía rechazar el archivo y no lo hizo
        return r | {"calculo_ok": False, "alertas_ok": False, "rechazado": False}, None, None

    alertas = calcular_alertas(m, caso["historico_tasas"])
    datos = m.model_dump()
    diferencias = {k: (datos[k], v) for k, v in esperado.items() if k != "alertas" and datos[k] != v}
    obtenidas = sorted(f"{a.codigo}:{a.entidad}" for a in alertas)
    r |= {
        "calculo_ok": not diferencias,
        "alertas_ok": obtenidas == esperado["alertas"],
        "diferencias": {k: {"obtenido": o, "esperado": e} for k, (o, e) in diferencias.items()},
        "alertas_obtenidas": obtenidas,
    }
    return r, m, alertas


def evaluar_caso(caso: dict, modelo: str | None, prompt: str) -> dict:
    r, m, alertas = evaluar_codigo(caso)
    if m is not None and modelo:
        from lastmile_report.llm import generar_reporte

        try:
            res = generar_reporte(m, alertas, modelo, prompt)
            r |= {
                "errores": res.errores,
                "costo_usd": res.costo_usd or 0.0,
                "segundos": res.segundos,
                "tokens_entrada": res.tokens_entrada,
                "tokens_salida": res.tokens_salida,
                "reporte": res.reporte.model_dump(),
            }
        except Exception as e:  # noqa: BLE001 - en un eval, un fallo es un dato más
            r["errores"] = [f"fallo_llamada:{type(e).__name__}"]
    r["acierto"] = r["calculo_ok"] and r["alertas_ok"] and not r["errores"]
    return r


def resumir(resultados: list[dict]) -> dict:
    def pct(clave, grupo):
        return round(100 * sum(bool(c[clave]) for c in grupo) / len(grupo), 1)

    con_reporte = [c for c in resultados if "reporte" in c or c["errores"]]
    return {
        "casos": len(resultados),
        "aciertos_pct": pct("acierto", resultados),
        "calculo_ok_pct": pct("calculo_ok", resultados),
        "alertas_ok_pct": pct("alertas_ok", resultados),
        "reporte_fiel_pct": round(100 * sum(not c["errores"] for c in con_reporte) / len(con_reporte), 1)
        if con_reporte
        else None,
        "aciertos_por_tipo": {
            t: pct("acierto", [c for c in resultados if c["tipo"] == t])
            for t in dict.fromkeys(c["tipo"] for c in resultados)
        },
        "errores_por_tipo": dict(Counter(e.split(":")[0] for c in resultados for e in c["errores"])),
        "reportes_generados": len(con_reporte),
        "costo_usd_por_reporte": round(sum(c["costo_usd"] for c in con_reporte) / len(con_reporte), 5)
        if con_reporte
        else 0,
        "segundos_por_reporte": round(sum(c["segundos"] for c in con_reporte) / len(con_reporte), 1)
        if con_reporte
        else 0,
        "costo_usd_total": round(sum(c["costo_usd"] for c in resultados), 4),
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Evalúa el sistema sobre los 50 casos")
    p.add_argument("--modelo", default=None)
    p.add_argument("--prompt", default="v1")
    p.add_argument("--etiqueta", default=None, help="Nombre con el que se guarda esta versión")
    p.add_argument("--sin-modelo", action="store_true")
    args = p.parse_args()

    modelo = None
    if not args.sin_modelo:
        from lastmile_report.llm import MODELO_DEFECTO

        modelo = args.modelo or MODELO_DEFECTO
    etiqueta = args.etiqueta or (f"{args.prompt}_{modelo}" if modelo else "solo_codigo")

    casos = cargar_casos()
    print(
        f"Evaluando {len(casos)} casos · modelo: {modelo or 'ninguno'} · prompt: {args.prompt}\n", flush=True
    )
    resultados = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        tareas = [pool.submit(evaluar_caso, c, modelo, args.prompt) for c in casos]
        for i, t in enumerate(as_completed(tareas), 1):
            r = t.result()
            resultados.append(r)
            marcas = "".join("✓" if r[k] else "✗" for k in ("calculo_ok", "alertas_ok"))
            print(
                f"  [{i:>2}/{len(casos)}] {'ACIERTO' if r['acierto'] else 'FALLO  '} {r['id']} {r['tipo']:<8} "
                f"código {marcas}  {r['segundos']:>5}s  ${r['costo_usd']:.5f}  {r['errores'] or ''}",
                flush=True,
            )

    resultados.sort(key=lambda r: r["id"])
    resumen = {"etiqueta": etiqueta, "modelo": modelo, "prompt": args.prompt} | resumir(resultados)
    print("\nRESUMEN")
    for k, v in resumen.items():
        print(f"  {k:<24} {v}")

    RESULTADOS.mkdir(parents=True, exist_ok=True)
    destino = RESULTADOS / f"{etiqueta}.json"
    destino.write_text(
        json.dumps({"resumen": resumen, "casos": resultados}, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nGuardado en {destino}")


if __name__ == "__main__":
    main()
