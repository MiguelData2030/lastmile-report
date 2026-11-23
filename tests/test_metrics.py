"""Tests de la Fase 1. Usan datos mínimos hechos a mano: si sé la respuesta
de memoria, puedo comprobar que el código la calcula bien."""

import pandas as pd
import pytest

from lastmile_report.metrics import calcular_alertas, calcular_metricas, cargar_dia


def fila(package_id, route_id="R1", status="DELIVERED", zone="Z1", stop="AA", **extra):
    base = {
        "station_code": "DXX1",
        "date": "2018-08-01",
        "route_id": route_id,
        "route_score": "High",
        "executor_capacity_cm3": "1000",
        "stop_id": stop,
        "zone_id": zone,
        "package_id": package_id,
        "scan_status": status,
        "tw_start_utc": None,
        "depth_cm": "10",
        "height_cm": "10",
        "width_cm": "1",  # volumen = 100 cm3
    }
    return base | extra


def dia_normal() -> pd.DataFrame:
    """10 paquetes, 2 rutas. R1: 8 paquetes y 1 fallido. R2: 2 entregados."""
    filas = [fila(f"P{i}") for i in range(7)]
    filas.append(fila("P7", status="DELIVERY_ATTEMPTED", zone="Z2", stop="AB"))
    filas += [fila("P8", route_id="R2"), fila("P9", route_id="R2")]
    return pd.DataFrame(filas)


def test_conteos_y_tasas():
    m = calcular_metricas(dia_normal())
    assert (m.paquetes, m.entregados, m.intentos_fallidos, m.rechazados) == (10, 9, 1, 0)
    assert m.tasa_entrega_pct == 90.0
    assert m.tasa_fallidos_pct == 10.0
    assert m.rutas == 2
    assert m.paradas == 3  # R1: AA y AB ; R2: AA
    assert m.paquetes_por_ruta == 5.0


def test_ocupacion_y_peores():
    m = calcular_metricas(dia_normal())
    # R1: 800/1000 = 80% ; R2: 200/1000 = 20% ; promedio 50%
    assert m.ocupacion_promedio_pct == 50.0
    assert [r.route_id for r in m.peores_rutas] == ["R1"]
    assert m.peores_rutas[0].tasa_fallidos_pct == 12.5
    assert [z.zone_id for z in m.peores_zonas] == ["Z2"]


def test_datos_sucios():
    df = dia_normal()
    df.loc[0, "scan_status"] = " delivered "  # espacios y minúsculas
    df.loc[1, "scan_status"] = "???"  # estado inexistente
    df.loc[2, "depth_cm"] = "10,0"  # coma decimal
    df.loc[3, "depth_cm"] = "abc"  # basura
    df = pd.concat([df, df.iloc[[8]]])  # paquete duplicado
    df.columns = [c.upper() + " " for c in df.columns]  # encabezados descuidados

    m = calcular_metricas(df)
    assert m.paquetes == 10
    assert m.entregados == 8  # el "???" ya no cuenta como entregado
    assert m.calidad_datos.duplicados_eliminados == 1
    assert m.calidad_datos.estados_desconocidos == 1
    assert m.calidad_datos.dimensiones_invalidas == 1


def test_archivo_invalido():
    with pytest.raises(ValueError, match="Faltan columnas"):
        calcular_metricas(dia_normal().drop(columns=["scan_status"]))
    with pytest.raises(ValueError, match="no tiene filas"):
        calcular_metricas(dia_normal().iloc[0:0])


def test_lee_csv_y_excel(tmp_path):
    df = dia_normal()
    df.to_csv(tmp_path / "dia.csv", index=False)
    df.to_excel(tmp_path / "dia.xlsx", index=False)
    assert calcular_metricas(cargar_dia(tmp_path / "dia.csv")) == calcular_metricas(
        cargar_dia(tmp_path / "dia.xlsx")
    )


def test_alertas_dia_malo():
    filas = [fila(f"P{i}") for i in range(14)]
    filas += [fila(f"F{i}", status="DELIVERY_ATTEMPTED") for i in range(6)]  # 6 de 20 = 30%
    m = calcular_metricas(pd.DataFrame(filas))
    codigos = {a.codigo for a in calcular_alertas(m)}
    assert codigos == {"FALLIDOS_ALTOS", "RUTA_CRITICA"}


def test_alertas_dia_limpio_y_historico():
    limpio = calcular_metricas(pd.DataFrame([fila(f"P{i}") for i in range(10)]))
    assert calcular_alertas(limpio) == []

    # 1 fallido de 100 = 1%: bajo el umbral fijo, pero el doble de lo habitual
    filas = [fila(f"P{i}") for i in range(99)] + [fila("F", status="DELIVERY_ATTEMPTED")]
    hoy = calcular_metricas(pd.DataFrame(filas))
    previos = [0.5] * 3
    assert [a.codigo for a in calcular_alertas(hoy, previos)] == ["FALLIDOS_SOBRE_HISTORICO"]
    assert calcular_alertas(hoy, previos[:2]) == []  # histórico insuficiente


def test_reintento_exitoso_no_es_duplicado():
    """Hallazgo en datos reales: fallido en una parada y entregado en otra."""
    df = dia_normal()  # P7 falló en la parada AB
    df = pd.concat([df, pd.DataFrame([fila("P7", stop="AC")])])  # ...y luego se entregó
    m = calcular_metricas(df)
    assert m.paquetes == 10
    assert (m.entregados, m.intentos_fallidos) == (10, 0)
    assert m.calidad_datos.recuperados_en_reintento == 1
    assert m.calidad_datos.duplicados_eliminados == 0
    assert calcular_alertas(m) == []
