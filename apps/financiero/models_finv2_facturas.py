"""Persistencia compartida para facturas de gastos e ingresos (S1)."""
from django.db import models

from apps.core.models import BaseModel
from .models_base import CicloFacturacion


class Banco(BaseModel):
    nombre = models.CharField('Nombre', max_length=150, unique=True)
    activo = models.BooleanField('Activo', default=True)

    class Meta:
        db_table = 'financiero_bancos'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class MetodoPago(BaseModel):
    nombre = models.CharField('Nombre', max_length=100, unique=True)
    activo = models.BooleanField('Activo', default=True)

    class Meta:
        db_table = 'financiero_metodos_pago'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Proveedor(BaseModel):
    nombre = models.CharField('Nombre o razón social', max_length=255)
    nit = models.CharField('NIT', max_length=30, blank=True, unique=True, null=True)
    email = models.EmailField('Correo electrónico', blank=True)
    telefono = models.CharField('Teléfono', max_length=50, blank=True)
    activo = models.BooleanField('Activo', default=True)

    class Meta:
        db_table = 'financiero_proveedores'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Cliente(BaseModel):
    nombre = models.CharField('Nombre o razón social', max_length=255)
    nit = models.CharField('NIT', max_length=30, blank=True, unique=True, null=True)
    email = models.EmailField('Correo electrónico', blank=True)
    telefono = models.CharField('Teléfono', max_length=50, blank=True)
    activo = models.BooleanField('Activo', default=True)

    class Meta:
        db_table = 'financiero_clientes'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class FacturaGasto(BaseModel):
    class Estado(models.TextChoices):
        PENDIENTE_APROBACION = 'PENDIENTE_APROBACION', 'Pendiente de aprobación'
        PENDIENTE_PAGO = 'PENDIENTE_PAGO', 'Pendiente de pago'
        RECHAZADA = 'RECHAZADA', 'Rechazada'
        PAGADA = 'PAGADA', 'Pagada'

    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT, related_name='facturas_gasto')
    contrato = models.ForeignKey('contratos.Contrato', on_delete=models.PROTECT, related_name='facturas_gasto')
    presupuesto = models.ForeignKey('financiero.Presupuesto', on_delete=models.SET_NULL, null=True, blank=True, related_name='facturas_gasto')
    homologacion = models.ForeignKey('financiero.HomologacionProjectsContable', on_delete=models.PROTECT, null=True, blank=True, related_name='facturas_gasto')
    banco = models.ForeignKey(Banco, on_delete=models.PROTECT, null=True, blank=True, related_name='facturas_gasto')
    metodo_pago = models.ForeignKey(MetodoPago, on_delete=models.PROTECT, null=True, blank=True, related_name='facturas_gasto')
    numero_documento = models.CharField('Número de documento', max_length=100)
    documento = models.FileField('Documento', upload_to='financiero/facturas_gasto/', blank=True)
    fecha = models.DateField('Fecha')
    concepto = models.CharField('Concepto', max_length=255)
    categoria = models.CharField('Categoría', max_length=255)
    centro_costo = models.CharField('Centro de costo', max_length=100, blank=True)
    subtotal = models.DecimalField('Subtotal', max_digits=18, decimal_places=2)
    iva = models.DecimalField('IVA', max_digits=18, decimal_places=2, default=0)
    total = models.DecimalField('Total', max_digits=18, decimal_places=2)
    estado = models.CharField(max_length=25, choices=Estado.choices, default=Estado.PENDIENTE_PAGO)
    comentario_decision = models.TextField('Comentario de aprobación', blank=True)
    referencia_pago = models.CharField('Referencia de pago', max_length=100, blank=True)

    class Meta:
        db_table = 'financiero_facturas_gasto'
        ordering = ['-fecha', '-created_at']
        constraints = [models.UniqueConstraint(fields=['proveedor', 'numero_documento'], name='uq_finv2_gasto_proveedor_doc')]

    def __str__(self):
        return f'{self.proveedor} — {self.numero_documento}'


class PagoFacturaGasto(BaseModel):
    factura = models.ForeignKey(FacturaGasto, on_delete=models.CASCADE, related_name='pagos')
    banco = models.ForeignKey(Banco, on_delete=models.PROTECT)
    metodo_pago = models.ForeignKey(MetodoPago, on_delete=models.PROTECT)
    fecha = models.DateField('Fecha')
    monto = models.DecimalField('Monto', max_digits=18, decimal_places=2)
    referencia = models.CharField('Referencia', max_length=100)

    class Meta:
        db_table = 'financiero_pagos_factura_gasto'
        ordering = ['-fecha', '-created_at']


# CicloFacturacion sigue siendo el agregado raíz del ingreso; los campos se
# instalan aquí para no volver a abrir el monolito legacy models_base.py.
CicloFacturacion.add_to_class('cliente', models.ForeignKey(Cliente, on_delete=models.PROTECT, null=True, blank=True, related_name='ciclos_facturacion'))
CicloFacturacion.add_to_class('banco_pago', models.ForeignKey(Banco, on_delete=models.PROTECT, null=True, blank=True, related_name='ciclos_facturacion_pagados'))
CicloFacturacion.add_to_class('numero_secuencial', models.PositiveIntegerField('Número secuencial', null=True, blank=True, unique=True))
CicloFacturacion.add_to_class('subtotal', models.DecimalField('Subtotal', max_digits=18, decimal_places=2, default=0))
CicloFacturacion.add_to_class('iva', models.DecimalField('IVA', max_digits=18, decimal_places=2, default=0))
CicloFacturacion.add_to_class('total', models.DecimalField('Total', max_digits=18, decimal_places=2, default=0))
CicloFacturacion.add_to_class('plazo_pago_dias', models.PositiveIntegerField('Plazo de pago (días)', null=True, blank=True))
CicloFacturacion.add_to_class('referencia_cobro', models.CharField('Referencia de cobro', max_length=100, blank=True))


class LineaFacturaIngreso(BaseModel):
    ciclo = models.ForeignKey(CicloFacturacion, on_delete=models.CASCADE, related_name='lineas_factura')
    descripcion = models.CharField('Descripción', max_length=255)
    cantidad = models.DecimalField('Cantidad', max_digits=12, decimal_places=2, default=1)
    valor_unitario = models.DecimalField('Valor unitario', max_digits=18, decimal_places=2)
    total = models.DecimalField('Total', max_digits=18, decimal_places=2)

    class Meta:
        db_table = 'financiero_lineas_factura_ingreso'
        ordering = ['created_at']


class PagoFacturaIngreso(BaseModel):
    ciclo = models.ForeignKey(CicloFacturacion, on_delete=models.CASCADE, related_name='pagos_factura')
    banco = models.ForeignKey(Banco, on_delete=models.PROTECT)
    metodo_pago = models.ForeignKey(MetodoPago, on_delete=models.PROTECT)
    fecha = models.DateField('Fecha')
    monto = models.DecimalField('Monto', max_digits=18, decimal_places=2)
    referencia = models.CharField('Referencia', max_length=100)

    class Meta:
        db_table = 'financiero_pagos_factura_ingreso'
        ordering = ['-fecha', '-created_at']
