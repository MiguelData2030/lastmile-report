"""Convierte el dataset crudo de Amazon (JSON anidado) en "archivos del día".

Entrada : data/raw/route_data.json y data/raw/package_data.json
Salida  : data/daily/<estacion>_<fecha>.csv  (una fila por paquete)

Cada CSV representa lo que un analista descargaría del sistema al cierre
del día en una estación. Es la entrada del resto del proyecto.

Uso: uv run python -m lastmile_report.ingest
"""

import json
from pathlib import Path

import pandas as pd

RAW = Path("data/raw")
DAILY = Path("data/daily")


def _texto_o_none(valor):
    """El dataset usa NaN (float) cuando no hay ventana horaria."""
    return valor if isinstance(valor, str) else None


def aplanar(rutas: dict, paquetes: dict) -> pd.DataFrame:
    """Une rutas + paradas + paquetes en una sola tabla plana."""
    filas = []
    for route_id, ruta in rutas.items():
        for stop_id, paquetes_parada in paquetes.get(route_id, {}).items():
            parada = ruta["stops"][stop_id]
            for package_id, p in paquetes_parada.items():
                filas.append(
                    {
                        "station_code": ruta["station_code"],
                        "date": ruta["date_YYYY_MM_DD"],
                        "route_id": route_id,
                        "departure_time_utc": ruta["departure_time_utc"],
                        "route_score": ruta["route_score"],
                        "executor_capacity_cm3": ruta["executor_capacity_cm3"],
                        "stop_id": stop_id,
                        "zone_id": parada["zone_id"],
                        "lat": parada["lat"],
                        "lng": parada["lng"],
                        "package_id": package_id,
                        "scan_status": p["scan_status"],
                        "tw_start_utc": _texto_o_none(p["time_window"]["start_time_utc"]),
                        "tw_end_utc": _texto_o_none(p["time_window"]["end_time_utc"]),
                        "planned_service_time_s": p["planned_service_time_seconds"],
                        "depth_cm": p["dimensions"]["depth_cm"],
                        "height_cm": p["dimensions"]["height_cm"],
                        "width_cm": p["dimensions"]["width_cm"],
                    }
                )
    return pd.DataFrame(filas)


def main() -> None:
    rutas = json.loads((RAW / "route_data.json").read_text())
    paquetes = json.loads((RAW / "package_data.json").read_text())
    tabla = aplanar(rutas, paquetes)

    DAILY.mkdir(parents=True, exist_ok=True)
    for (estacion, fecha), dia in tabla.groupby(["station_code", "date"]):
        dia.to_csv(DAILY / f"{estacion}_{fecha}.csv", index=False)

    print(f"{len(tabla):,} paquetes -> {tabla.groupby(['station_code', 'date']).ngroups} archivos en {DAILY}")


if __name__ == "__main__":
    main()
