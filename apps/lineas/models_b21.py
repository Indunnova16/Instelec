"""
B2.1 — Segmentación de Vanos por Semestre (S1 / S2 / TA).

Issue: Indunnova16/Instelec#102 (Sofi, mayo 2026).

Modelos nuevos
- `VanoSemestre`: estado del vano dentro de un período de trabajo (S1, S2 o TA).
  Cada Vano puede tener 1–3 registros VanoSemestre (uno por período).
- `SeguimientoVanoSemestre`: registros de avance (porcentaje, horas, observaciones)
  asociados a un VanoSemestre. Histórico/audit trail.

Reglas
- Estado independiente por semestre: marcar vano S1 EJECUTADO no toca S2.
- Cálculo avance por semestre: ejec_<S>/total_<S>. Consolidado: suma agregada.
- Permite vanos exclusivos S1 (ej. LN 805: 246 en S1, 129 en S2) — lo que
  significa que SOLO existen rows VanoSemestre(vano, 'S1') para 117 vanos
  que no se trabajan en S2.
"""
from django.db import models
from django.db.models import Count, Q

from apps.core.models import BaseModel


class VanoSemestreQuerySet(models.QuerySet):
    """Queryset helper para filtros comunes por semestre/línea."""

    def por_linea(self, linea):
        return self.filter(vano__linea=linea)

    def por_semestre(self, semestre):
        if not semestre or semestre.upper() not in (s for s, _ in VanoSemestre.Semestre.choices):
            return self
        return self.filter(semestre=semestre.upper())

    def ejecutados(self):
        return self.filter(estado=VanoSemestre.Estado.EJECUTADO)

    def pendientes(self):
        return self.filter(estado=VanoSemestre.Estado.PENDIENTE)


class VanoSemestreManager(models.Manager):
    def get_queryset(self):
        return VanoSemestreQuerySet(self.model, using=self._db)

    def por_linea(self, linea):
        return self.get_queryset().por_linea(linea)

    def por_semestre(self, semestre):
        return self.get_queryset().por_semestre(semestre)

    def por_vano_y_semestre(self, vano, semestre):
        """
        Contrato del BLUEPRINT — devuelve la VanoSemestre o None.
        Útil para el endpoint de cambio de estado.
        """
        try:
            return self.get_queryset().get(vano=vano, semestre=semestre.upper())
        except self.model.DoesNotExist:
            return None

    def avance_consolidado(self, linea):
        """
        Contrato del BLUEPRINT — devuelve dict con avance por semestre y total.

        Returns:
            {
                's1':    {'total': int, 'ejecutados': int, 'porcentaje': float},
                's2':    {...},
                'ta':    {...},
                'total': {'total': int, 'ejecutados': int, 'porcentaje': float},
            }
        """
        qs = self.por_linea(linea)

        def _bucket(sem_code):
            sub = qs.filter(semestre=sem_code)
            total = sub.count()
            ejec = sub.filter(estado=VanoSemestre.Estado.EJECUTADO).count()
            pct = round((ejec / total) * 100, 1) if total else 0.0
            return {'total': total, 'ejecutados': ejec, 'porcentaje': pct}

        s1 = _bucket(VanoSemestre.Semestre.S1)
        s2 = _bucket(VanoSemestre.Semestre.S2)
        ta = _bucket(VanoSemestre.Semestre.TA)
        total_total = s1['total'] + s2['total'] + ta['total']
        total_ejec = s1['ejecutados'] + s2['ejecutados'] + ta['ejecutados']
        consolidado = {
            'total': total_total,
            'ejecutados': total_ejec,
            'porcentaje': round((total_ejec / total_total) * 100, 1) if total_total else 0.0,
        }
        return {'s1': s1, 's2': s2, 'ta': ta, 'total': consolidado}


