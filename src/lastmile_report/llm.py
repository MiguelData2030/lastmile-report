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
PROMPT_DEFECTO = "v2"
REINTENTOS_DEFECTO = 1

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
    # v1: línea base, deliberadamente simple.
    "v1": (
        "Eres analista de operaciones de última milla. Con los datos del día de una "
        "estación de entrega, escribe el reporte diario en español.\n"
        "Incluye estos indicadores: {indicadores}.\n"
        "Incluye las alertas que vienen en los datos y da recomendaciones."
    ),
    # v2 (mejora 1): reglas explícitas sobre cifras, nacidas de los fallos reales de v1
    # (metas inventadas "60-70%", redondeos "superior al 99%", cálculos "3.08 puntos").
    "v2": (
        "Eres analista de operaciones de última milla. Con los datos del día de una "
        "estación de entrega, escribe el reporte diario en español.\n\n"
        "Todas las cifras ya fueron calculadas por un sistema. Tu trabajo es redactar, no calcular.\n\n"
        "Reglas sobre cifras (un verificador automático rechaza el reporte si se incumplen):\n"
        "1. Usa solo números que aparezcan literalmente en los datos y cópialos exactos, con todos "
        "sus decimales. No redondees ni aproximes: nada de 'casi', 'cerca de', 'más de', 'superior al'.\n"
        "2. No hagas ninguna operación: ni sumas, restas, porcentajes, promedios, diferencias en "
        "puntos, ni 'X veces'. Si quieres comparar dos cifras, cita ambas tal cual y describe la "
        "relación solo con palabras (mayor, menor, muy por encima).\n"
        "3. No propongas metas, rangos ni umbrales numéricos propios. Los únicos umbrales válidos "
        "son los de 'umbrales'. Las recomendaciones deben ser acciones concretas, sin números nuevos.\n"
        "4. Escribe los identificadores de ruta y zona completos, sin abreviar.\n\n"
        "Estructura:\n"
        "- indicadores: exactamente estos, con la clave idéntica y el valor copiado: {indicadores}.\n"
        "- alertas: exactamente las de 'alertas', con el mismo codigo, severidad y entidad. "
        "Si la lista viene vacía, devuelve una lista vacía.\n"
        "- resumen: tres o cuatro frases para el jefe de operación.\n"
        "- recomendaciones: de dos a cuatro, ligadas a las alertas o a las peores rutas y zonas."
    ),
}

CORRECCION = (
    "Un verificador automático encontró estos errores en tu reporte:\n{errores}\n\n"
    "Reescribe el reporte completo corrigiéndolos. Para cada 'cifra_no_respaldada', elimina ese "
    "número o reemplázalo por una cifra copiada exacta de los datos. No cambies lo que ya estaba bien."
)


class Resultado(BaseModel):
    reporte: Reporte
    errores: list[str]  # salida de verificar(); vacío = reporte fiel a los datos
    modelo: str
    prompt: str
    intentos: int
    tokens_entrada: int
    tokens_salida: int
    costo_usd: float | None
    segundos: float


def generar_reporte(
    m: MetricasDia,
    alertas: list[Alerta],
    modelo: str = MODELO_DEFECTO,
    prompt: str = PROMPT_DEFECTO,
    reintentos: int = REINTENTOS_DEFECTO,
) -> Resultado:
    """Envía al modelo SOLO cifras ya calculadas y recibe un Reporte validado.

    Mejora 2: si el verificador encuentra errores, se le devuelven al modelo
    para que corrija, hasta `reintentos` veces.
    """
    load_dotenv()  # lee OPENAI_API_KEY del archivo .env
    cliente = OpenAI()
    datos = {
        "metricas": m.model_dump(),
        "alertas": [a.model_dump() for a in alertas],
        "umbrales": UMBRALES,
    }
    mensajes = [
        {"role": "system", "content": PROMPTS[prompt].format(indicadores=", ".join(INDICADORES))},
        {"role": "user", "content": json.dumps(datos, ensure_ascii=False)},
    ]

    entrada = salida = intentos = 0
    inicio = time.perf_counter()
    while True:
        respuesta = cliente.chat.completions.parse(
            model=modelo,
            messages=mensajes,
            response_format=Reporte,  # el SDK obliga al modelo a cumplir el esquema
        )
        intentos += 1
        entrada += respuesta.usage.prompt_tokens
        salida += respuesta.usage.completion_tokens
        reporte = respuesta.choices[0].message.parsed
        if reporte is None:
            raise RuntimeError("El modelo no devolvió un reporte válido")
        errores = verificar(reporte, m, alertas)
        if not errores or intentos > reintentos:
            break
        mensajes += [
            {"role": "assistant", "content": reporte.model_dump_json()},
            {"role": "user", "content": CORRECCION.format(errores="\n".join(f"- {e}" for e in errores))},
        ]
    segundos = time.perf_counter() - inicio

    precio = PRECIOS.get(modelo)
    return Resultado(
        reporte=reporte,
        errores=errores,
        modelo=modelo,
        prompt=prompt,
        intentos=intentos,
        tokens_entrada=entrada,
        tokens_salida=salida,
        costo_usd=round((entrada * precio[0] + salida * precio[1]) / 1e6, 6) if precio else None,
        segundos=round(segundos, 2),
    )
