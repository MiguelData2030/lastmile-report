"""Fase 1: todo lo que se CALCULA. Aquí no hay LLM.

Flujo:  archivo del día -> cargar_dia() -> limpiar() -> calcular_metricas()
        -> calcular_alertas()

El modelo de lenguaje recibirá después solo el resultado (MetricasDia y
la lista de Alerta). Nunca verá las filas ni hará una suma.
"""

from pathlib import Path
from typing import Literal

import pandas as pd
from pydantic import BaseModel

COLUMNAS_REQUERIDAS = [
    "station_code",
    "date",
    "route_id",
    "route_score",
    "executor_capacity_cm3",
    "stop_id",
    "zone_id",
    "package_id",
    "scan_status",
    "depth_cm",
    "height_cm",
    "width_cm",
]
ESTADOS_VALIDOS = {"DELIVERED", "DELIVERY_ATTEMPTED", "REJECTED"}
# Si un paquete tiene varias filas, gana el estado de menor número.
PRIORIDAD_ESTADO = {"DELIVERED": 0, "REJECTED": 1, "DELIVERY_ATTEMPTED": 2, "UNKNOWN": 3}

# Umbrales de alerta. Viven en código para que sean visibles y testeables.
UMBRAL_FALLIDOS_PCT = 2.0  # tasa de fallidos de la estación
UMBRAL_RUTA_FALLIDOS_PCT = 5.0  # tasa de fallidos de una ruta
MIN_FALLIDOS_RUTA = 5  # evita alertar por 1 fallido en una ruta pequeña
FACTOR_SOBRE_HISTORICO = 1.5  # hoy vs. promedio de días previos
MIN_DIAS_HISTORICO = 3


# ---------- Modelos de salida (el "contrato" con el resto del sistema) ----------


class CalidadDatos(BaseModel):
    filas_leidas: int
    duplicados_eliminados: int
    recuperados_en_reintento: int  # no es un problema de datos; se informa aparte
    estados_desconocidos: int
    dimensiones_invalidas: int


class RutaResumen(BaseModel):
    route_id: str
    route_score: str
    paquetes: int
    fallidos: int
    tasa_fallidos_pct: float
    ocupacion_pct: float


class ZonaResumen(BaseModel):
    zone_id: str
    paquetes: int
    fallidos: int


class MetricasDia(BaseModel):
    station_code: str
    date: str
    paquetes: int
    entregados: int
    intentos_fallidos: int
    rechazados: int
    tasa_entrega_pct: float
    tasa_fallidos_pct: float
    rutas: int
    paradas: int
    paquetes_por_ruta: float
    ocupacion_promedio_pct: float
    rutas_por_score: dict[str, int]
    paquetes_con_ventana_horaria: int
    peores_rutas: list[RutaResumen]
    rutas_criticas: list[RutaResumen]  # todas las que superan el umbral, no solo el top
    peores_zonas: list[ZonaResumen]
    calidad_datos: CalidadDatos


class Alerta(BaseModel):
    codigo: str
    severidad: Literal["alta", "media"]
    entidad: str  # "estacion", un route_id, etc.
    valor: float
    referencia: float  # umbral o promedio histórico contra el que se comparó


# ---------- Carga y limpieza ----------


def cargar_dia(ruta: str | Path) -> pd.DataFrame:
    """Lee el archivo del día (CSV o Excel) sin interpretar nada todavía."""
    ruta = Path(ruta)
    if ruta.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(ruta, dtype=str)
    return pd.read_csv(ruta, dtype=str)


def _a_numero(serie: pd.Series) -> pd.Series:
    """'25,4' -> 25.4 ; texto basura -> NaN."""
    texto = serie.astype("string").str.strip().str.replace(",", ".", regex=False)
    return pd.to_numeric(texto, errors="coerce")


