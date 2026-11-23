"""Corre la parte de CÓDIGO de los 50 casos en cada push (sin modelo, gratis).

Si alguien cambia metrics.py y rompe un cálculo o una alerta, CI se pone en rojo.
"""

import pytest

from lastmile_report.evals import cargar_casos, evaluar_codigo

CASOS = cargar_casos()


def test_son_50_casos():
    assert len(CASOS) == 50


@pytest.mark.parametrize("caso", CASOS, ids=[c["id"] for c in CASOS])
def test_codigo_coincide_con_lo_esperado(caso):
    r, _, _ = evaluar_codigo(caso)
    assert r["calculo_ok"], r.get("diferencias")
    assert r["alertas_ok"], (r.get("alertas_obtenidas"), caso["esperado"].get("alertas"))
