"""Listado, historial y notificación de alertas de Producción Diaria (#252)."""

import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone
from django.views.generic import ListView

from apps.core.mixins import RoleRequiredMixin
from apps.usuarios.models import Usuario

from .models_produccion_diaria import AlertaProduccion, ProduccionDiaria
from .services_produccion_diaria import sincronizar_alerta_desviacion

logger = logging.getLogger(__name__)
PRODUCCION_DIARIA_ROLES = ["admin", "director", "coordinador", "supervisor"]


def notificar_alerta_desviacion(alerta):
    """Envía una alerta nueva a directores activos y registra la entrega.

    No se marca ``notificada_en`` si no hay destinatario o falla el backend de
    correo: así un siguiente listado puede reintentar sin perder la alerta.
    """
    destinatarios = list(
        Usuario.objects.filter(rol="director", is_active=True)
        .exclude(email="")
        .values_list("email", flat=True)
    )
    if not destinatarios:
        logger.warning("Alerta %s sin director activo destinatario", alerta.pk)
        return "No hay directores activos configurados para recibir la alerta."

    produccion = alerta.produccion
    programacion = produccion.programacion
    try:
        detalle_url = reverse("construccion:produccion_diaria_detalle", args=[produccion.pk])
    except Exception:  # La ruta B1 puede no estar integrada durante el merge.
        detalle_url = f"/construccion/produccion-diaria/{produccion.pk}/"
    proyecto = programacion.proyecto or "Sin proyecto asociado"
    try:
        send_mail(
            subject="Alerta de desviación en producción diaria",
            message=(
                f"{alerta.mensaje}\n\n"
                f"Cuadrilla: {programacion.cuadrilla}\n"
                f"Proyecto: {proyecto}\n"
                f"Fecha de producción: {produccion.fecha:%Y-%m-%d}\n"
                f"Detalle: {detalle_url}"
            ),
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=destinatarios,
            fail_silently=False,
        )
    except Exception:
        logger.exception("No fue posible notificar alerta de producción %s", alerta.pk)
        return "No fue posible enviar el correo de alerta; se reintentará."

    alerta.notificada_en = timezone.now()
    alerta.save(update_fields=["notificada_en", "updated_at"])
    return None


def sincronizar_alertas_de_producciones(producciones):
    """Sincroniza alertas contra la ejecución semanal y notifica altas nuevas.

    Una programación sin ejecución todavía no tiene un valor real verificable;
    por ello no se inventa una desviación. Una base programada igual a cero se
    delega al servicio compartido, que elimina cualquier alerta obsoleta.
    """
    errores = []
    for produccion in producciones:
        programacion = produccion.programacion
        ejecucion = getattr(programacion, "ejecucion", None)
        if ejecucion is None and (programacion.torres_programadas or 0) > 0:
            continue

        ya_existia = AlertaProduccion.objects.filter(produccion=produccion).exists()
        alerta = sincronizar_alerta_desviacion(
            produccion,
            getattr(ejecucion, "torres_ejecutadas", 0),
            programacion.torres_programadas,
        )
        if alerta and (not ya_existia or alerta.notificada_en is None):
            error = notificar_alerta_desviacion(alerta)
            if error:
                errores.append(error)
    return errores


class _ProduccionDiariaBaseListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    """Comportamiento compartido para las dos superficies de consulta."""

    model = ProduccionDiaria
    context_object_name = "producciones"
    paginate_by = 50
    allowed_roles = PRODUCCION_DIARIA_ROLES

    def get_queryset(self):
        return ProduccionDiaria.objects.select_related(
            "programacion",
            "programacion__cuadrilla",
            "programacion__proyecto",
            "programacion__ejecucion",
            "alerta_desviacion",
        ).order_by("-fecha", "-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        producciones = list(context["producciones"])
        context["errores_alerta"] = sincronizar_alertas_de_producciones(producciones)
        alertas = AlertaProduccion.objects.filter(produccion__in=producciones)
        alertas_por_produccion = {alerta.produccion_id: alerta for alerta in alertas}
        for produccion in producciones:
            produccion.alerta_actual = alertas_por_produccion.get(produccion.pk)
        context["producciones"] = producciones
        return context


class ProduccionDiariaListView(_ProduccionDiariaBaseListView):
    """Lista diaria con badge para desviaciones persistentes superiores a 20 %."""

    template_name = "construccion/produccion_diaria/listado_diario.html"


class ProduccionDiariaHistorialView(_ProduccionDiariaBaseListView):
    """Expone exclusivamente los últimos 30 días calendario de producción."""

    template_name = "construccion/produccion_diaria/historial_30_dias.html"
    paginate_by = 100

    def get_queryset(self):
        fecha_inicio = timezone.localdate() - timedelta(days=29)
        return super().get_queryset().filter(fecha__gte=fecha_inicio)
