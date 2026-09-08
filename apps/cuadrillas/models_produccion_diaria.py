"""Dominio compartido de Producción Diaria (#252).

Las pantallas de registro, análisis e historial viven en sub-features
independientes. Este módulo conserva únicamente sus contratos persistentes.
"""

from decimal import Decimal

from django.db import models

from apps.core.models import BaseModel


class ProduccionDiaria(BaseModel):
    """Cabecera de la producción reportada contra una programación semanal."""

    class Calidad(models.TextChoices):
        BUENA = "BUENA", "Buena"
        NORMAL = "NORMAL", "Normal"
        MALA = "MALA", "Mala"

    programacion = models.ForeignKey(
        "cuadrillas.ProgramacionSemanalCuadrilla",
        on_delete=models.PROTECT,
        related_name="producciones_diarias",
        verbose_name="Programación semanal",
    )
    fecha = models.DateField("Fecha de producción")
    calidad_trabajo = models.CharField(
        "Calidad del trabajo",
        max_length=10,
        choices=Calidad.choices,
        default=Calidad.NORMAL,
    )
    observaciones = models.TextField("Observaciones", blank=True)
    registrado_por = models.ForeignKey(
        "usuarios.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="producciones_diarias_registradas",
        verbose_name="Registrado por",
    )

    class Meta:
        db_table = "produccion_diaria"
        verbose_name = "Producción diaria"
        verbose_name_plural = "Producciones diarias"
        ordering = ["-fecha", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["programacion", "fecha"],
                name="produccion_diaria_programacion_fecha_unica",
            ),
        ]
        indexes = [models.Index(fields=["fecha"])]

    def __str__(self):
        return f"{self.programacion} — {self.fecha:%Y-%m-%d}"


class RegistroPersonalProduccion(BaseModel):
    """Horas y asistencia de una persona en un reporte diario."""

    class MotivoAusencia(models.TextChoices):
        NO_INFORMO = "NO_INFORMO", "No informó"
        ENFERMEDAD = "ENFERMEDAD", "Enfermedad"
        PERMISO = "PERMISO", "Permiso"
        CAMBIO_ORDEN = "CAMBIO_ORDEN", "Cambio de orden"
        OTRO = "OTRO", "Otro"

    produccion = models.ForeignKey(
        ProduccionDiaria,
        on_delete=models.CASCADE,
        related_name="registros_personal",
        verbose_name="Producción diaria",
    )
    personal = models.ForeignKey(
        "cuadrillas.PersonalCuadrilla",
        on_delete=models.PROTECT,
        related_name="registros_produccion_diaria",
        verbose_name="Personal",
    )
    horas_trabajadas = models.DecimalField(
        "Horas trabajadas", max_digits=4, decimal_places=2, default=0
    )
    motivo_ausencia = models.CharField(
        "Motivo de ausencia",
        max_length=20,
        choices=MotivoAusencia.choices,
        blank=True,
    )
    observacion = models.TextField("Observación", blank=True)

    class Meta:
        db_table = "registro_personal_produccion"
        verbose_name = "Registro de personal en producción"
        verbose_name_plural = "Registros de personal en producción"
        constraints = [
            models.UniqueConstraint(
                fields=["produccion", "personal"], name="registro_personal_produccion_unico"
            ),
        ]


class ActividadProduccion(BaseModel):
    """Avance real de una actividad en un reporte diario."""

    produccion = models.ForeignKey(
        ProduccionDiaria,
        on_delete=models.CASCADE,
        related_name="actividades",
        verbose_name="Producción diaria",
    )
    descripcion = models.CharField("Actividad", max_length=255)
    avance_pct = models.DecimalField(
        "Avance (%)", max_digits=5, decimal_places=2, default=Decimal("0")
    )
    observacion = models.TextField("Observación", blank=True)

    class Meta:
        db_table = "actividad_produccion"
        verbose_name = "Actividad de producción"
        verbose_name_plural = "Actividades de producción"


class NovedadProduccion(BaseModel):
    """Novedad operativa, con adjunto administrado por el storage configurado."""

    class Tipo(models.TextChoices):
        LLUVIA = "LLUVIA", "Lluvia"
        ACCIDENTE_LESION = "ACCIDENTE_LESION", "Accidente/Lesión"
        CAMBIO_ORDEN = "CAMBIO_ORDEN", "Cambio orden"
        MATERIAL_FALTANTE = "MATERIAL_FALTANTE", "Material faltante"
        HERRAMIENTA_DANADA = "HERRAMIENTA_DANADA", "Herramienta dañada"
        OTRO = "OTRO", "Otro"

    produccion = models.ForeignKey(
        ProduccionDiaria,
        on_delete=models.CASCADE,
        related_name="novedades",
        verbose_name="Producción diaria",
    )
    tipo = models.CharField("Tipo de novedad", max_length=25, choices=Tipo.choices)
    descripcion = models.TextField("Descripción")
    foto = models.FileField("Foto", upload_to="produccion_diaria/", blank=True)

    class Meta:
        db_table = "novedad_produccion"
        verbose_name = "Novedad de producción"
        verbose_name_plural = "Novedades de producción"


class MaterialProduccion(BaseModel):
    """Material consumido y su costo unitario estimado al momento del registro."""

    produccion = models.ForeignKey(
        ProduccionDiaria,
        on_delete=models.CASCADE,
        related_name="materiales",
        verbose_name="Producción diaria",
    )
    descripcion = models.CharField("Material", max_length=255)
    cantidad = models.DecimalField(
        "Cantidad", max_digits=12, decimal_places=2, default=Decimal("0")
    )
    costo_unitario_estimado = models.DecimalField(
        "Costo unitario estimado",
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
    )

    class Meta:
        db_table = "material_produccion"
        verbose_name = "Material de producción"
        verbose_name_plural = "Materiales de producción"

    @property
    def costo_estimado(self):
        return self.cantidad * self.costo_unitario_estimado


class AlertaProduccion(BaseModel):
    """Alerta persistente de desviación de producción, visible en el dashboard."""

    produccion = models.OneToOneField(
        ProduccionDiaria,
        on_delete=models.CASCADE,
        related_name="alerta_desviacion",
        verbose_name="Producción diaria",
    )
    desviacion_pct = models.DecimalField("Desviación (%)", max_digits=7, decimal_places=2)
    mensaje = models.TextField("Mensaje")
    notificada_en = models.DateTimeField("Notificada en", null=True, blank=True)

    class Meta:
        db_table = "alertas_produccion"
        verbose_name = "Alerta de producción"
        verbose_name_plural = "Alertas de producción"
        ordering = ["-created_at"]
