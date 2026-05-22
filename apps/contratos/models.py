"""
Models for contract management by business unit.
"""
from django.db import models

from apps.core.models import BaseModel


class Contrato(BaseModel):
    """
    Contract linked to a business unit (Mantenimiento or Construccion).
    """

    class UnidadNegocio(models.TextChoices):
        MANTENIMIENTO = 'MANTENIMIENTO', 'Mantenimiento de Líneas'
        CONSTRUCCION = 'CONSTRUCCION', 'Construcción de Líneas'

    class Estado(models.TextChoices):
        ACTIVO = 'ACTIVO', 'Activo'
        FINALIZADO = 'FINALIZADO', 'Finalizado'
        SUSPENDIDO = 'SUSPENDIDO', 'Suspendido'

    class TipoContrato(models.TextChoices):
        LLAVE_EN_MANO = 'LLAVE_EN_MANO', 'Llave en Mano'
        SUMA_GLOBAL = 'SUMA_GLOBAL', 'Suma Global'
        ADMINISTRACION = 'ADMINISTRACION', 'Por Administración'
        PRECIOS_UNITARIOS = 'PRECIOS_UNITARIOS', 'Precios Unitarios'

    unidad_negocio = models.CharField(
        'Unidad de negocio',
        max_length=20,
        choices=UnidadNegocio.choices,
    )
    codigo = models.CharField(
        'Código',
        max_length=50,
        unique=True,
    )
    nombre = models.CharField(
        'Nombre del contrato',
        max_length=300,
    )
    cliente = models.CharField(
        'Cliente',
        max_length=200,
        blank=True,
    )
    objeto = models.TextField(
        'Objeto del contrato',
        blank=True,
    )
    valor = models.DecimalField(
        'Valor del contrato',
        max_digits=16,
        decimal_places=2,
        default=0,
    )
    fecha_inicio = models.DateField(
        'Fecha de inicio',
        null=True,
        blank=True,
    )
    fecha_fin = models.DateField(
        'Fecha de finalización',
        null=True,
        blank=True,
    )
    estado = models.CharField(
        'Estado',
        max_length=20,
        choices=Estado.choices,
        default=Estado.ACTIVO,
    )
    observaciones = models.TextField(
        'Observaciones',
        blank=True,
    )
    tipo_contrato = models.CharField(
        'Tipo de contrato',
        max_length=30,
        choices=TipoContrato.choices,
        blank=True,
    )
    plazo_ejecucion = models.IntegerField(
        'Plazo de ejecución (días)',
        null=True,
        blank=True,
    )
    longitud_linea = models.DecimalField(
        'Longitud de la línea (km)',
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    acta_inicio = models.FileField(
        'Acta de inicio (documento firmado)',
        upload_to='contratos/actas/',
        null=True,
        blank=True,
    )
    fecha_acta_inicio = models.DateField(
        'Fecha del Acta de Inicio',
        null=True,
        blank=True,
        help_text='Fecha de firma del Acta. Habilita registro de actividades y rige el cálculo de plazos.',
    )
    numero_torres = models.PositiveIntegerField(
        'Número de torres',
        null=True,
        blank=True,
    )

    class Voltaje(models.TextChoices):
        KV_115 = '115', '115 kV'
        KV_230 = '230', '230 kV'
        KV_500 = '500', '500 kV'

    voltaje = models.CharField(
        'Voltaje de la línea',
        max_length=5,
        choices=Voltaje.choices,
        blank=True,
    )
    numero_circuitos = models.PositiveSmallIntegerField(
        'Número de circuitos',
        null=True,
        blank=True,
        choices=[(1, '1 circuito'), (2, '2 circuitos')],
        help_text='Afecta el tendido (Único / Doble)',
    )

    class Meta:
        db_table = 'contratos'
        verbose_name = 'Contrato'
        verbose_name_plural = 'Contratos'
        ordering = ['unidad_negocio', 'codigo']

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"

    @property
    def puede_iniciar_actividades(self):
        """True si el Acta de Inicio ya fue firmada (regla de negocio Gabriel Valencia)."""
        return self.fecha_acta_inicio is not None

    @property
    def dias_transcurridos(self):
        """Días desde la firma del Acta. None si aún no firmada."""
        if not self.fecha_acta_inicio:
            return None
        from datetime import date
        return (date.today() - self.fecha_acta_inicio).days

    @property
    def dias_restantes(self):
        """Días restantes del plazo. Negativo si está vencido. None si falta data."""
        if not self.fecha_acta_inicio or not self.plazo_ejecucion:
            return None
        transcurridos = self.dias_transcurridos
        return self.plazo_ejecucion - transcurridos

    @property
    def fecha_fin_calculada(self):
        """Fecha fin esperada según Acta + plazo. None si falta data."""
        if not self.fecha_acta_inicio or not self.plazo_ejecucion:
            return None
        from datetime import timedelta
        return self.fecha_acta_inicio + timedelta(days=self.plazo_ejecucion)

    def generar_proyecto_y_torres(self):
        """Para Contratos CONSTRUCCION: crea ProyectoConstruccion y N TorreConstruccion
        nombradas E1, E2, ..., En según numero_torres. Idempotente — no duplica.
        """
        if self.unidad_negocio != self.UnidadNegocio.CONSTRUCCION:
            return None, []
        if not self.numero_torres:
            return None, []
        from apps.construccion.models import ProyectoConstruccion, TorreConstruccion
        proyecto, _ = ProyectoConstruccion.objects.get_or_create(
            contrato=self,
            defaults={'nombre': self.nombre},
        )
        existentes = set(proyecto.torres.values_list('numero', flat=True))
        nuevas = []
        for i in range(1, self.numero_torres + 1):
            numero = f"E{i}"
            if numero in existentes:
                continue
            nuevas.append(TorreConstruccion(proyecto=proyecto, numero=numero))
        if nuevas:
            TorreConstruccion.objects.bulk_create(nuevas, ignore_conflicts=True)
        return proyecto, nuevas