def limpiar(df: pd.DataFrame) -> tuple[pd.DataFrame, CalidadDatos]:
    """Normaliza el archivo y deja constancia de cada problema encontrado."""
    df = df.rename(columns=lambda c: str(c).strip().lower())
    faltantes = [c for c in COLUMNAS_REQUERIDAS if c not in df.columns]
    if faltantes:
        raise ValueError(f"Faltan columnas en el archivo: {faltantes}")
    if df.empty:
        raise ValueError("El archivo no tiene filas")

    filas_leidas = len(df)
    df = df.drop_duplicates().copy()  # filas idénticas completas = error de exportación
    duplicados = filas_leidas - len(df)

    df["scan_status"] = df["scan_status"].astype("string").str.strip().str.upper()
    desconocidos = ~df["scan_status"].isin(ESTADOS_VALIDOS)
    df.loc[desconocidos, "scan_status"] = "UNKNOWN"

    # Un mismo paquete puede aparecer dos veces en el día: un intento fallido
    # y luego la entrega en otra parada. No es un duplicado: es un reintento.
    # Nos quedamos con su mejor estado final y contamos los recuperados.
    estados = df.groupby("package_id")["scan_status"].agg(set)
    recuperados = int(estados.map(lambda s: {"DELIVERED", "DELIVERY_ATTEMPTED"} <= s).sum())
    df["_prioridad"] = df["scan_status"].map(PRIORIDAD_ESTADO)
    df = df.sort_values("_prioridad", kind="stable").drop_duplicates(subset="package_id").copy()

    for col in ["depth_cm", "height_cm", "width_cm", "executor_capacity_cm3"]:
        df[col] = _a_numero(df[col])
    dims = df[["depth_cm", "height_cm", "width_cm"]]
    dims_invalidas = dims.isna().any(axis=1) | (dims <= 0).any(axis=1)
    df["volumen_cm3"] = (dims.prod(axis=1)).where(~dims_invalidas, 0.0)

    calidad = CalidadDatos(
        filas_leidas=filas_leidas,
        duplicados_eliminados=duplicados,
        recuperados_en_reintento=recuperados,
        estados_desconocidos=int(desconocidos.sum()),
        dimensiones_invalidas=int(dims_invalidas.sum()),
    )
    return df, calidad


# ---------- Métricas ----------


def _pct(parte: float, total: float) -> float:
    return round(100 * parte / total, 2) if total else 0.0


def _resumir_rutas(tabla: pd.DataFrame) -> list[RutaResumen]:
    return [
        RutaResumen(
            route_id=str(rid),
            route_score=str(r["route_score"]),
            paquetes=int(r["paquetes"]),
            fallidos=int(r["fallidos"]),
            tasa_fallidos_pct=float(r["tasa"]),
            ocupacion_pct=float(r["ocupacion"]),
        )
        for rid, r in tabla.iterrows()
    ]


