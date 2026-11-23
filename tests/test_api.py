"""Tests de la API. Usan `solo_metricas`, así que no llaman al modelo."""

from fastapi.testclient import TestClient

from lastmile_report.api import app
from lastmile_report.evals import CASOS, cargar_casos

cliente = TestClient(app)


def test_salud_y_pagina():
    assert cliente.get("/salud").json() == {"estado": "ok"}
    assert "Reporte diario" in cliente.get("/").text
    assert len(cliente.get("/casos").json()) == 50


def test_reporte_de_un_caso():
    caso = cargar_casos()[20]  # un día malo
    r = cliente.post(f"/reporte/caso/{caso['id']}", params={"solo_metricas": True})
    assert r.status_code == 200
    assert r.json()["metricas"]["paquetes"] == caso["esperado"]["paquetes"]
    obtenidas = sorted(f"{a['codigo']}:{a['entidad']}" for a in r.json()["alertas_calculadas"])
    assert obtenidas == caso["esperado"]["alertas"]


def test_subir_archivo_e_historico():
    caso = cargar_casos()[0]
    contenido = (CASOS / caso["archivo"]).read_bytes()
    r = cliente.post(
        "/reporte",
        files={"archivo": ("dia.csv", contenido, "text/csv")},
        data={"historico": "0.5, 0.6, 0.4", "solo_metricas": "true"},
    )
    assert r.status_code == 200
    assert r.json()["metricas"]["paquetes"] == caso["esperado"]["paquetes"]


def test_archivo_invalido_devuelve_mensaje_claro():
    invalido = next(c for c in cargar_casos() if c["tipo"] == "invalido")
    r = cliente.post(f"/reporte/caso/{invalido['id']}", params={"solo_metricas": True})
    assert r.status_code == 422
    assert invalido["esperado"]["error"] in r.json()["detail"]
    assert cliente.post("/reporte/caso/no_existe").status_code == 404
