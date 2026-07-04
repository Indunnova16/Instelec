"""Programación semanal de cuadrillas — vista semanal, duplicar y export PDF.

Issue Indunnova16/Instelec#178 — Sprint C (parte NO bloqueada por el archivo de
Alcides): C1 (grid semanal read-only, mínimo — aloja las dos acciones), C2
("Duplicar semana anterior") y C3 (export PDF imprimible).

La "programación semanal" NO tiene un modelo propio: se materializa como el
conjunto de ``Cuadrilla`` cuyo ``codigo`` tiene el prefijo ``WW-YYYY-`` (formato
generado por ``ProgramacionS18CuadrillaImporter._generar_codigo``:
``{semana:02d}-{anio}-{numero:04d}-{iniciales}``). Cada ``Cuadrilla`` es un
bloque de actividad de esa semana; sus ``CuadrillaMiembro`` son el personal
asignado. La sección NOVEDADES vive en ``NovedadPersonalSemana`` (semana+año
explícitos, sin FK a Cuadrilla).

NO se toca el namespace ``construccion:programacion_cuadrilla*`` (concepto
distinto: asignación de cuadrilla a proyecto/torre), ni el flujo de carga
masiva S18 vertical existente (#124).
"""

import logging
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.urls import path, reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.core.mixins import RoleRequiredMixin

from .models import Cuadrilla, CuadrillaMiembro, NovedadPersonalSemana

logger = logging.getLogger(__name__)

# Roles con acceso — se replica el gate de ``CuadrillaListView`` para que la
# programación semanal quede alineada con el resto del módulo Cuadrillas.
# (Cualquier rol nivel admin pasa vía RoleRequiredMixin/RBAC v2 aunque no esté
# listado aquí.)
ROLES_CUADRILLAS = ["admin", "director", "coordinador", "ing_residente", "supervisor"]


# ---------------------------------------------------------------------------
# Helpers de semana
# ---------------------------------------------------------------------------


def _prefijo(anio, semana):
    """Prefijo de código que identifica una semana: ``WW-YYYY-``."""
    return f"{int(semana):02d}-{int(anio)}-"


def _bloques_qs(anio, semana):
    """Cuadrillas (bloques de actividad) de una semana, con miembros precargados."""
    return (
        Cuadrilla.objects.filter(codigo__startswith=_prefijo(anio, semana))
        .select_related("linea_asignada", "vehiculo", "supervisor")
        .prefetch_related("miembros__usuario")
        .order_by("codigo")
    )


def _ultima_semana_iso(anio):
    """Última semana ISO del año (52 o 53). El 28-dic siempre cae en ella."""
    return date(anio, 12, 28).isocalendar()[1]


def _semana_anterior(anio, semana):
    """(anio, semana) de la semana inmediatamente anterior, cruzando el año."""
    if semana > 1:
        return anio, semana - 1
    prev = anio - 1
    return prev, _ultima_semana_iso(prev)


def _semana_siguiente(anio, semana):
    if semana >= _ultima_semana_iso(anio):
        return anio + 1, 1
    return anio, semana + 1


def _recodigo(codigo, semana, anio):
    """Reindexa un código ``WW-YYYY-NNNN-XXX`` a otra semana/año, preservando
    número de actividad e iniciales."""
    partes = codigo.split("-")
    resto = partes[2:] if len(partes) > 2 else []
    return _prefijo(anio, semana) + "-".join(resto)


def _shift(fecha, dias=7):
    """Corre una fecha ``dias`` hacia adelante (None → None)."""
    if not fecha:
        return None
    return fecha + timedelta(days=dias)


def _rango_calendario(anio, semana):
    """(lunes, domingo) del calendario para una semana ISO, o (None, None)."""
    try:
        lunes = date.fromisocalendar(anio, semana, 1)
        return lunes, lunes + timedelta(days=6)
    except ValueError:
        return None, None


def _bloque_a_dict(cuadrilla):
    """Normaliza una Cuadrilla + miembros a un dict listo para plantilla.

    Ordena los miembros con el Jefe de Trabajo (JT/CTA) primero.
    """
    miembros = [
        {
            "nombre": (m.usuario.get_full_name() or m.usuario.get_username()),
            "documento": getattr(m.usuario, "documento", "") or "",
            "rol": m.get_rol_cuadrilla_display(),
            "cargo": m.get_cargo_display(),
            "es_jt": m.cargo == "JT_CTA",
        }
        for m in cuadrilla.miembros.all()
        if m.activo
    ]
    miembros.sort(key=lambda x: (not x["es_jt"], x["nombre"]))
    return {
        "codigo": cuadrilla.codigo,
        "nombre": cuadrilla.nombre,
        "linea": getattr(cuadrilla.linea_asignada, "codigo", "") or "",
        "vehiculo": getattr(cuadrilla.vehiculo, "placa", "") or "",
        "fecha": cuadrilla.fecha,
        "observaciones": cuadrilla.observaciones or "",
        "miembros": miembros,
    }


