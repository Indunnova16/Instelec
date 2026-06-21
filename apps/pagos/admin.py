from django.contrib import admin
from .models import PlanServicio, Suscripcion, Pago, DatosFacturacion


@admin.register(DatosFacturacion)
class DatosFacturacionAdmin(admin.ModelAdmin):
    list_display = ('razon_social', 'tipo_identificacion', 'numero_identificacion', 'email', 'alegra_contacto_id')
    search_fields = ('razon_social', 'numero_identificacion', 'email')
    readonly_fields = ('created_at', 'updated_at', 'alegra_contacto_id')


@admin.register(PlanServicio)
class PlanServicioAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'precio', 'activo', 'created_at')
    list_filter = ('activo',)


@admin.register(Suscripcion)
class SuscripcionAdmin(admin.ModelAdmin):
    list_display = ('plan', 'estado', 'fecha_inicio', 'fecha_proximo_pago', 'datos_facturacion')
    list_filter = ('estado',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ('suscripcion', 'monto', 'estado', 'wompi_transaction_id', 'alegra_invoice_id', 'fecha_pago')
    list_filter = ('estado', 'fecha_pago')
    search_fields = ('wompi_transaction_id', 'wompi_reference', 'alegra_invoice_id')
    readonly_fields = ('created_at', 'updated_at', 'detalle_respuesta')
    date_hierarchy = 'fecha_pago'
