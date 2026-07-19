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
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import path, reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.core.mixins import RoleRequiredMixin

from .models import Cuadrilla, CuadrillaMiembro, NovedadPersonalSemana, PersonalCuadrilla, Vehiculo

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
    """Cuadrillas (bloques de actividad) ACTIVAS de una semana, con miembros
    precargados. Se filtra ``activa=True`` igual que ``CuadrillaListView`` — un
    bloque dado de baja (soft-delete) no debe reaparecer en la programación
    semanal ni duplicarse."""
    return (
        Cuadrilla.objects.filter(codigo__startswith=_prefijo(anio, semana), activa=True)
        .select_related("linea_asignada", "vehiculo", "supervisor", "tipo_actividad", "tramo")
        .prefetch_related("miembros__usuario", "miembros__rol_cuadrilla")
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

    Issue #188 (A2): agrega ``id``/FKs crudos (para hx-post/selects
    precargados del grid editable) y enriquece cada miembro con
    ``miembro_pk``/``celular``/``placa_vehiculo``/``es_conductor`` (A5-A7).
    El ``celular`` vive en el maestro ``PersonalCuadrilla`` (A1/A5), NO en
    ``Usuario.telefono`` (ese es un concepto distinto, poblado solo por los
    importers S18) — se resuelve por ``documento`` en un único query batched
    (evita N+1 por miembro).
    """
    activos = [m for m in cuadrilla.miembros.all() if m.activo]
    documentos = [
        getattr(m.usuario, "documento", "") for m in activos if getattr(m.usuario, "documento", "")
    ]
    celulares_por_documento = dict(
        PersonalCuadrilla.objects.filter(documento__in=documentos).values_list(
            "documento", "celular"
        )
    )
    miembros = [
        {
            "miembro_pk": str(m.pk),
            "usuario_pk": str(m.usuario_id),
            "nombre": (m.usuario.get_full_name() or m.usuario.get_username()),
            "documento": getattr(m.usuario, "documento", "") or "",
            "celular": celulares_por_documento.get(getattr(m.usuario, "documento", ""), "") or "",
            "rol": m.get_rol_cuadrilla_display(),
            "rol_codigo": m.rol_cuadrilla_id,
            "cargo": m.get_cargo_display(),
            "cargo_codigo": m.cargo,
            "es_jt": m.cargo == "JT_CTA",
            "es_conductor": m.rol_cuadrilla_id == "CONDUCTOR",
            "placa_vehiculo": m.placa_vehiculo or "",
        }
        for m in activos
    ]
    miembros.sort(key=lambda x: (not x["es_jt"], x["nombre"]))
    return {
        "id": str(cuadrilla.id),
        "codigo": cuadrilla.codigo,
        "nombre": cuadrilla.nombre,
        "tipo_actividad_id": str(cuadrilla.tipo_actividad_id) if cuadrilla.tipo_actividad_id else "",
        "tipo_actividad": getattr(cuadrilla.tipo_actividad, "nombre", "") or "",
        "linea_id": str(cuadrilla.linea_asignada_id) if cuadrilla.linea_asignada_id else "",
        "linea": getattr(cuadrilla.linea_asignada, "codigo", "") or "",
        "tramo_id": str(cuadrilla.tramo_id) if cuadrilla.tramo_id else "",
        "tramo": getattr(cuadrilla.tramo, "codigo", "") or "",
        "tramo_nombre": getattr(cuadrilla.tramo, "nombre", "") or "",
        "vehiculo_id": str(cuadrilla.vehiculo_id) if cuadrilla.vehiculo_id else "",
        "vehiculo": getattr(cuadrilla.vehiculo, "placa", "") or "",
        "supervisor_id": str(cuadrilla.supervisor_id) if cuadrilla.supervisor_id else "",
        "fecha": cuadrilla.fecha,
        "observaciones": cuadrilla.observaciones or "",
        "miembros": miembros,
    }


def _siguiente_codigo_bloque(anio, semana, nombre=""):
    """Genera el próximo código ``WW-YYYY-NNNN-XXX`` para un bloque nuevo de la
    semana (issue #188, A3), reusando el mismo formato de
    ``ProgramacionS18CuadrillaImporter._generar_codigo``. Busca el número más
    alto YA usado en la semana (no solo ``.count()`` — evita colisión si algún
    bloque fue borrado) y le suma 1."""
    import re

    prefijo = _prefijo(anio, semana)
    max_num = 0
    for codigo in Cuadrilla.objects.filter(codigo__startswith=prefijo).values_list(
        "codigo", flat=True
    ):
        partes = codigo.split("-")
        if len(partes) >= 3:
            try:
                max_num = max(max_num, int(partes[2]))
            except ValueError:
                continue
    iniciales = re.sub(r"[^A-Z]", "", (nombre or "").upper())[:3] or "BLQ"
    return f"{prefijo}{max_num + 1:04d}-{iniciales}"


def _anio_semana_desde_codigo(codigo):
    """Extrae (anio, semana) del prefijo ``WW-YYYY-`` de un código de bloque
    (issue #188, A4) — mismo criterio de ``CuadrillaListView._parse_semana``."""
    partes = (codigo or "").split("-")
    try:
        if len(partes) >= 2:
            semana, anio = int(partes[0]), int(partes[1])
            if 1 <= semana <= 53 and 2000 <= anio <= 2100:
                return anio, semana
    except (ValueError, IndexError):
        pass
    return None, None


def _post_a_bloque_dict(request, fecha=None, codigo=""):
    """Reconstruye un dict "tipo _bloque_a_dict" a partir de un POST fallido
    (issue #188, A3/A4) — para reusar _bloque_form.html/_bloque_card.html y NO
    perder lo que el usuario ya había llenado cuando el submit falla por
    validación."""
    return {
        "id": "",
        "codigo": codigo,
        "nombre": (request.POST.get("nombre") or "").strip(),
        "tipo_actividad_id": request.POST.get("tipo_actividad") or "",
        "linea_id": request.POST.get("linea_asignada") or "",
        "tramo_id": request.POST.get("tramo") or "",
        "tramo": "",
        "tramo_nombre": "",
        "vehiculo_id": request.POST.get("vehiculo") or "",
        "supervisor_id": request.POST.get("supervisor") or "",
        "fecha": fecha,
        "observaciones": (request.POST.get("observaciones") or "").strip(),
    }


def _choices_form_bloque():
    """Catálogos activos para el form de bloque (crear/editar, issue #188
    A2-A4): tipo de actividad, línea, vehículo, supervisor. El propio Tramo
    se resuelve por cascada AJAX dependiente de la línea (A3) — no vive acá.
    También incluye el datalist de Colaboradores activos (A5) que alimenta
    el autocompletado de "agregar personal" en cada card."""
    from apps.actividades.models import TipoActividad
    from apps.lineas.models import Linea
    from apps.usuarios.models import Usuario

    return {
        "tipos_actividad_bloque": TipoActividad.objects.filter(activo=True).order_by("nombre"),
        "lineas_bloque": Linea.objects.filter(activa=True).order_by("codigo"),
        "vehiculos_bloque": Vehiculo.objects.filter(activo=True).order_by("placa"),
        "supervisores_bloque": Usuario.objects.filter(rol="supervisor", is_active=True).order_by(
            "first_name"
        ),
        "personal_disponible_datalist": PersonalCuadrilla.objects.filter(activo=True).order_by(
            "nombre"
        ),
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


def _semana_mas_reciente_con_datos():
    """(anio, semana) de la programación con datos más reciente, o la semana
    ISO actual si no hay ninguna cargada. Issue #188 (A9): extraído de
    ``ProgramacionSemanalIndexView.get()`` para reusarlo también desde
    ``CuadrillaListView`` (pantalla fusionada) cuando no viene un ``semana``
    explícito en la URL."""
    codigos = Cuadrilla.objects.filter(
        codigo__regex=r"^[0-9]{2}-[0-9]{4}-", activa=True
    ).values_list("codigo", flat=True)
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
    return mejor[0], mejor[1]


class ProgramacionSemanalIndexView(LoginRequiredMixin, RoleRequiredMixin, View):
    """``/cuadrillas/semanal/`` → redirige a la semana con datos más reciente
    (o a la semana ISO actual si no hay ninguna programación cargada)."""

    allowed_roles = ROLES_CUADRILLAS

    def get(self, request):
        anio, semana = _semana_mas_reciente_con_datos()
        return redirect("cuadrillas:semanal_grid", anio=anio, semana=semana)


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
        # Issue #188 (A2): choices del form de bloque (crear/editar), reusadas
        # por _bloque_form.html vía include. La cascada Línea→Tramo real
        # (AJAX) llega en A3 — acá solo se precargan los catálogos activos.
        context.update(_choices_form_bloque())
        return context


class TramosPorLineaAPIView(LoginRequiredMixin, View):
    """GET /cuadrillas/api/tramos-por-linea/?linea_id=<uuid> (issue #188, A3).

    Cascada Línea→Tramo: devuelve <option> ya renderizados para reemplazar el
    innerHTML del select #id_tramo del form de bloque (HTMX hx-swap=innerHTML).
    Acepta tanto ``linea_id`` como ``linea_asignada`` (el select del form de
    bloque usa este último `name`; HTMX serializa el form completo al hacer
    hx-get sobre un elemento dentro de un <form>)."""

    def get(self, request, *args, **kwargs):
        from apps.lineas.models import Tramo

        linea_id = (request.GET.get("linea_id") or request.GET.get("linea_asignada") or "").strip()
        html = '<option value="">— Sin tramo —</option>'
        if linea_id:
            tramos = Tramo.objects.filter(linea_id=linea_id).order_by("codigo")
            for t in tramos:
                html += f'<option value="{t.pk}">{t.codigo} - {t.nombre}</option>'
        return HttpResponse(html, content_type="text/html")


class ProgramacionSemanalBloqueCrearView(LoginRequiredMixin, RoleRequiredMixin, View):
    """POST /cuadrillas/semanal/<anio>/<semana>/bloque/crear/ (issue #188, A3).

    Crea un bloque (Cuadrilla) DENTRO del grid semanal, sin recargar la
    página. Éxito: responde con un swap out-of-band que agrega la card nueva
    al final de #bloques-lista + el form de creación reseteado (mismo
    request, para que el usuario pueda seguir creando bloques). Falla:
    re-renderiza el mismo form con el error inline, preservando lo ya
    llenado (`_post_a_bloque_dict`)."""

    allowed_roles = ROLES_CUADRILLAS

    def post(self, request, anio, semana):
        anio, semana = int(anio), int(semana)
        nombre = (request.POST.get("nombre") or "").strip()
        if not nombre:
            return self._form_con_error(request, anio, semana, "El nombre del bloque es obligatorio.")

        fecha_str = (request.POST.get("fecha") or "").strip()
        fecha = None
        if fecha_str:
            try:
                fecha = date.fromisoformat(fecha_str)
            except ValueError:
                return self._form_con_error(request, anio, semana, "La fecha ingresada no es válida.")

        codigo = _siguiente_codigo_bloque(anio, semana, nombre)
        try:
            with transaction.atomic():
                cuadrilla = Cuadrilla.objects.create(
                    codigo=codigo,
                    nombre=nombre,
                    tipo_actividad_id=request.POST.get("tipo_actividad") or None,
                    linea_asignada_id=request.POST.get("linea_asignada") or None,
                    tramo_id=request.POST.get("tramo") or None,
                    vehiculo_id=request.POST.get("vehiculo") or None,
                    supervisor_id=request.POST.get("supervisor") or None,
                    observaciones=(request.POST.get("observaciones") or "").strip(),
                    fecha=fecha,
                    activa=True,
                )
        except Exception as e:
            logger.exception("Error creando bloque de programación semanal (issue #188)")
            return self._form_con_error(request, anio, semana, f"Error al crear el bloque: {e}")

        card_html = render_to_string(
            "cuadrillas/partials/_bloque_card.html",
            {**_choices_form_bloque(), "b": _bloque_a_dict(cuadrilla), "anio": anio, "semana": semana},
            request=request,
        )
        form_html = self._render_form(request, anio, semana)
        return HttpResponse(f'<div hx-swap-oob="beforeend:#bloques-lista">{card_html}</div>{form_html}')

    def _render_form(self, request, anio, semana, form_error=None, valores=None):
        contexto = {
            **_choices_form_bloque(),
            "b": valores,
            "anio": anio,
            "semana": semana,
            "form_id": "form-nuevo-bloque",
            "post_url": reverse("cuadrillas:semanal_bloque_crear", args=[anio, semana]),
            "cerrar_expr": "creando=false",
            "form_error": form_error,
        }
        return render_to_string("cuadrillas/partials/_bloque_form.html", contexto, request=request)

    def _form_con_error(self, request, anio, semana, mensaje):
        valores = _post_a_bloque_dict(request)
        html = self._render_form(request, anio, semana, form_error=mensaje, valores=valores)
        return HttpResponse(html, status=400)


class ProgramacionSemanalBloqueEditarView(LoginRequiredMixin, RoleRequiredMixin, View):
    """POST /cuadrillas/semanal/bloque/<uuid:pk>/editar/ (issue #188, A4).

    Mismos campos de A3 sobre un bloque YA existente. Éxito: reemplaza el
    card completo (outerHTML) con la vista de solo lectura actualizada —
    reinicia el `x-data` de Alpine (nuevo nodo del DOM), sin necesidad de
    tocar el estado ``editando`` a mano. Falla: reemplaza el card con el
    mismo form de edición abierto (``editando_inicial=True``) + error
    inline, preservando lo ya llenado."""

    allowed_roles = ROLES_CUADRILLAS

    def post(self, request, pk):
        cuadrilla = get_object_or_404(Cuadrilla, pk=pk)
        anio, semana = _anio_semana_desde_codigo(cuadrilla.codigo)

        nombre = (request.POST.get("nombre") or "").strip()
        if not nombre:
            return self._card_con_error(request, cuadrilla, anio, semana, "El nombre del bloque es obligatorio.")

        fecha_str = (request.POST.get("fecha") or "").strip()
        fecha = None
        if fecha_str:
            try:
                fecha = date.fromisoformat(fecha_str)
            except ValueError:
                return self._card_con_error(request, cuadrilla, anio, semana, "La fecha ingresada no es válida.")

        try:
            with transaction.atomic():
                cuadrilla.nombre = nombre
                cuadrilla.tipo_actividad_id = request.POST.get("tipo_actividad") or None
                cuadrilla.linea_asignada_id = request.POST.get("linea_asignada") or None
                cuadrilla.tramo_id = request.POST.get("tramo") or None
                cuadrilla.vehiculo_id = request.POST.get("vehiculo") or None
                cuadrilla.supervisor_id = request.POST.get("supervisor") or None
                cuadrilla.observaciones = (request.POST.get("observaciones") or "").strip()
                cuadrilla.fecha = fecha
                cuadrilla.save()
        except Exception as e:
            logger.exception("Error editando bloque de programación semanal (issue #188)")
            return self._card_con_error(request, cuadrilla, anio, semana, f"Error al guardar: {e}")

        cuadrilla.refresh_from_db()
        html = render_to_string(
            "cuadrillas/partials/_bloque_card.html",
            {**_choices_form_bloque(), "b": _bloque_a_dict(cuadrilla), "anio": anio, "semana": semana},
            request=request,
        )
        return HttpResponse(html)

    def _card_con_error(self, request, cuadrilla, anio, semana, mensaje):
        valores = _post_a_bloque_dict(request, codigo=cuadrilla.codigo)
        valores["id"] = str(cuadrilla.id)
        html = render_to_string(
            "cuadrillas/partials/_bloque_card.html",
            {
                **_choices_form_bloque(),
                "b": valores,
                "anio": anio,
                "semana": semana,
                "editando_inicial": True,
                "form_error": mensaje,
            },
            request=request,
        )
        return HttpResponse(html, status=400)


class ProgramacionSemanalMiembroAgregarView(LoginRequiredMixin, RoleRequiredMixin, View):
    """POST /cuadrillas/semanal/bloque/<uuid:pk>/miembro/agregar/ (issue #188,
    A5). Agrega personal a un bloque REUSANDO el patrón probado de
    ``CuadrillaMiembroAddView``/``detalle.html``: documento + autocompletado
    AJAX vía ``PersonalCuadrillaAPIView`` (ahora con ``celular``, A5) +
    ``resolver_o_crear_usuario`` (extraído a ``services.py``). Si el ``Cargo``
    elegido es ``CONDUCTOR``, exige placa manual. Éxito y falla responden
    SIEMPRE el card completo (outerHTML) — en falla, con el mini-form de
    "agregar personal" reabierto (``agregar_state``) y el mensaje inline."""

    allowed_roles = ROLES_CUADRILLAS

    def post(self, request, pk):
        from .services import resolver_o_crear_usuario

        cuadrilla = get_object_or_404(Cuadrilla, pk=pk)
        anio, semana = _anio_semana_desde_codigo(cuadrilla.codigo)
        documento = (request.POST.get("documento") or "").strip()
        cargo_jerarquico = request.POST.get("cargo") or CuadrillaMiembro.CargoJerarquico.MIEMBRO
        if cargo_jerarquico not in dict(CuadrillaMiembro.CargoJerarquico.choices):
            cargo_jerarquico = CuadrillaMiembro.CargoJerarquico.MIEMBRO
        placa_vehiculo = (request.POST.get("placa_vehiculo") or "").strip()

        if not documento:
            return self._card_con_error(
                request, cuadrilla, anio, semana,
                "Debe ingresar el documento de un colaborador.",
                agregar_state={"open": True, "documento": documento},
            )

        personal = PersonalCuadrilla.objects.filter(documento=documento, activo=True).first()
        if not personal:
            return self._card_con_error(
                request, cuadrilla, anio, semana,
                f'No se encontró un colaborador activo con documento "{documento}". '
                'Verifique el documento o dé de alta el colaborador en el maestro.',
                agregar_state={"open": True, "documento": documento},
            )

        rol_id = personal.rol_cuadrilla_id
        es_conductor = rol_id == "CONDUCTOR"
        if es_conductor and not placa_vehiculo:
            return self._card_con_error(
                request, cuadrilla, anio, semana,
                "Debe ingresar la placa del vehículo.",
                agregar_state={
                    "open": True,
                    "documento": documento,
                    "nombre_display": personal.nombre,
                    "es_conductor": True,
                },
            )

        usuario = resolver_o_crear_usuario(personal)

        # Issue #188 (A7): la unicidad cuadrilla+usuario+activo YA existe a
        # nivel de BD (unique_together, ver models_base.py) — este pre-check
        # es SOLO superficie UX: convierte lo que sería un IntegrityError
        # crudo en un aviso inline claro, ANTES de intentar el insert. Misma
        # persona en un bloque DISTINTO de la semana no cae acá (el filtro
        # está scoped a `cuadrilla`), sigue siendo válido.
        if CuadrillaMiembro.objects.filter(cuadrilla=cuadrilla, usuario=usuario, activo=True).exists():
            return self._card_con_error(
                request, cuadrilla, anio, semana,
                f"{usuario.get_full_name()} ya es miembro activo.",
                agregar_state={
                    "open": True,
                    "documento": documento,
                    "nombre_display": personal.nombre,
                    "es_conductor": es_conductor,
                    "placa": placa_vehiculo,
                },
            )

        try:
            with transaction.atomic():
                CuadrillaMiembro.objects.create(
                    cuadrilla=cuadrilla,
                    usuario=usuario,
                    rol_cuadrilla_id=rol_id,
                    cargo=cargo_jerarquico,
                    costo_dia=0,
                    fecha_inicio=date.today(),
                    placa_vehiculo=placa_vehiculo if es_conductor else "",
                )
        except Exception as e:
            logger.exception("Error agregando personal al bloque (issue #188)")
            return self._card_con_error(
                request, cuadrilla, anio, semana,
                f"Error al agregar el colaborador: {e}",
                agregar_state={
                    "open": True,
                    "documento": documento,
                    "nombre_display": personal.nombre,
                    "es_conductor": es_conductor,
                    "placa": placa_vehiculo,
                },
            )

        cuadrilla.refresh_from_db()
        html = render_to_string(
            "cuadrillas/partials/_bloque_card.html",
            {**_choices_form_bloque(), "b": _bloque_a_dict(cuadrilla), "anio": anio, "semana": semana},
            request=request,
        )
        return HttpResponse(html)

    def _card_con_error(self, request, cuadrilla, anio, semana, mensaje, agregar_state):
        agregar_state = {**agregar_state, "error": mensaje}
        html = render_to_string(
            "cuadrillas/partials/_bloque_card.html",
            {
                **_choices_form_bloque(),
                "b": _bloque_a_dict(cuadrilla),
                "anio": anio,
                "semana": semana,
                "agregar_state": agregar_state,
            },
            request=request,
        )
        return HttpResponse(html, status=400)


class ProgramacionSemanalMiembroQuitarView(LoginRequiredMixin, RoleRequiredMixin, View):
    """POST /cuadrillas/semanal/bloque/<uuid:pk>/miembro/<uuid:miembro_pk>/quitar/
    (issue #188, A6). Soft-remove: marca ``activo=False`` + ``fecha_fin`` (NO
    DELETE físico — mismo patrón que ``CuadrillaMiembroRemoveView``).
    Idempotente: si el miembro ya estaba inactivo, no rompe — simplemente
    devuelve el card sin cambios."""

    allowed_roles = ROLES_CUADRILLAS

    def post(self, request, pk, miembro_pk):
        cuadrilla = get_object_or_404(Cuadrilla, pk=pk)
        anio, semana = _anio_semana_desde_codigo(cuadrilla.codigo)

        miembro = CuadrillaMiembro.objects.filter(pk=miembro_pk, cuadrilla=cuadrilla).first()
        if miembro and miembro.activo:
            miembro.activo = False
            miembro.fecha_fin = date.today()
            miembro.save(update_fields=["activo", "fecha_fin", "updated_at"])

        cuadrilla.refresh_from_db()
        html = render_to_string(
            "cuadrillas/partials/_bloque_card.html",
            {**_choices_form_bloque(), "b": _bloque_a_dict(cuadrilla), "anio": anio, "semana": semana},
            request=request,
        )
        return HttpResponse(html)


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
    # Issue #188 (A3) — grid editable in-place: crear bloque + cascada Línea→Tramo.
    path(
        "semanal/<int:anio>/<int:semana>/bloque/crear/",
        ProgramacionSemanalBloqueCrearView.as_view(),
        name="semanal_bloque_crear",
    ),
    path("api/tramos-por-linea/", TramosPorLineaAPIView.as_view(), name="tramos_por_linea_api"),
    # Issue #188 (A4) — editar bloque existente in-place.
    path(
        "semanal/bloque/<uuid:pk>/editar/",
        ProgramacionSemanalBloqueEditarView.as_view(),
        name="semanal_bloque_editar",
    ),
    # Issue #188 (A5) — agregar personal a un bloque in-place.
    path(
        "semanal/bloque/<uuid:pk>/miembro/agregar/",
        ProgramacionSemanalMiembroAgregarView.as_view(),
        name="semanal_miembro_agregar",
    ),
    # Issue #188 (A6) — quitar/inactivar personal de un bloque in-place.
    path(
        "semanal/bloque/<uuid:pk>/miembro/<uuid:miembro_pk>/quitar/",
        ProgramacionSemanalMiembroQuitarView.as_view(),
        name="semanal_miembro_quitar",
    ),
]
