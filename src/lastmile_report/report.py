"""Fase 2: el contrato de SALIDA del modelo y su verificación.

- `Reporte` es el esquema que el modelo está obligado a llenar.
- `verificar()` comprueba, con código, que el modelo no inventó ni cambió
  ninguna cifra. Es la base del "número de calidad" del proyecto.
"""

import re
from typing import Literal

from pydantic import BaseModel, Field

from lastmile_report import metrics
from lastmile_report.metrics import Alerta, MetricasDia

# Indicadores que todo reporte debe traer, tal cual salen de MetricasDia.
INDICADORES = [
    "paquetes",
    "entregados",
    "intentos_fallidos",
    "tasa_entrega_pct",
    "tasa_fallidos_pct",
    "rutas",
    "ocupacion_promedio_pct",
]


class Indicador(BaseModel):
    clave: str = Field(description="Nombre exacto del indicador en los datos")
    valor: float = Field(description="Valor copiado de los datos, sin modificar")
    lectura: str = Field(description="Una frase corta que interpreta el valor")


class AlertaReporte(BaseModel):
    codigo: str
    severidad: Literal["alta", "media"]
    entidad: str
    mensaje: str = Field(description="Qué pasó y por qué importa, en una o dos frases")


class Reporte(BaseModel):
    resumen: str = Field(description="Tres o cuatro frases para el jefe de operación")
    indicadores: list[Indicador]
    alertas: list[AlertaReporte]
    recomendaciones: list[str]


# ---------- Verificación ----------

UMBRALES = {
    "umbral_fallidos_pct": metrics.UMBRAL_FALLIDOS_PCT,
    "umbral_ruta_fallidos_pct": metrics.UMBRAL_RUTA_FALLIDOS_PCT,
    "min_fallidos_ruta": metrics.MIN_FALLIDOS_RUTA,
    "factor_sobre_historico": metrics.FACTOR_SOBRE_HISTORICO,
}


def _numeros_de(objeto) -> set[float]:
    """Todos los números que aparecen en una estructura de datos."""
    if isinstance(objeto, bool):
        return set()
    if isinstance(objeto, (int, float)):
        return {float(objeto)}
    if isinstance(objeto, dict):
        return set().union(*(_numeros_de(v) for v in objeto.values())) if objeto else set()
    if isinstance(objeto, list):
        return set().union(*(_numeros_de(v) for v in objeto)) if objeto else set()
    return set()


def _interpretaciones(token: str) -> set[float]:
    """'9.911' puede ser 9911 o 9.911; '0,49' es 0.49. Aceptamos cualquiera."""
    token = token.strip(".,")
    candidatos = {token.replace(",", "."), token.replace(".", "").replace(",", "."), token.replace(",", "")}
    valores = set()
    for c in candidatos:
        try:
            valores.add(float(c))
        except ValueError:
            pass
    return valores


def cifras_no_respaldadas(texto: str, permitidos: set[float], ignorar: list[str]) -> list[str]:
    """Números escritos en el texto que no existen en los datos calculados."""
    for identificador in sorted(ignorar, key=len, reverse=True):  # ids de ruta, zona, fecha...
        texto = texto.replace(identificador, " ")
    malas = []
    for token in re.findall(r"\d[\d.,]*", texto):
        if not any(abs(v - p) < 0.005 for v in _interpretaciones(token) for p in permitidos):
            malas.append(token.strip(".,"))
    return malas


def verificar(reporte: Reporte, m: MetricasDia, alertas: list[Alerta]) -> list[str]:
    """Devuelve la lista de errores del reporte. Lista vacía = reporte fiel."""
    errores = []
    datos = m.model_dump()

    # 1. Indicadores: todos presentes y con el valor exacto.
    vistos = {i.clave: i.valor for i in reporte.indicadores}
    for clave in INDICADORES:
        if clave not in vistos:
            errores.append(f"indicador_faltante:{clave}")
        elif abs(vistos[clave] - datos[clave]) > 0.005:
            errores.append(f"indicador_incorrecto:{clave}={vistos[clave]} (real {datos[clave]})")
    for clave in vistos.keys() - set(INDICADORES):
        errores.append(f"indicador_no_pedido:{clave}")

    # 2. Alertas: exactamente las que calculó el código, ni más ni menos.
    esperadas = {(a.codigo, a.entidad) for a in alertas}
    escritas = {(a.codigo, a.entidad) for a in reporte.alertas}
    errores += [f"alerta_omitida:{c}:{e}" for c, e in sorted(esperadas - escritas)]
    errores += [f"alerta_inventada:{c}:{e}" for c, e in sorted(escritas - esperadas)]

    # 3. Texto libre: cada cifra mencionada debe existir en los datos.
    permitidos = _numeros_de(datos) | _numeros_de([a.model_dump() for a in alertas])
    permitidos |= _numeros_de(UMBRALES)
    # La fecha escrita en palabras ("28 de julio de 2018") y el 100% como referencia no son cálculos.
    permitidos |= {float(parte) for parte in m.date.split("-")} | {100.0}
    ignorar = [m.date, m.station_code] + [r.route_id for r in m.peores_rutas + m.rutas_criticas]
    ignorar += [z.zone_id for z in m.peores_zonas]
    # El modelo a veces abrevia un id ("ruta 76f22159"): sus fragmentos no son cifras.
    ignorar += [trozo for ident in list(ignorar) for trozo in re.split(r"[_-]", ident) if len(trozo) >= 8]
    texto = " ".join(
        [reporte.resumen, *reporte.recomendaciones]
        + [i.lectura for i in reporte.indicadores]
        + [a.mensaje for a in reporte.alertas]
    )
    errores += [f"cifra_no_respaldada:{c}" for c in cifras_no_respaldadas(texto, permitidos, ignorar)]
    return errores
