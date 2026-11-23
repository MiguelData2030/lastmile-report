"""API y página web local, para usar el sistema desde el navegador.

Uso:  uv run lastmile-api     y luego abrir  http://localhost:8000

Corre en tu propio equipo: no necesita GitHub ni ningún servicio de despliegue.
La página está en web.py; aquí solo viven los endpoints.
"""

import json
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from lastmile_report.evals import CASOS, RESULTADOS, cargar_casos
from lastmile_report.llm import (
    MODELO_DEFECTO,
    PRECIOS,
    PROMPT_DEFECTO,
    PROMPTS,
    REINTENTOS_DEFECTO,
    generar_reporte,
)
from lastmile_report.metrics import calcular_alertas, calcular_metricas, cargar_dia
from lastmile_report.web import PAGINA

app = FastAPI(title="Reporte diario de última milla")


def _responder(
    archivo: Path,
    historico: list[float],
    solo_metricas: bool,
    modelo: str | None = None,
    prompt: str | None = None,
    reintentos: int | None = None,
) -> dict:
    modelo, prompt = modelo or MODELO_DEFECTO, prompt or PROMPT_DEFECTO
    reintentos = REINTENTOS_DEFECTO if reintentos is None else reintentos
    if modelo not in PRECIOS or prompt not in PROMPTS or not 0 <= reintentos <= 3:
        raise HTTPException(status_code=422, detail="Modelo, prompt o reintentos no válidos")
    try:
        metricas = calcular_metricas(cargar_dia(archivo))
    except ValueError as e:  # archivo inválido: se le explica a la persona, no se llama al modelo
        raise HTTPException(status_code=422, detail=str(e)) from e
    alertas = calcular_alertas(metricas, historico)
    salida = {
        "metricas": metricas.model_dump(),
        "alertas_calculadas": [a.model_dump() for a in alertas],
        "historico": historico,
    }
    if not solo_metricas:
        salida |= generar_reporte(metricas, alertas, modelo, prompt, reintentos).model_dump()
    return salida


def _tasas(texto: str) -> list[float]:
    try:
        return [float(x) for x in texto.replace(";", ",").split(",") if x.strip()]
    except ValueError as e:
        raise HTTPException(status_code=422, detail="El histórico debe ser una lista de números") from e


@app.get("/salud")
def salud() -> dict:
    return {"estado": "ok"}


@app.get("/opciones")
def opciones() -> dict:
    """Modelos y prompts disponibles, para experimentar desde la página."""
    return {
        "modelos": list(PRECIOS),
        "prompts": list(PROMPTS),
        "defecto": {"modelo": MODELO_DEFECTO, "prompt": PROMPT_DEFECTO, "reintentos": REINTENTOS_DEFECTO},
    }


@app.get("/casos")
def casos() -> list[dict]:
    """Los 50 casos de ejemplo, para probar sin tener un archivo propio."""
    return [
        {"id": c["id"], "tipo": c["tipo"], "origen": c["origen"], "suciedad": c["suciedad"]}
        for c in cargar_casos()
    ]


@app.get("/evals")
def evals() -> list[dict]:
    """Resumen de cada versión evaluada sobre los 50 casos (evals/resultados/v*.json)."""
    filas = [
        json.loads(f.read_text(encoding="utf-8"))["resumen"] | {"archivo": f.name}
        for f in sorted(RESULTADOS.glob("v*.json"))
    ]
    return sorted(filas, key=lambda r: (r["aciertos_pct"], -r["costo_usd_por_reporte"]))


@app.post("/reporte/caso/{caso_id}")
def reporte_de_caso(
    caso_id: str,
    solo_metricas: bool = False,
    modelo: str | None = None,
    prompt: str | None = None,
    reintentos: int | None = None,
) -> dict:
    caso = next((c for c in cargar_casos() if c["id"] == caso_id), None)
    if caso is None:
        raise HTTPException(status_code=404, detail="Ese caso no existe")
    return _responder(
        CASOS / caso["archivo"], caso["historico_tasas"], solo_metricas, modelo, prompt, reintentos
    )


@app.post("/reporte")
def reporte_de_archivo(
    archivo: UploadFile,
    historico: Annotated[str, Form()] = "",  # % de fallidos de días anteriores, separados por coma
    solo_metricas: Annotated[bool, Form()] = False,
    modelo: Annotated[str | None, Form()] = None,
    prompt: Annotated[str | None, Form()] = None,
    reintentos: Annotated[int | None, Form()] = None,
) -> dict:
    sufijo = Path(archivo.filename or "dia.csv").suffix or ".csv"
    with tempfile.TemporaryDirectory() as carpeta:
        destino = Path(carpeta) / f"dia{sufijo}"
        destino.write_bytes(archivo.file.read())
        return _responder(destino, _tasas(historico), solo_metricas, modelo, prompt, reintentos)


@app.get("/", response_class=HTMLResponse)
def pagina() -> str:
    return PAGINA


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
