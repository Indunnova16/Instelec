"""Entrada manual de ubicación de cuadrillas (issue #178, F2 — pedido F,
parte 2: "sitios sin señal").

Módulo nuevo, mismo patrón optional-import que ``views_semanal.py``/
``views_b3.py`` (ver ``urls.py``) — se mantiene separado de ``views.py``
para aislar este sub-item. Reusa ``TrackingUbicacion.origen`` (agregado por
M1): las entradas manuales quedan marcadas ``origen='manual'`` para que el
mapa (``mapa.html``) las pinte con un marcador distinto al GPS automático —
evita que alguien confunda una coordenada tecleada a mano con la posición
real reportada por el dispositivo.
"""

from decimal import Decimal, InvalidOperation

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import path
from django.views import View

from apps.core.mixins import RoleRequiredMixin

from .models import Cuadrilla, TrackingUbicacion

# Mismo set de roles que MapaCuadrillasView/MapaCuadrillasPartialView
# (apps/cuadrillas/views.py) — cualquiera que puede VER el mapa puede
# reportar una ubicación manual (incluye liniero/auxiliar: son quienes
# están en campo, en el sitio sin señal).
ROLES_MAPA = [
    "admin",
    "director",
    "coordinador",
    "ing_residente",
    "supervisor",
    "liniero",
    "auxiliar",
]

LAT_MIN, LAT_MAX = Decimal("-90"), Decimal("90")
LNG_MIN, LNG_MAX = Decimal("-180"), Decimal("180")


class TrackingUbicacionManualCreateView(LoginRequiredMixin, RoleRequiredMixin, View):
    """POST /cuadrillas/<uuid:pk_cuadrilla>/ubicacion/manual/

    Crea un ``TrackingUbicacion(origen='manual')`` puntual para la cuadrilla
    indicada. Responde JSON (el mini-form de ``mapa.html`` usa ``fetch()``
    plano, no HTMX — consistente con el resto de esa pantalla, que ya
    polling-ea vía JS plano, no HTMX)."""

    allowed_roles = ROLES_MAPA

    def post(self, request, pk_cuadrilla):
        cuadrilla = get_object_or_404(Cuadrilla, pk=pk_cuadrilla)

        # Edge 2: cuadrilla inactiva (dada de baja) — no tiene sentido
        # seguir reportándole ubicación, ni automática ni manual.
        if not cuadrilla.activa:
            return JsonResponse(
                {
                    "ok": False,
                    "error": f"La cuadrilla {cuadrilla.codigo} está inactiva; no se puede "
                    "reportar ubicación manual.",
                },
                status=400,
            )

        try:
            lat = Decimal((request.POST.get("lat") or "").strip())
            lng = Decimal((request.POST.get("lng") or "").strip())
        except InvalidOperation:
            return JsonResponse(
                {"ok": False, "error": "Latitud/longitud inválidas — deben ser numéricas."},
                status=400,
            )

        # Edge 1: coordenadas fuera de rango geográfico válido.
        if not (LAT_MIN <= lat <= LAT_MAX) or not (LNG_MIN <= lng <= LNG_MAX):
            return JsonResponse(
                {
                    "ok": False,
                    "error": "Coordenadas fuera de rango válido "
                    "(latitud entre -90 y 90, longitud entre -180 y 180).",
                },
                status=400,
            )

        ubicacion = TrackingUbicacion(
            cuadrilla=cuadrilla,
            usuario=request.user,
            latitud=lat,
            longitud=lng,
            origen=TrackingUbicacion.OrigenUbicacion.MANUAL,
        )
        try:
            # Red de seguridad adicional (más allá del rango -90..90/-180..180):
            # valida max_digits/decimal_places del campo (evita un 500 crudo de
            # Postgres si alguien manda una precisión absurda) y el choices de
            # `origen`.
            ubicacion.full_clean()
        except ValidationError as e:
            return JsonResponse({"ok": False, "error": "; ".join(e.messages)}, status=400)

        ubicacion.save()

        return JsonResponse(
            {
                "ok": True,
                "ubicacion": {
                    "cuadrilla_id": str(cuadrilla.id),
                    "cuadrilla_codigo": cuadrilla.codigo,
                    "cuadrilla_nombre": cuadrilla.nombre,
                    "lat": float(ubicacion.latitud),
                    "lng": float(ubicacion.longitud),
                    "origen": ubicacion.origen,
                    "timestamp": ubicacion.created_at.isoformat(),
                },
            }
        )


urlpatterns = [
    path(
        "<uuid:pk_cuadrilla>/ubicacion/manual/",
        TrackingUbicacionManualCreateView.as_view(),
        name="ubicacion_manual_crear",
    ),
]
