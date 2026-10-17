"""Reglas de anuncios de VIREVO.

Es una función pura (sin base de datos, sin archivos, sin red) a propósito:
así es fácil de probar y de cambiar cuando validemos qué reglas funcionan.
"""
import math
import os
from dataclasses import dataclass

MAX_FREE_SECONDS = 15 * 60   # tope del plan gratis: 15 minutos
SECONDS_PER_AD_BLOCK = 5 * 60  # 1 anuncio por cada 5 minutos de video
MAX_ADS = 3                  # nunca más de 3 anuncios
# Duración de cada anuncio. En desarrollo puedes acortarla con la variable de entorno
# VIREVO_AD_SECONDS (por ejemplo 3) para no esperar 20 s en cada prueba.
AD_SECONDS = int(os.environ.get("VIREVO_AD_SECONDS") or 20)


@dataclass(frozen=True)
class AdPlan:
    allowed: bool          # ¿puede procesarse gratis?
    ads_required: int      # cuántos anuncios debe ver
    seconds_per_ad: int    # duración de cada anuncio
    total_ad_seconds: int  # tiempo total viendo anuncios
    reason: str            # mensaje para mostrar al usuario


def calculate_ad_plan(duration_seconds: float) -> AdPlan:
    if duration_seconds <= 0:
        return AdPlan(False, 0, 0, 0, "No pudimos leer la duración del video.")

    if duration_seconds > MAX_FREE_SECONDS:
        minutes = MAX_FREE_SECONDS // 60
        return AdPlan(
            False, 0, 0, 0,
            f"El plan gratis admite videos de hasta {minutes} minutos.",
        )

    ads = min(MAX_ADS, max(1, math.ceil(duration_seconds / SECONDS_PER_AD_BLOCK)))
    return AdPlan(True, ads, AD_SECONDS, ads * AD_SECONDS, "OK")
