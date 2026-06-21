from django.db import models


class PlanServicio(models.Model):
    nombre = models.CharField('Nombre del Plan', max_length=100)
    precio = models.DecimalField('Precio Mensual (COP)', max_digits=12, decimal_places=2)
    descripcion = models.TextField('Descripcion', blank=True)
    activo = models.BooleanField('Activo', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Plan de Servicio'
        verbose_name_plural = 'Planes de Servicio'

    def __str__(self):
        return f"{self.nombre} - ${float(self.precio):,.0f} COP/mes"


class DatosFacturacion(models.Model):
    TIPO_PERSONA_CHOICES = [
        ('JURIDICA', 'Persona Juridica'),
        ('NATURAL', 'Persona Natural'),
    ]
    TIPO_IDENTIFICACION_CHOICES = [
        ('NIT', 'NIT'),
        ('CC', 'Cedula de Ciudadania'),
        ('CE', 'Cedula de Extranjeria'),
    ]
    REGIMEN_CHOICES = [
        ('COMMON_REGIME', 'Regimen Comun'),
        ('SIMPLIFIED_REGIME', 'Regimen Simplificado'),
    ]

    tipo_persona = models.CharField('Tipo de persona', max_length=10, choices=TIPO_PERSONA_CHOICES)
    razon_social = models.CharField('Razon social / Nombre', max_length=200)
    tipo_identificacion = models.CharField('Tipo de identificacion', max_length=5, choices=TIPO_IDENTIFICACION_CHOICES)
    numero_identificacion = models.CharField('Numero de identificacion', max_length=20)
    dv = models.CharField('Digito de verificacion', max_length=1, blank=True)
    email = models.EmailField('Email de facturacion')
    telefono = models.CharField('Telefono', max_length=20)
    direccion = models.CharField('Direccion', max_length=200)
    ciudad = models.CharField('Ciudad', max_length=100)
    departamento = models.CharField('Departamento', max_length=100)
    regimen = models.CharField('Regimen', max_length=20, choices=REGIMEN_CHOICES, default='COMMON_REGIME')
    alegra_contacto_id = models.CharField('ID Contacto Alegra', max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Datos de Facturacion'
        verbose_name_plural = 'Datos de Facturacion'

    def __str__(self):
        return f"{self.razon_social} - {self.tipo_identificacion} {self.numero_identificacion}"


class Suscripcion(models.Model):
    ESTADO_CHOICES = [
        ('ACTIVA', 'Activa'),
        ('PENDIENTE', 'Pendiente de Pago'),
        ('SUSPENDIDA', 'Suspendida'),
        ('CANCELADA', 'Cancelada'),
    ]
    plan = models.ForeignKey(PlanServicio, on_delete=models.PROTECT, verbose_name='Plan')
    estado = models.CharField('Estado', max_length=20, choices=ESTADO_CHOICES, default='PENDIENTE')
    fecha_inicio = models.DateField('Fecha de Inicio', auto_now_add=True)
    fecha_proximo_pago = models.DateField('Proximo Pago', null=True, blank=True)
    wompi_payment_source_id = models.CharField('WOMPI Payment Source ID', max_length=100, blank=True)
    datos_facturacion = models.ForeignKey(
        DatosFacturacion, on_delete=models.SET_NULL,
        blank=True, null=True, related_name='suscripciones',
        verbose_name='Datos de facturacion'
    )
    notas = models.TextField('Notas', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Suscripcion'
        verbose_name_plural = 'Suscripciones'
        ordering = ['-created_at']

    def __str__(self):
        return f"Suscripcion {self.plan.nombre} - {self.get_estado_display()}"


class Pago(models.Model):
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('APROBADO', 'Aprobado'),
        ('RECHAZADO', 'Rechazado'),
        ('ERROR', 'Error'),
        ('ANULADO', 'Anulado'),
    ]
    suscripcion = models.ForeignKey(Suscripcion, on_delete=models.CASCADE, related_name='pagos', verbose_name='Suscripcion')
    monto = models.DecimalField('Monto (COP)', max_digits=12, decimal_places=2)
    estado = models.CharField('Estado', max_length=20, choices=ESTADO_CHOICES, default='PENDIENTE')
    wompi_transaction_id = models.CharField('WOMPI Transaction ID', max_length=100, blank=True, db_index=True)
    wompi_reference = models.CharField('Referencia WOMPI', max_length=100, blank=True)
    metodo_pago = models.CharField('Metodo de Pago', max_length=50, blank=True)
    detalle_respuesta = models.JSONField('Detalle Respuesta WOMPI', default=dict, blank=True)
    alegra_invoice_id = models.CharField('ID Factura Alegra', max_length=50, blank=True, null=True)
    fecha_pago = models.DateTimeField('Fecha de Pago', auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Pago'
        verbose_name_plural = 'Pagos'
        ordering = ['-fecha_pago']

    def __str__(self):
        return f"Pago ${float(self.monto):,.0f} - {self.get_estado_display()}"