def _contexto_semana(anio, semana):
    """Contexto compartido por la vista grid y el export PDF."""
    bloques = [_bloque_a_dict(c) for c in _bloques_qs(anio, semana)]
    novedades = list(
        NovedadPersonalSemana.objects.filter(anio=anio, semana=semana).order_by("nombre")
    )
    total_miembros = sum(len(b["miembros"]) for b in bloques)
    lunes, domingo = _rango_calendario(anio, semana)
    origen_anio, origen_semana = _semana_anterior(anio, semana)
    prev_anio, prev_semana = origen_anio, origen_semana
    next_anio, next_semana = _semana_siguiente(anio, semana)
    return {
        "anio": anio,
        "semana": semana,
        "bloques": bloques,
        "novedades": novedades,
        "total_bloques": len(bloques),
        "total_miembros": total_miembros,
        "total_novedades": len(novedades),
        "tiene_datos": bool(bloques) or bool(novedades),
        "lunes": lunes,
        "domingo": domingo,
        "origen_anio": origen_anio,
        "origen_semana": origen_semana,
        "origen_tiene_datos": _bloques_qs(origen_anio, origen_semana).exists(),
        "prev_anio": prev_anio,
        "prev_semana": prev_semana,
        "next_anio": next_anio,
        "next_semana": next_semana,
    }


# ---------------------------------------------------------------------------
# Vistas
# ---------------------------------------------------------------------------


class ProgramacionSemanalIndexView(LoginRequiredMixin, RoleRequiredMixin, View):
    """``/cuadrillas/semanal/`` → redirige a la semana con datos más reciente
    (o a la semana ISO actual si no hay ninguna programación cargada)."""

    allowed_roles = ROLES_CUADRILLAS

    def get(self, request):
        codigos = Cuadrilla.objects.filter(codigo__regex=r"^[0-9]{2}-[0-9]{4}-").values_list(
            "codigo", flat=True
        )
        mejor = None
        for codigo in codigos:
            partes = codigo.split("-")
            try:
                sem, ano = int(partes[0]), int(partes[1])
            except (ValueError, IndexError):
                continue
            if 1 <= sem <= 53 and 2000 <= ano <= 2100:
                if mejor is None or (ano, sem) > mejor:
                    mejor = (ano, sem)
        if mejor is None:
            hoy = date.today().isocalendar()
            mejor = (hoy[0], hoy[1])
        return redirect("cuadrillas:semanal_grid", anio=mejor[0], semana=mejor[1])