class VanoSemestre(BaseModel):
    """
    Estado de un Vano dentro de un Semestre (o "Todo el Año").

    Un Vano puede aparecer en S1, S2 o TA (o varias combinaciones). El estado
    se rastrea de forma independiente por período.
    """

    class Semestre(models.TextChoices):
        S1 = 'S1', 'Semestre 1 (Ene–Jun)'
        S2 = 'S2', 'Semestre 2 (Jul–Dic)'
        TA = 'TA', 'Todo el año'

    class Estado(models.TextChoices):
        PENDIENTE = 'pendiente', 'Pendiente'
        EJECUTADO = 'ejecutado', 'Ejecutado'
        SIN_PERMISO = 'sin_permiso', 'Sin Permiso'
        NO_EJECUTADO = 'no_ejecutado', 'No Ejecutado'
        EN_ESPERA = 'en_espera', 'Parcial'

    vano = models.ForeignKey(
        'lineas.Vano',
        on_delete=models.CASCADE,
        related_name='semestres',
        verbose_name='Vano',
    )
    semestre = models.CharField(
        'Semestre',
        max_length=2,
        choices=Semestre.choices,
        db_index=True,
    )
    estado = models.CharField(
        'Estado',
        max_length=20,
        choices=Estado.choices,
        default=Estado.PENDIENTE,
        db_index=True,
    )
    fecha_inicio = models.DateField(
        'Fecha inicio del período',
        null=True,
        blank=True,
        help_text='Inicio del trabajo en este semestre (opcional).',
    )
    fecha_fin = models.DateField(
        'Fecha fin del período',
        null=True,
        blank=True,
        help_text='Fin previsto del trabajo en este semestre (opcional).',
    )
    observaciones = models.TextField(
        'Observaciones',
        blank=True,
    )
    creado_por = models.ForeignKey(
        'usuarios.Usuario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vano_semestres_creados',
        verbose_name='Creado por',
    )
    actualizado_por = models.ForeignKey(
        'usuarios.Usuario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vano_semestres_actualizados',
        verbose_name='Última actualización por',
    )

    objects = VanoSemestreManager()

    class Meta:
        db_table = 'vano_semestres'
        verbose_name = 'Vano · Semestre'
        verbose_name_plural = 'Vanos · Semestres'
        unique_together = [('vano', 'semestre')]
        ordering = ['vano__linea__codigo', 'vano__numero', 'semestre']
        indexes = [
            models.Index(fields=['semestre', 'estado']),
        ]

    def __str__(self):
        return f"Vano {self.vano.numero} ({self.vano.linea.codigo}) · {self.semestre}"

    def marcar(self, nuevo_estado, usuario=None, observaciones=''):
        """
        Cambia el estado del Vano en ESTE semestre exclusivamente.
        No afecta filas de otros semestres del mismo Vano.
        Devuelve self refrescado.
        """
        if nuevo_estado not in dict(self.Estado.choices):
            raise ValueError(f"Estado inválido: {nuevo_estado!r}")
        self.estado = nuevo_estado
        if usuario and not getattr(usuario, '_anon', False):
            self.actualizado_por = usuario
        if observaciones:
            self.observaciones = observaciones
        self.save(update_fields=['estado', 'actualizado_por', 'observaciones', 'updated_at'])
        return self


class SeguimientoVanoSemestre(BaseModel):
    """
    Registro de seguimiento granular por VanoSemestre.
    Histórico de avances (no destruye, append-only).
    """
    vano_semestre = models.ForeignKey(
        VanoSemestre,
        on_delete=models.CASCADE,
        related_name='seguimientos',
        verbose_name='Vano · Semestre',
    )
    fecha = models.DateField(
        'Fecha de seguimiento',
    )
    porcentaje_avance = models.FloatField(
        'Porcentaje avance (0–100)',
        default=0,
    )
    horas = models.FloatField(
        'Horas trabajadas',
        default=0,
    )
    observaciones = models.TextField(
        'Observaciones',
        blank=True,
    )
    registrado_por = models.ForeignKey(
        'usuarios.Usuario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='seguimientos_vano_semestre',
        verbose_name='Registrado por',
    )

    class Meta:
        db_table = 'seguimientos_vano_semestre'
        verbose_name = 'Seguimiento Vano · Semestre'
        verbose_name_plural = 'Seguimientos Vanos · Semestres'
        ordering = ['-fecha', '-created_at']
        indexes = [
            models.Index(fields=['vano_semestre', '-fecha']),
        ]

    def __str__(self):
        return f"{self.vano_semestre} · {self.fecha} · {self.porcentaje_avance}%"

    def save(self, *args, **kwargs):
        # Validar rango [0,100]
        if self.porcentaje_avance is not None:
            self.porcentaje_avance = max(0.0, min(100.0, float(self.porcentaje_avance)))
        if self.horas is not None and self.horas < 0:
            self.horas = 0
        super().save(*args, **kwargs)


def filter_vanos_by_semestre(vano_queryset, semestre):
    """
    Helper utility exportado para que vistas existentes (p. ej.
    `apps.campo.views.RegistroAvanceCreateView`) puedan filtrar el grid de
    vanos por semestre sin tocar models_base.py.

    Importable como:
        from apps.lineas.views_b21 import filter_vanos_by_semestre

    Args:
        vano_queryset: QuerySet de Vano.
        semestre: 'S1' | 'S2' | 'TA' | None.

    Returns: queryset filtrado o queryset original si semestre vacío/None.
    """
    if not semestre:
        return vano_queryset
    sem = semestre.upper()
    if sem not in dict(VanoSemestre.Semestre.choices):
        return vano_queryset
    return vano_queryset.filter(semestres__semestre=sem).distinct()
