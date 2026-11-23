"""Construye los 50 casos de prueba de evals/casos/.

Cada caso = un archivo de entrada + lo que el reporte DEBE decir (esperado).

Importante: lo esperado se calcula aquí con Python puro (módulo csv), SIN usar
el código del proyecto (metrics.py). Así son dos implementaciones independientes:
si las dos coinciden, es muy improbable que ambas estén mal de la misma forma.

Uso (requiere data/daily, ver ingest.py):  uv run python evals/construir_casos.py
"""

import csv
import json
import random
import shutil
from collections import defaultdict
from pathlib import Path

import pandas as pd

DAILY = Path("data/daily")
CASOS = Path("evals/casos")
MAX_PAQUETES = 1500  # días pequeños: el repositorio se mantiene liviano
PRIORIDAD = {"DELIVERED": 0, "REJECTED": 1, "DELIVERY_ATTEMPTED": 2}
ALERTAS_GRAVES = ("FALLIDOS_ALTOS", "FALLIDOS_SOBRE_HISTORICO", "RUTA_CRITICA")


# ---------- Implementación independiente de lo esperado ----------


def resumen_dia(archivo: Path) -> dict:
    final = {}  # package_id -> fila con su mejor estado
    with archivo.open(newline="", encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            previa = final.get(fila["package_id"])
            if previa is None or PRIORIDAD[fila["scan_status"]] < PRIORIDAD[previa["scan_status"]]:
                final[fila["package_id"]] = fila

    por_ruta = defaultdict(lambda: {"paquetes": 0, "fallidos": 0, "score": ""})
    conteo = defaultdict(int)
    dims_invalidas = 0
    for fila in final.values():
        conteo[fila["scan_status"]] += 1
        ruta = por_ruta[fila["route_id"]]
        ruta["paquetes"] += 1
        ruta["fallidos"] += fila["scan_status"] == "DELIVERY_ATTEMPTED"
        ruta["score"] = fila["route_score"]
        try:
            dims_invalidas += min(float(fila[c]) for c in ("depth_cm", "height_cm", "width_cm")) <= 0
        except ValueError:
            dims_invalidas += 1

    total = len(final)
    return {
        "paquetes": total,
        "entregados": conteo["DELIVERED"],
        "intentos_fallidos": conteo["DELIVERY_ATTEMPTED"],
        "rechazados": conteo["REJECTED"],
        "tasa_fallidos_pct": round(100 * conteo["DELIVERY_ATTEMPTED"] / total, 2),
        "rutas": len(por_ruta),
        "_criticas": sorted(
            rid
            for rid, r in por_ruta.items()
            if r["fallidos"] >= 5 and round(100 * r["fallidos"] / r["paquetes"], 2) >= 5.0
        ),
        "_rutas_low": sum(r["score"] == "Low" for r in por_ruta.values()),
        "_dims_invalidas": dims_invalidas,
    }


def alertas_esperadas(r: dict, historico: list[float], suciedad: bool) -> list[str]:
    alertas = []
    if len(historico) >= 3:
        promedio = round(sum(historico) / len(historico), 2)
        if promedio > 0 and r["tasa_fallidos_pct"] >= 1.5 * promedio:
            alertas.append("FALLIDOS_SOBRE_HISTORICO:estacion")
    if r["tasa_fallidos_pct"] >= 2.0:
        alertas.append("FALLIDOS_ALTOS:estacion")
    alertas += [f"RUTA_CRITICA:{rid}" for rid in r["_criticas"]]
    if r["_rutas_low"]:
        alertas.append("RUTAS_BAJA_CALIDAD:estacion")
    if suciedad or r["_dims_invalidas"]:
        alertas.append("CALIDAD_DATOS:archivo")
    return sorted(alertas)


def publico(r: dict) -> dict:
    return {k: v for k, v in r.items() if not k.startswith("_")}


# ---------- Suciedad inyectada (sabemos exactamente qué rompimos) ----------


def ensuciar(df: pd.DataFrame, tipo: str, rng: random.Random, esperado: dict) -> tuple[pd.DataFrame, bool]:
    """Devuelve el archivo ensuciado y si eso debe disparar CALIDAD_DATOS."""
    if tipo == "encabezados":
        return df.rename(columns=lambda c: f" {c.upper()} "), False
    if tipo == "estados_mal_escritos":
        idx = rng.sample(list(df.index), k=max(1, len(df) // 10))
        df.loc[idx, "scan_status"] = df.loc[idx, "scan_status"].map(lambda s: f" {s.lower()}  ")
        return df, False
    if tipo == "coma_decimal":
        for c in ("depth_cm", "height_cm", "width_cm"):
            df[c] = df[c].str.replace(".", ",", regex=False)
        return df, False
    if tipo == "filas_duplicadas":
        extra = df.loc[rng.sample(list(df.index), k=rng.randint(3, 12))]
        return pd.concat([df, extra], ignore_index=True), True
    if tipo == "estado_desconocido":
        unicos = df[~df["package_id"].duplicated(keep=False) & df["scan_status"].eq("DELIVERED")]
        idx = rng.sample(list(unicos.index), k=rng.randint(2, 8))
        df.loc[idx, "scan_status"] = rng.choice(["???", "", "PENDIENTE"])
        esperado["entregados"] -= len(idx)  # ya no se puede afirmar que se entregaron
        return df, True
    if tipo == "dimension_basura":
        idx = rng.sample(list(df.index), k=rng.randint(2, 8))
        df.loc[idx, "depth_cm"] = rng.choice(["N/A", "-1", ""])
        return df, True
    if tipo == "excel":
        return df, False
    raise ValueError(tipo)


TIPOS = [
    "encabezados",
    "estados_mal_escritos",
    "coma_decimal",
    "filas_duplicadas",
    "estado_desconocido",
    "dimension_basura",
    "excel",
]


def main() -> None:
    rng = random.Random(2021)

    # 1. Resumen e histórico de todos los días reales
    por_estacion = defaultdict(list)
    for archivo in sorted(DAILY.glob("*.csv")):
        por_estacion[archivo.stem.split("_")[0]].append(archivo)
    dias = []
    for archivos in por_estacion.values():
        tasas = []
        for archivo in archivos:
            r = resumen_dia(archivo)
            dias.append({"archivo": archivo, "resumen": r, "historico": tasas[-7:]})
            tasas.append(r["tasa_fallidos_pct"])

    # 2. Clasificar y elegir
    candidatos = [d for d in dias if d["resumen"]["paquetes"] <= MAX_PAQUETES]
    for d in candidatos:
        d["alertas"] = alertas_esperadas(d["resumen"], d["historico"], suciedad=False)
        d["malo"] = any(a.startswith(ALERTAS_GRAVES) for a in d["alertas"])
    rng.shuffle(candidatos)
    malos = [d for d in candidatos if d["malo"]]
    normales = [d for d in candidatos if not d["malo"]]
    plan = (
        [("normal", d, []) for d in normales[:20]]
        + [("malo", d, []) for d in malos[:15]]
        + [("sucio", d, [TIPOS[i % 7]]) for i, d in enumerate(normales[20:24] + malos[15:18])]
        + [
            ("sucio", d, [TIPOS[i % 7], TIPOS[(i + 3) % 7]])
            for i, d in enumerate(normales[24:27] + malos[18:21])
        ]
        + [("invalido", normales[27], ["sin_columna_estado"]), ("invalido", normales[28], ["sin_filas"])]
    )
    assert len(plan) == 50, len(plan)

    # 3. Escribir archivos y casos.json
    shutil.rmtree(CASOS, ignore_errors=True)
    (CASOS / "archivos").mkdir(parents=True)
    casos = []
    for n, (tipo, d, suciedad) in enumerate(plan, 1):
        cid = f"caso_{n:02d}"
        df = pd.read_csv(d["archivo"], dtype=str, keep_default_na=False)
        esperado = publico(d["resumen"])
        extension = "xlsx" if "excel" in suciedad else "csv"

        if tipo == "invalido":
            if suciedad == ["sin_columna_estado"]:
                df, esperado = df.drop(columns=["scan_status"]), {"error": "Faltan columnas"}
            else:
                df, esperado = df.iloc[0:0], {"error": "no tiene filas"}
        else:
            dispara = False
            for s in suciedad:
                df, d_s = ensuciar(df, s, rng, esperado)
                dispara = dispara or d_s
            esperado["alertas"] = alertas_esperadas(d["resumen"], d["historico"], suciedad=dispara)

        destino = CASOS / "archivos" / f"{cid}.{extension}"
        df.to_excel(destino, index=False) if extension == "xlsx" else df.to_csv(destino, index=False)
        casos.append(
            {
                "id": cid,
                "tipo": tipo,
                "archivo": f"archivos/{destino.name}",
                "origen": d["archivo"].stem,
                "suciedad": suciedad,
                "historico_tasas": d["historico"],
                "esperado": esperado,
            }
        )

    (CASOS / "casos.json").write_text(json.dumps(casos, indent=2, ensure_ascii=False), encoding="utf-8")
    peso = sum(p.stat().st_size for p in (CASOS / "archivos").iterdir()) / 1e6
    print(f"{len(casos)} casos en {CASOS} ({peso:.1f} MB)")
    for t in ("normal", "malo", "sucio", "invalido"):
        print(f"  {t}: {sum(c['tipo'] == t for c in casos)}")


if __name__ == "__main__":
    main()
