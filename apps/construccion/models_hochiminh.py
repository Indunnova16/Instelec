"""Hochiminh Fase 1 (#171, 2026-07-12) — matriz por torre: Marcación/Replanteo
+ columnas de solo-lectura (Tipo, Cimentación, Predial, Ambiental, % de
avance por bloque, Estado general).

Frente 2 de #171 ("columnas configurables por capítulo"), discovery cerrada
por el cliente el 2026-07-10 con PDF real (San Felipe-Puerta de Oro) + mockup.
Ver `SPRINTS/PLAN_2026-07-12_171_hochiminh_fase1.md` (contrato completo, F2)
y `SPRINTS/DECISIONS_2026-06-28_171-149.md` (discovery original).

Diseño: NO se crea un modelo "matriz" nuevo. La fila de Hochiminh se compone
en la vista a partir de datos que YA existen (TorreConstruccion.tipo/
tipo_cimentacion, torre.obra_civil.avance_ponderado_pct,
torre.montaje_estructura.avance_ponderado_pct, torre.tendido.avance_*_pct,
cruce Predial/Ambiental vía `cruzar_preliminares`). Lo único genuinamente
nuevo son los 8 booleans de Marcación/Replanteo por pata (A/B/C/D), que viven
en `HochiminhMarcacionReplanteo`.
"""
import re
import uuid

from django.db import models

from apps.core.models import BaseModel
from .models import TorreConstruccion


class HochiminhMarcacionReplanteo(BaseModel):
    """Marcación y Replanteo por pata (A/B/C/D) de una torre — únicos campos
    genuinamente nuevos del módulo Hochiminh Fase 1. Todo lo demás que se ve
    en la matriz (Obra Civil %, Montaje %, Tendido %, Predial, Ambiental) se
    reusa vía las properties de abajo o el helper `cruzar_preliminares`.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    torre = models.OneToOneField(
        TorreConstruccion,
        on_delete=models.CASCADE,
        related_name='hochiminh',
    )

    marcacion_a = models.BooleanField('Marcación pata A', default=False)
    marcacion_b = models.BooleanField('Marcación pata B', default=False)
    marcacion_c = models.BooleanField('Marcación pata C', default=False)
    marcacion_d = models.BooleanField('Marcación pata D', default=False)
    replanteo_a = models.BooleanField('Replanteo pata A', default=False)
    replanteo_b = models.BooleanField('Replanteo pata B', default=False)
    replanteo_c = models.BooleanField('Replanteo pata C', default=False)
    replanteo_d = models.BooleanField('Replanteo pata D', default=False)

    class Meta:
        db_table = 'construccion_hochiminh'
        verbose_name = 'Hochiminh — Marcación/Replanteo'
        verbose_name_plural = 'Hochiminh — Marcación/Replanteo'

    def __str__(self):
        return f"Hochiminh {self.torre.numero_display}"

    @property
    def obra_civil_pct(self):
        """Reuso directo de Obra Civil (#74) — sin cálculo propio."""
        oc = getattr(self.torre, 'obra_civil', None)
        return oc.avance_ponderado_pct if oc else 0.0

    @property
    def montaje_pct(self):
        """Reuso directo de Montaje (#76) — sin cálculo propio."""
        m = getattr(self.torre, 'montaje_estructura', None)
        return m.avance_ponderado_pct if m else 0.0

    @property
    def tendido_pct(self):
        """#171 2026-07-10: promedio simple conductor+fibra (decisión Miguel
        aprobada, NO el SUMPRODUCT ponderado que usa el módulo Tendido)."""
        t = getattr(self.torre, 'tendido', None)
        if not t:
            return 0.0
        return round((t.avance_conductor_pct + t.avance_fibra_pct) / 2, 1)

    @property
    def estado_general_pct(self):
        """Promedio simple de los 3 bloques (Obra Civil, Montaje, Tendido)."""
        return round((self.obra_civil_pct + self.montaje_pct + self.tendido_pct) / 3, 1)

    @staticmethod
    def color_semaforo(pct):
        """#171 2026-07-10: umbral LITERAL del cliente — verde>=100,
        amarillo 40-99, rojo<40. NO es el 75/50 que usa el resto de la app
        (Obra Civil/Montaje/Tendido matrices) — centralizado acá (no
        hardcodeado en el template) para que no se confunda con ese otro
        umbral. Caso amarillo no existe en datos reales de prod hoy (único
        proyecto QA está en 100%/0%) — cubierto por unit test de esta función
        pura en tests_hochiminh.py, no por E2E contra prod."""
        if pct >= 100:
            return 'text-green-600'
        if pct >= 40:
            return 'text-amber-600'
        return 'text-red-600'


def cruzar_preliminares(proyecto, torres):
    """#171 (F2, 2026-07-12): cruce TorreConstruccion↔TorreContrato por
    sufijo numérico + contrato_id compartido.

    `TorreConstruccion.numero` (formato real: 'E1'..'E65') y
    `TorreContrato.nombre` (app `ingenieria`, formato real: 'T1'..'T65') no
    calzan por igualdad string — se cruzan extrayendo solo los dígitos de
    cada uno y comparando dentro del mismo contrato (`proyecto.contrato_id`
    == `TorreContrato.contrato_id`). Verificado 65/65 match, 0 duplicados,
    para el proyecto QA real (ver PLAN).

    Fuente de Predial/Ambiental: `apps.preliminares.PredialTorre.liberacion_predial`
    / `apps.preliminares.AmbientalTorre.liberacion_pdo` — cuelgan de
    TorreContrato, consistente con "Actividades Preliminares" del sidebar
    (término literal del cliente).

    Devuelve dict {torre.id: {'predial': bool|None, 'ambiental': bool|None}}.
    `None` significa "sin match o sin dato" — el template lo renderiza como
    '—' (fallback, NO se resuelve acá para mantener el helper de solo-datos).
    """
    from apps.ingenieria.models import TorreContrato

    contrato_id = proyecto.contrato_id
    torres_contrato = {
        re.sub(r'[^0-9]', '', tc.nombre): tc
        for tc in TorreContrato.objects.filter(contrato_id=contrato_id)
        .select_related('predial', 'ambiental')
    }
    resultado = {}
    for t in torres:
        suf = re.sub(r'[^0-9]', '', t.numero or '')
        tc = torres_contrato.get(suf)
        if tc is None:
            resultado[t.id] = {'predial': None, 'ambiental': None}
            continue
        predial = getattr(tc, 'predial', None)
        ambiental = getattr(tc, 'ambiental', None)
        resultado[t.id] = {
            'predial': predial.liberacion_predial if predial else None,
            'ambiental': ambiental.liberacion_pdo if ambiental else None,
        }
    return resultado
