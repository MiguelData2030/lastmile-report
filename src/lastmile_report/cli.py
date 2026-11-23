"""Línea de comandos: para que otra persona use el sistema sin tocar código.

Uso:
    uv run lastmile-report data/daily/DLA7_2018-08-01.csv
    uv run lastmile-report data/daily/DLA7_2018-08-01.csv --solo-metricas
"""

import argparse
import json
import sys
from pathlib import Path

from lastmile_report.metrics import Alerta, MetricasDia, calcular_alertas, calcular_metricas, cargar_dia

DIAS_HISTORICO = 7


def procesar(archivo: Path) -> tuple[MetricasDia, list[Alerta]]:
    """Métricas y alertas de un archivo, usando como histórico los días
    anteriores de la misma estación que estén en la misma carpeta
    (archivos nombrados <estacion>_<fecha>.csv)."""
    hoy = calcular_metricas(cargar_dia(archivo))
    previos = sorted(
        p for p in archivo.parent.glob(f"{hoy.station_code}_*{archivo.suffix}") if p.stem < archivo.stem
    )[-DIAS_HISTORICO:]
    historico = [calcular_metricas(cargar_dia(p)).tasa_fallidos_pct for p in previos]
    return hoy, calcular_alertas(hoy, historico)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Reporte diario de última milla")
    parser.add_argument("archivo", type=Path, help="CSV o Excel del día")
    parser.add_argument("--solo-metricas", action="store_true", help="No llama al modelo")
    parser.add_argument("--modelo", default=None)
    parser.add_argument("--prompt", default=None)
    args = parser.parse_args()

    metricas, alertas = procesar(args.archivo)
    if args.solo_metricas:
        salida = {"metricas": metricas.model_dump(), "alertas": [a.model_dump() for a in alertas]}
    else:
        from lastmile_report.llm import MODELO_DEFECTO, PROMPT_DEFECTO, generar_reporte

        salida = generar_reporte(
            metricas, alertas, args.modelo or MODELO_DEFECTO, args.prompt or PROMPT_DEFECTO
        ).model_dump()
    print(json.dumps(salida, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