class ProgramacionSemanalGridView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Grid semanal read-only: bloques de actividad + personal + NOVEDADES,
    con navegación prev/next y las acciones Duplicar / Exportar PDF."""

    template_name = "cuadrillas/programacion_semanal_grid.html"
    allowed_roles = ROLES_CUADRILLAS

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        anio = int(self.kwargs["anio"])
        semana = int(self.kwargs["semana"])
        context.update(_contexto_semana(anio, semana))
        # Cuando la semana destino ya tiene datos, el POST de duplicar pide
        # confirmación redirigiendo aquí con ?confirmar_duplicado=1.
        context["confirmar_duplicado"] = self.request.GET.get("confirmar_duplicado") == "1"
        return context


class ProgramacionSemanalDuplicarView(LoginRequiredMixin, RoleRequiredMixin, View):
    """Copia los bloques (Cuadrilla + CuadrillaMiembro) de la semana anterior a
    la semana destino como base editable. NO destructivo: si un bloque ya existe
    en el destino se omite (no se sobrescribe). Las NOVEDADES no se duplican."""

    allowed_roles = ROLES_CUADRILLAS

    def post(self, request, anio, semana):
        anio, semana = int(anio), int(semana)
        origen_anio, origen_semana = _semana_anterior(anio, semana)
        origen = list(_bloques_qs(origen_anio, origen_semana))

        if not origen:
            messages.error(
                request,
                f"La semana anterior ({origen_semana:02d}/{origen_anio}) no tiene "
                f"programación cargada; no hay nada que duplicar.",
            )
            return redirect("cuadrillas:semanal_grid", anio=anio, semana=semana)

        destino_existe = _bloques_qs(anio, semana).exists()
        if destino_existe and not request.POST.get("confirmar"):
            messages.warning(
                request,
                f"La semana {semana:02d}/{anio} ya tiene programación. Al duplicar "
                f"solo se agregarán los bloques que falten (los existentes NO se "
                f"sobrescriben). Confirmá para continuar.",
            )
            url = reverse("cuadrillas:semanal_grid", args=[anio, semana])
            return redirect(f"{url}?confirmar_duplicado=1")

        creadas = 0
        omitidas = 0
        miembros_creados = 0
        with transaction.atomic():
            for c in origen:
                nuevo_codigo = _recodigo(c.codigo, semana, anio)
                if Cuadrilla.objects.filter(codigo=nuevo_codigo).exists():
                    omitidas += 1
                    continue
                nueva = Cuadrilla.objects.create(
                    codigo=nuevo_codigo,
                    nombre=c.nombre,
                    supervisor=c.supervisor,
                    vehiculo=c.vehiculo,
                    linea_asignada=c.linea_asignada,
                    activa=True,
                    observaciones=c.observaciones,
                    fecha=_shift(c.fecha, 7),
                )
                for m in c.miembros.all():
                    if not m.activo:
                        continue
                    CuadrillaMiembro.objects.create(
                        cuadrilla=nueva,
                        usuario=m.usuario,
                        rol_cuadrilla=m.rol_cuadrilla,
                        cargo=m.cargo,
                        costo_dia=m.costo_dia,
                        fecha_inicio=_shift(m.fecha_inicio, 7) or date.today(),
                        fecha_fin=_shift(m.fecha_fin, 7),
                        activo=True,
                        es_conductor_interno=m.es_conductor_interno,
                    )
                    miembros_creados += 1
                creadas += 1

        if creadas:
            extra = f" {omitidas} ya existían y se omitieron." if omitidas else ""
            messages.success(
                request,
                f"Semana {semana:02d}/{anio}: se duplicaron {creadas} bloque(s) y "
                f"{miembros_creados} asignación(es) desde la semana "
                f"{origen_semana:02d}/{origen_anio}.{extra} Ahora podés editarla.",
            )
        else:
            messages.info(
                request,
                f"No se creó ningún bloque nuevo: los {omitidas} bloque(s) de la "
                f"semana {origen_semana:02d}/{origen_anio} ya existían en la semana "
                f"{semana:02d}/{anio}.",
            )
        return redirect("cuadrillas:semanal_grid", anio=anio, semana=semana)


class ProgramacionSemanalPDFView(LoginRequiredMixin, RoleRequiredMixin, View):
    """Export PDF imprimible de la programación semanal (vista tabular plana,
    sin merges — regla de negocio #3 del cliente). Motor WeasyPrint (ya en
    ``requirements/base.txt`` y con libs nativas en el Dockerfile de prod)."""

    allowed_roles = ROLES_CUADRILLAS

    def get(self, request, anio, semana):
        anio, semana = int(anio), int(semana)
        contexto = _contexto_semana(anio, semana)
        contexto["generado"] = timezone.now()
        html = render_to_string(
            "cuadrillas/programacion_semanal_pdf.html", contexto, request=request
        )
        try:
            from weasyprint import HTML

            pdf_bytes = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
        except Exception as e:  # pragma: no cover - depende de libs nativas
            logger.exception("Error generando PDF de programación semanal")
            return HttpResponse(
                f"No se pudo generar el PDF de la programación semanal: {e}",
                status=500,
            )
        resp = HttpResponse(pdf_bytes, content_type="application/pdf")
        resp["Content-Disposition"] = (
            f'inline; filename="programacion_semana_{semana:02d}_{anio}.pdf"'
        )
        return resp


urlpatterns = [
    path("semanal/", ProgramacionSemanalIndexView.as_view(), name="semanal_index"),
    path(
        "semanal/<int:anio>/<int:semana>/",
        ProgramacionSemanalGridView.as_view(),
        name="semanal_grid",
    ),
    path(
        "semanal/<int:anio>/<int:semana>/duplicar/",
        ProgramacionSemanalDuplicarView.as_view(),
        name="semanal_duplicar",
    ),
    path(
        "semanal/<int:anio>/<int:semana>/pdf/",
        ProgramacionSemanalPDFView.as_view(),
        name="semanal_pdf",
    ),
]