def calcular_metricas(df: pd.DataFrame, top: int = 3) -> MetricasDia:
    """Recibe el archivo crudo del día y devuelve todas las cifras del reporte."""
    df, calidad = limpiar(df)
    df["fallido"] = df["scan_status"].eq("DELIVERY_ATTEMPTED")

    por_ruta = df.groupby("route_id").agg(
        route_score=("route_score", "first"),
        paquetes=("package_id", "size"),
        fallidos=("fallido", "sum"),
        volumen=("volumen_cm3", "sum"),
        capacidad=("executor_capacity_cm3", "first"),
    )
    por_ruta["tasa"] = [_pct(f, p) for f, p in zip(por_ruta["fallidos"], por_ruta["paquetes"])]
    por_ruta["ocupacion"] = [_pct(v, c) for v, c in zip(por_ruta["volumen"], por_ruta["capacidad"])]

    peores_rutas = por_ruta[por_ruta["fallidos"] > 0].sort_values(["fallidos", "tasa"], ascending=False)
    criticas = peores_rutas[
        (peores_rutas["fallidos"] >= MIN_FALLIDOS_RUTA) & (peores_rutas["tasa"] >= UMBRAL_RUTA_FALLIDOS_PCT)
    ]
    por_zona = df.groupby("zone_id").agg(paquetes=("package_id", "size"), fallidos=("fallido", "sum"))
    peores_zonas = por_zona[por_zona["fallidos"] > 0].sort_values("fallidos", ascending=False)

    total = len(df)
    fallidos = int(df["fallido"].sum())
    entregados = int(df["scan_status"].eq("DELIVERED").sum())
    return MetricasDia(
        station_code=str(df["station_code"].iloc[0]),
        date=str(df["date"].iloc[0]),
        paquetes=total,
        entregados=entregados,
        intentos_fallidos=fallidos,
        rechazados=int(df["scan_status"].eq("REJECTED").sum()),
        tasa_entrega_pct=_pct(entregados, total),
        tasa_fallidos_pct=_pct(fallidos, total),
        rutas=len(por_ruta),
        paradas=int(df.groupby("route_id")["stop_id"].nunique().sum()),
        paquetes_por_ruta=round(total / len(por_ruta), 1),
        ocupacion_promedio_pct=round(float(por_ruta["ocupacion"].mean()), 2),
        rutas_por_score={str(k): int(v) for k, v in por_ruta["route_score"].value_counts().items()},
        paquetes_con_ventana_horaria=int(df["tw_start_utc"].notna().sum())
        if "tw_start_utc" in df.columns
        else 0,
        peores_rutas=_resumir_rutas(peores_rutas.head(top)),
        rutas_criticas=_resumir_rutas(criticas),
        peores_zonas=[
            ZonaResumen(zone_id=str(z), paquetes=int(r["paquetes"]), fallidos=int(r["fallidos"]))
            for z, r in peores_zonas.head(top).iterrows()
        ],
        calidad_datos=calidad,
    )


# ---------- Alertas ----------


def calcular_alertas(hoy: MetricasDia, historico: list[float] | None = None) -> list[Alerta]:
    """Decide qué merece atención. Reglas explícitas, no opinión del modelo.

    `historico` son las tasas de fallidos (%) de días anteriores de la misma estación.
    """
    alertas: list[Alerta] = []
    historico = historico or []

    if len(historico) >= MIN_DIAS_HISTORICO:
        promedio = round(sum(historico) / len(historico), 2)
        if promedio > 0 and hoy.tasa_fallidos_pct >= FACTOR_SOBRE_HISTORICO * promedio:
            alertas.append(
                Alerta(
                    codigo="FALLIDOS_SOBRE_HISTORICO",
                    severidad="alta",
                    entidad="estacion",
                    valor=hoy.tasa_fallidos_pct,
                    referencia=promedio,
                )
            )
    if hoy.tasa_fallidos_pct >= UMBRAL_FALLIDOS_PCT:
        alertas.append(
            Alerta(
                codigo="FALLIDOS_ALTOS",
                severidad="alta",
                entidad="estacion",
                valor=hoy.tasa_fallidos_pct,
                referencia=UMBRAL_FALLIDOS_PCT,
            )
        )
    for r in hoy.rutas_criticas:
        alertas.append(
            Alerta(
                codigo="RUTA_CRITICA",
                severidad="alta",
                entidad=r.route_id,
                valor=r.tasa_fallidos_pct,
                referencia=UMBRAL_RUTA_FALLIDOS_PCT,
            )
        )
    rutas_low = hoy.rutas_por_score.get("Low", 0)
    if rutas_low:
        alertas.append(
            Alerta(
                codigo="RUTAS_BAJA_CALIDAD",
                severidad="media",
                entidad="estacion",
                valor=rutas_low,
                referencia=0,
            )
        )
    c = hoy.calidad_datos
    problemas = c.duplicados_eliminados + c.estados_desconocidos + c.dimensiones_invalidas
    if problemas:
        alertas.append(
            Alerta(
                codigo="CALIDAD_DATOS", severidad="media", entidad="archivo", valor=problemas, referencia=0
            )
        )
    return alertas
