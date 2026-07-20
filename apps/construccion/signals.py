"""Signals para el módulo construccion (#69, #65, #78)."""
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import (
    KitCerramiento,
    MovimientoFinanciero,
    MovimientoKit,
    PeriodoFinanciero,
    PinturaAeronauticaTorre,
    PinturaFranja,
    ProyectoConstruccion,
    crear_columnas_configurables_default,
    sync_columnas_sistema_pesos_proyecto,
)


@receiver(post_save, sender=ProyectoConstruccion)
def crear_columnas_configurables_proyecto_nuevo(sender, instance, created, **kwargs):
    """#171 B2 (creación) + B3/B4 (actualización): mantiene
    ColumnaConfigurable sincronizado con ProyectoConstruccion en TODO save().

    - `created=True`: genera las 21 filas ColumnaConfigurable 'de fábrica'
      (mismos pesos que hoy rigen por default en el modelo, ya que un
      proyecto recién creado trae los peso_*_pct default). Idempotente —
      get_or_create por (proyecto, capitulo, clave), mismo patrón que
      crear_franjas_pintura_aeronautica de abajo.
    - `created=False`: re-sincroniza `peso_pct` de las columnas
      `es_sistema=True` con los valores ACTUALES de `proyecto.peso_*_pct`
      — desde B3/B4, `avance_ponderado`/`avance_conductor`/`avance_fibra`
      leen el peso desde `ColumnaConfigurable`, no de esos campos
      directamente. Sin esto, editar `proyecto.peso_cerramiento_pct` (o
      cualquier otro `peso_*_pct`) y guardar sería un no-op silencioso
      sobre el avance calculado — hueco encontrado durante B3/B4 (fuera
      del scope original de F2), ver docstring de
      `sync_columnas_sistema_pesos_proyecto`.
    """
    if created:
        crear_columnas_configurables_default(instance)
        return
    sync_columnas_sistema_pesos_proyecto(instance)


@receiver(post_save, sender=PinturaAeronauticaTorre)
def crear_franjas_pintura_aeronautica(sender, instance, created, **kwargs):
    """#78: al crear PinturaAeronauticaTorre genera las 7 franjas con colores
    alternando (1,3,5,7 NARANJA · 2,4,6 BLANCO). Idempotente."""
    if not created:
        return
    for n in range(1, 8):
        color = PinturaFranja.Color.NARANJA if n % 2 == 1 else PinturaFranja.Color.BLANCO
        PinturaFranja.objects.get_or_create(
            pintura_aeronautica=instance,
            numero_franja=n,
            defaults={'color': color},
        )


class PresupuestoBloqueadoError(Exception):
    """Se intentó modificar un movimiento PRESUPUESTO ya establecido."""


@receiver(pre_save, sender=MovimientoFinanciero)
def bloquear_modificacion_presupuesto(sender, instance, **kwargs):
    """#69: el PRESUPUESTO es editable una sola vez. Después solo admins
    pueden cambiarlo y solo si el período NO está cerrado.

    Reglas:
    - Si tipo=REAL → permitir siempre (salvo período cerrado).
    - Si tipo=PRESUPUESTO Y es UPDATE Y valor previo != 0 → bloquear
      (a menos que se setee `instance._override_presupuesto = True` desde
      una vista admin que confirme la edición).
    - Si período.cerrado=True → bloquear REAL también.
    """
    # Período cerrado bloquea cualquier escritura (excepto admin override)
    try:
        periodo = instance.periodo
    except PeriodoFinanciero.DoesNotExist:
        return
    if periodo and periodo.cerrado and not getattr(instance, '_override_cierre', False):
        raise PresupuestoBloqueadoError(
            f'Período {periodo} está cerrado — no acepta nuevos movimientos.'
        )

    # Bloqueo edición PRESUPUESTO (solo first-write)
    if instance.tipo != MovimientoFinanciero.Tipo.PRESUPUESTO:
        return
    if not instance.pk:
        return  # creación = primera edición, OK
    if getattr(instance, '_override_presupuesto', False):
        return  # admin confirmó la edición
    try:
        previo = MovimientoFinanciero.objects.get(pk=instance.pk)
    except MovimientoFinanciero.DoesNotExist:
        return
    if previo.valor and previo.valor != 0:
        # Ya tenía valor presupuestado → no permitir
        raise PresupuestoBloqueadoError(
            f'El PRESUPUESTO de "{previo.categoria.nombre}" para {periodo} '
            f'ya está establecido en ${previo.valor:,.0f} y no puede modificarse '
            f'(regla #69). Setear instance._override_presupuesto=True para confirmar.'
        )


# === #65 Histórico movimientos kits ===

@receiver(post_save, sender=KitCerramiento)
def registrar_movimiento_kit(sender, instance, created, **kwargs):
    """Genera MovimientoKit cuando el kit cambia de torre o estado.
    Compara contra _state_previo (setado en pre_save abajo) o el estado
    actual si es creación."""
    if created:
        if instance.torre_actual:
            MovimientoKit.objects.create(
                kit=instance,
                accion=MovimientoKit.Accion.ASIGNAR,
                torre_destino=instance.torre_actual,
                estado_nuevo=instance.estado,
            )
        return
    # Update: lee estado previo del marcador
    previo_torre = getattr(instance, '_previo_torre_actual_id', None)
    previo_estado = getattr(instance, '_previo_estado', None)
    if previo_torre != instance.torre_actual_id:
        if previo_torre and instance.torre_actual_id:
            accion = MovimientoKit.Accion.MOVER
        elif previo_torre:
            accion = MovimientoKit.Accion.LIBERAR
        else:
            accion = MovimientoKit.Accion.ASIGNAR
        from .models import TorreConstruccion
        MovimientoKit.objects.create(
            kit=instance,
            accion=accion,
            torre_origen=TorreConstruccion.objects.filter(id=previo_torre).first() if previo_torre else None,
            torre_destino=instance.torre_actual,
            estado_previo=previo_estado or '',
            estado_nuevo=instance.estado,
        )
    elif previo_estado and previo_estado != instance.estado:
        MovimientoKit.objects.create(
            kit=instance,
            accion=MovimientoKit.Accion.ESTADO,
            torre_destino=instance.torre_actual,
            estado_previo=previo_estado,
            estado_nuevo=instance.estado,
        )


@receiver(pre_save, sender=KitCerramiento)
def capturar_estado_previo_kit(sender, instance, **kwargs):
    """Captura el torre_actual_id y estado previos para que el signal
    post_save sepa con qué comparar."""
    if not instance.pk:
        return
    try:
        previo = KitCerramiento.objects.get(pk=instance.pk)
        instance._previo_torre_actual_id = previo.torre_actual_id
        instance._previo_estado = previo.estado
    except KitCerramiento.DoesNotExist:
        pass


# B2a (#74) — Detalle OC granularidad torre × pata. Signal post_save refresca
# el cache agregado ObraCivilTorre. Import diferido al final del archivo para
# evitar ciclos en import time del módulo.
from . import signals_b3_oc_detalle  # noqa: F401, E402

# B3a (#76) — signal post_save MontajeEstructuraTorreDetalle → cache legacy
from . import signals_b3_mont_detalle  # noqa: F401,E402
