"""Tests del verificador. No llaman al modelo: no cuestan dinero y corren en CI."""

import pandas as pd
from test_metrics import fila

from lastmile_report.metrics import calcular_alertas, calcular_metricas
from lastmile_report.report import INDICADORES, AlertaReporte, Indicador, Reporte, verificar


def caso():
    """20 paquetes, 6 fallidos (30%): dispara FALLIDOS_ALTOS y RUTA_CRITICA."""
    filas = [fila(f"P{i}") for i in range(14)]
    filas += [fila(f"F{i}", status="DELIVERY_ATTEMPTED") for i in range(6)]
    m = calcular_metricas(pd.DataFrame(filas))
    return m, calcular_alertas(m)


def reporte_fiel(m, alertas) -> Reporte:
    datos = m.model_dump()
    return Reporte(
        resumen=f"El 1 de agosto de 2018 la estación {m.station_code} movió {m.paquetes} paquetes con 30.0% de fallidos.",
        indicadores=[Indicador(clave=c, valor=datos[c], lectura="ok") for c in INDICADORES],
        alertas=[
            AlertaReporte(codigo=a.codigo, severidad=a.severidad, entidad=a.entidad, mensaje="Revisar.")
            for a in alertas
        ],
        recomendaciones=["Revisar la ruta R1."],
    )


def test_reporte_fiel_no_tiene_errores():
    m, alertas = caso()
    assert verificar(reporte_fiel(m, alertas), m, alertas) == []


def test_detecta_indicador_cambiado_y_faltante():
    m, alertas = caso()
    r = reporte_fiel(m, alertas)
    r.indicadores[0].valor += 1
    r.indicadores.pop()
    errores = verificar(r, m, alertas)
    assert any(e.startswith("indicador_incorrecto:paquetes") for e in errores)
    assert "indicador_faltante:ocupacion_promedio_pct" in errores


def test_detecta_alerta_omitida_e_inventada():
    m, alertas = caso()
    r = reporte_fiel(m, alertas)
    r.alertas[0] = AlertaReporte(codigo="CLIMA", severidad="media", entidad="estacion", mensaje="Llovió.")
    errores = verificar(r, m, alertas)
    assert "alerta_inventada:CLIMA:estacion" in errores
    assert any(e.startswith("alerta_omitida:") for e in errores)


def test_detecta_cifra_inventada_en_el_texto():
    m, alertas = caso()
    r = reporte_fiel(m, alertas)
    r.resumen += " Esto es 12 puntos peor que ayer y equivale a 45 paquetes por hora."
    errores = verificar(r, m, alertas)
    # Ni 12 ni 45 existen en las métricas: el "modelo" los calculó o los inventó.
    assert errores == ["cifra_no_respaldada:12", "cifra_no_respaldada:45"]


def test_acepta_formato_espanol_de_numeros():
    filas = [fila(f"P{i}") for i in range(1234)] + [fila("F", status="DELIVERY_ATTEMPTED")]
    m = calcular_metricas(pd.DataFrame(filas))  # 1235 paquetes, 0.08% fallidos
    r = reporte_fiel(m, [])
    r.resumen = "Se movieron 1.235 paquetes con 0,08% de fallidos."
    assert verificar(r, m, []) == []


def test_id_de_ruta_abreviado_no_es_cifra():
    filas = [fila(f"P{i}", route_id="RouteID_76f22159-a7b6-43d5-b424-fe21033d7784") for i in range(14)]
    filas += [
        fila(f"F{i}", route_id="RouteID_76f22159-a7b6-43d5-b424-fe21033d7784", status="DELIVERY_ATTEMPTED")
        for i in range(6)
    ]
    m = calcular_metricas(pd.DataFrame(filas))
    alertas = calcular_alertas(m)
    r = reporte_fiel(m, alertas)
    r.recomendaciones = ["Revisar la ruta ID 76f22159."]
    assert verificar(r, m, alertas) == []
