"""Fase 2: la única parte del sistema que habla con un modelo de lenguaje.

Todo lo específico del proveedor (OpenAI) vive en este archivo. Si mañana
se cambia a otro proveedor, solo se reescribe `generar_reporte()`.
"""

import json
import time

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

from lastmile_report.metrics import Alerta, MetricasDia
from lastmile_report.report import INDICADORES, UMBRALES, Reporte, verificar

MODELO_DEFECTO = "gpt-4.1-mini"

# USD por millón de tokens (entrada, salida). Verificar en openai.com/api/pricing.
PRECIOS = {
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5-nano": (0.05, 0.40),
}

# Los prompts se versionan: cada versión se evalúa y se compara con la anterior.
PROMPTS = {
    "v1": (
        "Eres analista de operaciones de última milla. Con los datos del día de una "
        "estación de entrega, escribe el reporte diario en español.\n"
        "Incluye estos indicadores: {indicadores}.\n"
        "Incluye las alertas que vienen en los datos y da recomendaciones."
    ),
}


class Resultado(BaseModel):
    reporte: Reporte
    errores: list[str]  # salida de verificar(); vacío = reporte fiel a los datos
    modelo: str
    prompt: str
    tokens_entrada: int
    tokens_salida: int
    costo_usd: float | None
    segundos: float


def generar_reporte(
    m: MetricasDia,
    alertas: list[Alerta],
    modelo: str = MODELO_DEFECTO,
    prompt: str = "v1",
) -> Resultado:
    """Envía al modelo SOLO cifras ya calculadas y recibe un Reporte validado."""
    load_dotenv()  # lee OPENAI_API_KEY del archivo .env
    cliente = OpenAI()
    datos = {
        "metricas": m.model_dump(),
        "alertas": [a.model_dump() for a in alertas],
        "umbrales": UMBRALES,
    }

    inicio = time.perf_counter()
    respuesta = cliente.chat.completions.parse(
        model=modelo,
        messages=[
            {"role": "system", "content": PROMPTS[prompt].format(indicadores=", ".join(INDICADORES))},
            {"role": "user", "content": json.dumps(datos, ensure_ascii=False)},
        ],
        response_format=Reporte,  # el SDK obliga al modelo a cumplir el esquema
    )
    segundos = time.perf_counter() - inicio

    reporte = respuesta.choices[0].message.parsed
    if reporte is None:
        raise RuntimeError("El modelo no devolvió un reporte válido")

    entrada, salida = respuesta.usage.prompt_tokens, respuesta.usage.completion_tokens
    precio = PRECIOS.get(modelo)
    return Resultado(
        reporte=reporte,
        errores=verificar(reporte, m, alertas),
        modelo=modelo,
        prompt=prompt,
        tokens_entrada=entrada,
        tokens_salida=salida,
        costo_usd=round((entrada * precio[0] + salida * precio[1]) / 1e6, 6) if precio else None,
        segundos=round(segundos, 2),
    )
