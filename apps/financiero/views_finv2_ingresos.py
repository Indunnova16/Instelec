"""Emisión, consulta, PDF y cobranza de facturas de ingreso (#249)."""

from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.generic import DetailView, ListView, TemplateView

from apps.core.mixins import RoleRequiredMixin
from apps.core.models_roles import RoleModuloPermiso
from apps.core.permissions import SUBMODULO_FIN_FACTURAS_INGRESOS, user_nivel_acceso_submodulo

from .forms_finv2_ingresos import (
    FacturaIngresoForm,
    LineaFacturaIngresoFormSet,
    PagoFacturaIngresoForm,
)
from .importers_facturas_ingreso import columnas_para, validar_filas
from .models import (
    AuditoriaFacturaIngreso,
    CargaFacturasIngreso,
    CicloFacturacion,
    Cliente,
    LineaFacturaIngreso,
    MetodoPago,
    Presupuesto,
)
from apps.contratos.models import Contrato
from .services_finv2_ingresos import facturacion_real_vs_meta, generar_numero_factura


def _filtrar_listado(queryset, params):
    """Filtros de listado (#249 gap 5): estado, período, cliente, rango de valor.

    "Vencida" no es un estado persistido del modelo (`CicloFacturacion.Estado`
    va de informe a pago recibido) -- es derivado: no pagada y con fecha de
    vencimiento (fecha_factura + plazo_pago_dias) ya pasada. Se calcula con
    SQL (ExpressionWrapper) para no romper el queryset en una lista Python y
    perder select_related/orden ante el resto de filtros combinables.
    """
    estado = params.get("estado")
    if estado and estado != "TODAS":
        if estado == "VENCIDA":
            from django.db.models import DateField, DurationField, ExpressionWrapper, F, IntegerField
            from django.db.models.functions import Cast

            hoy = timezone.localdate()
            queryset = (
                queryset.exclude(estado=CicloFacturacion.Estado.PAGO_RECIBIDO)
                .filter(fecha_factura__isnull=False, plazo_pago_dias__isnull=False)
                .annotate(
                    # Backend gotcha (#249): plazo_pago_dias es PositiveIntegerField.
                    # El chequeo de Django para F(int)*timedelta en SQLite
                    # (django/db/models/expressions.py DurationExpression.as_sqlite)
                    # solo permite el string literal "IntegerField" -- NO sus
                    # subtipos ("PositiveIntegerField" incluido) -- y rechaza la
                    # multiplicación con "Invalid arguments for operator *", aunque
                    # en Postgres (prod) funciona sin problema. Cast() explícito a
                    # IntegerField plano antes de multiplicar, portable en ambos
                    # backends.
                    _plazo_int=Cast(F("plazo_pago_dias"), output_field=IntegerField())
                )
                .annotate(
                    _plazo_duracion=ExpressionWrapper(
                        F("_plazo_int") * timezone.timedelta(days=1),
                        output_field=DurationField(),
                    )
                )
                .annotate(
                    _vencimiento=ExpressionWrapper(
                        F("fecha_factura") + F("_plazo_duracion"),
                        output_field=DateField(),
                    )
                )
                .filter(_vencimiento__lt=hoy)
            )
        else:
            queryset = queryset.filter(estado=estado)
    cliente_id = params.get("cliente")
    if cliente_id:
        queryset = queryset.filter(cliente_id=cliente_id)
    fecha_desde = params.get("fecha_desde")
    if fecha_desde:
        queryset = queryset.filter(fecha_factura__gte=fecha_desde)
    fecha_hasta = params.get("fecha_hasta")
    if fecha_hasta:
        queryset = queryset.filter(fecha_factura__lte=fecha_hasta)
    valor_min = params.get("valor_min")
    if valor_min:
        try:
            queryset = queryset.filter(total__gte=Decimal(valor_min))
        except (ValueError, ArithmeticError):
            pass
    valor_max = params.get("valor_max")
    if valor_max:
        try:
            queryset = queryset.filter(total__lte=Decimal(valor_max))
        except (ValueError, ArithmeticError):
            pass
    return queryset


class IngresoListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    template_name = "financiero/facturas_ingresos_lista.html"
    context_object_name = "facturas"
    required_submodulo = SUBMODULO_FIN_FACTURAS_INGRESOS

    def get_queryset(self):
        queryset = (
            CicloFacturacion.objects.filter(numero_secuencial__isnull=False)
            .select_related(
                "cliente",
                "presupuesto__linea",
            )
            .order_by("-fecha_factura", "-numero_secuencial")
        )
        return _filtrar_listado(queryset, self.request.GET)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["clientes"] = Cliente.objects.filter(activo=True).order_by("nombre")
        context["estados"] = CicloFacturacion.Estado.choices
        context["filtros"] = self.request.GET
        return context


class IngresoCreateView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    template_name = "financiero/factura_ingreso_form.html"
    required_submodulo = SUBMODULO_FIN_FACTURAS_INGRESOS

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or FacturaIngresoForm(
            initial={"fecha_factura": timezone.localdate()}
        )
        context["lineas_formset"] = kwargs.get("lineas_formset") or LineaFacturaIngresoFormSet(
            prefix="lineas"
        )
        return context

    def post(self, request, *args, **kwargs):
        form = FacturaIngresoForm(request.POST)
        lineas = LineaFacturaIngresoFormSet(request.POST, prefix="lineas")
        if not (form.is_valid() and lineas.is_valid()):
            messages.error(request, "Revise los datos de la factura y sus líneas.")
            return self.render_to_response(self.get_context_data(form=form, lineas_formset=lineas))
        try:
            with transaction.atomic():
                factura = form.save(commit=False)
                factura.numero_factura = generar_numero_factura(factura.fecha_factura)
                factura.numero_secuencial = int(factura.numero_factura.rsplit("-", 1)[1])
                factura.estado = CicloFacturacion.Estado.FACTURA_EMITIDA
                factura.creado_por = request.user.get_username()
                factura.save()
                lineas.instance = factura
                items = lineas.save(commit=False)
                subtotal = Decimal("0.00")
                for item in items:
                    item.total = item.cantidad * item.valor_unitario
                    subtotal += item.total
                    item.save()
                for item in lineas.deleted_objects:
                    item.delete()
                iva = (subtotal * Decimal("0.19")).quantize(Decimal("0.01"))
                factura.subtotal = subtotal
                factura.iva = iva
                factura.total = subtotal + iva
                factura.monto_facturado = factura.total
                factura.save(
                    update_fields=["subtotal", "iva", "total", "monto_facturado", "updated_at"]
                )
        except IntegrityError:
            messages.error(request, "Otra emisión tomó ese consecutivo. Intente nuevamente.")
            return self.render_to_response(self.get_context_data(form=form, lineas_formset=lineas))
        messages.success(request, f"Factura {factura.numero_factura} emitida correctamente.")
        if factura.presupuesto_id and facturacion_real_vs_meta(factura.presupuesto)["supera_meta"]:
            messages.warning(
                request,
                "La facturación real asociada supera la meta del presupuesto; la factura fue emitida.",
            )
        return redirect("financiero:factura_ingreso_detalle", pk=factura.pk)


class IngresoContextoView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Opciones dependientes del contexto comercial para el formulario de emisión."""

    required_submodulo = SUBMODULO_FIN_FACTURAS_INGRESOS

    def get(self, request, *args, **kwargs):
        cliente = Cliente.objects.filter(pk=request.GET.get("cliente"), activo=True).first()
        proyecto_id = request.GET.get("proyecto")
        if not cliente:
            return JsonResponse({"proyectos": [], "presupuestos": []})
        proyectos = Contrato.objects.filter(
            estado=Contrato.Estado.ACTIVO, cliente__iexact=cliente.nombre
        )
        presupuestos = Presupuesto.objects.none()
        if proyecto_id:
            presupuestos = Presupuesto.objects.filter(cliente=cliente, proyecto_id=proyecto_id)
            fecha = request.GET.get("fecha")
            try:
                anio, mes = map(int, fecha.split("-")[:2])
                presupuestos = presupuestos.filter(anio=anio, mes=mes)
            except (AttributeError, TypeError, ValueError):
                pass
        return JsonResponse({
            "proyectos": [{"id": str(item.pk), "label": str(item)} for item in proyectos],
            "presupuestos": [{"id": str(item.pk), "label": str(item)} for item in presupuestos.select_related("linea")],
        })


class IngresoDetailView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    template_name = "financiero/factura_ingreso_detalle.html"
    context_object_name = "factura"
    required_submodulo = SUBMODULO_FIN_FACTURAS_INGRESOS

    def get_queryset(self):
        return (
            CicloFacturacion.objects.filter(numero_secuencial__isnull=False)
            .select_related("cliente", "proyecto", "presupuesto")
            .prefetch_related(
                "lineas_factura", "pagos_factura__banco", "pagos_factura__metodo_pago"
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pagado = sum((p.monto for p in self.object.pagos_factura.all()), Decimal("0.00"))
        context["saldo_pendiente"] = max(Decimal("0.00"), self.object.total - pagado)
        context["pago_form"] = kwargs.get("pago_form") or PagoFacturaIngresoForm(
            saldo=context["saldo_pendiente"]
        )
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        pagado = sum((p.monto for p in self.object.pagos_factura.all()), Decimal("0.00"))
        saldo = max(Decimal("0.00"), self.object.total - pagado)
        form = PagoFacturaIngresoForm(request.POST, saldo=saldo)
        if not form.is_valid():
            messages.error(request, "No fue posible registrar el pago.")
            return self.render_to_response(self.get_context_data(pago_form=form))
        estado_anterior = self.object.estado
        with transaction.atomic():
            pago = form.save(commit=False)
            pago.ciclo = self.object
            pago.registrado_por = request.user.get_username()
            pago.save()
            self.object.monto_pagado = pagado + pago.monto
            if self.object.monto_pagado >= self.object.total:
                self.object.estado = CicloFacturacion.Estado.PAGO_RECIBIDO
                self.object.fecha_pago = pago.fecha
            self.object.save(update_fields=["monto_pagado", "estado", "fecha_pago", "updated_at"])
            if self.object.estado != estado_anterior:
                AuditoriaFacturaIngreso.objects.create(
                    ciclo=self.object,
                    campo="estado",
                    valor_anterior=estado_anterior,
                    valor_nuevo=self.object.estado,
                    usuario=request.user.get_username(),
                )
        messages.success(request, "Pago registrado correctamente.")
        return redirect("financiero:factura_ingreso_detalle", pk=self.object.pk)


class IngresoPdfView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    required_submodulo = SUBMODULO_FIN_FACTURAS_INGRESOS

    def get(self, request, pk, *args, **kwargs):
        factura = (
            CicloFacturacion.objects.filter(numero_secuencial__isnull=False)
            .select_related("cliente", "proyecto", "presupuesto")
            .prefetch_related("lineas_factura")
            .filter(pk=pk)
            .first()
        )
        if not factura:
            raise Http404("La factura solicitada no existe.")
        html = render_to_string(
            "financiero/factura_ingreso_pdf.html", {"factura": factura, "request": request}
        )
        try:
            from weasyprint import HTML

            pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
        except (ImportError, OSError) as error:
            return HttpResponse(
                f"No fue posible generar el PDF: {error}", status=503, content_type="text/plain"
            )
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{factura.numero_factura}.pdf"'
        return response


class ImportarFacturasIngresoView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Carga masiva de facturas de ingreso con UPSERT (#249 gap 3).

    Mismo patrón preview→confirmar de `ImportarTercerosView` (#261/#262):
    "crear si es nuevo, actualizar con auditoría si ya existe" en vez de
    rechazar como duplicado. Clave de upsert: (cliente_nit, fecha_factura) --
    la carga no captura número de factura, lo asigna el sistema con el mismo
    consecutivo global de la emisión manual.
    """

    template_name = "financiero/facturas_ingresos_importar.html"
    required_submodulo = SUBMODULO_FIN_FACTURAS_INGRESOS

    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        if self.request.user.is_superuser:
            return True
        nivel = user_nivel_acceso_submodulo(self.request.user, self.required_submodulo)
        return nivel == RoleModuloPermiso.VER_EDITAR

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "columnas": columnas_para(),
            "historial": CargaFacturasIngreso.objects.all()[:10],
            "preview": self.request.session.get("importacion_facturas_ingreso"),
        })
        return context

    def get(self, request, *args, **kwargs):
        if request.GET.get("plantilla") == "csv":
            respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
            respuesta["Content-Disposition"] = 'attachment; filename="plantilla_facturas_ingreso.csv"'
            respuesta.write(",".join(columnas_para()) + "\n")
            return respuesta
        return self.render_to_response(self.get_context_data())

    def post(self, request, *args, **kwargs):
        clave = "importacion_facturas_ingreso"
        if request.POST.get("confirmar"):
            preview = request.session.get(clave)
            if not preview or preview.get("errores"):
                messages.error(request, "No hay una vista previa válida para confirmar.")
                return redirect(request.path)
            creadas = actualizadas = 0
            with transaction.atomic():
                for fila in preview["filas"]:
                    fecha_factura = date.fromisoformat(fila["fecha_factura"])
                    valor_neto = Decimal(fila["valor_neto"])
                    # `metodo_pago` de la carga es informativo (la factura no
                    # tiene FK a MetodoPago -- eso vive en PagoFacturaIngreso,
                    # que se registra cuando se cobra, no al facturar). Se
                    # conserva como texto en observaciones para no perder el
                    # dato capturado en el archivo.
                    if fila["accion_carga"] == "actualizar":
                        ciclo = CicloFacturacion.objects.select_for_update().get(
                            pk=fila["_ciclo_id"]
                        )
                        antes = {
                            "concepto": ciclo.lineas_factura.first().descripcion
                            if ciclo.lineas_factura.exists()
                            else "",
                            "subtotal": str(ciclo.subtotal),
                            "observaciones": ciclo.observaciones,
                        }
                        linea = ciclo.lineas_factura.first()
                        if linea:
                            linea.descripcion = fila["concepto"]
                            linea.cantidad = Decimal("1")
                            linea.valor_unitario = valor_neto
                            linea.total = valor_neto
                            linea.save()
                        else:
                            LineaFacturaIngreso.objects.create(
                                ciclo=ciclo, descripcion=fila["concepto"],
                                cantidad=Decimal("1"), valor_unitario=valor_neto, total=valor_neto,
                            )
                        iva = (valor_neto * Decimal("0.19")).quantize(Decimal("0.01"))
                        ciclo.subtotal = valor_neto
                        ciclo.iva = iva
                        ciclo.total = valor_neto + iva
                        ciclo.monto_facturado = ciclo.total
                        ciclo.observaciones = fila["observaciones"]
                        ciclo.save()
                        for campo, valor_nuevo in (
                            ("concepto", fila["concepto"]),
                            ("subtotal", str(ciclo.subtotal)),
                            ("observaciones", fila["observaciones"]),
                        ):
                            if antes.get(campo, "") != valor_nuevo:
                                AuditoriaFacturaIngreso.objects.create(
                                    ciclo=ciclo, campo=campo,
                                    valor_anterior=antes.get(campo, ""), valor_nuevo=valor_nuevo,
                                    usuario=request.user.get_username(),
                                )
                        actualizadas += 1
                    else:
                        numero_factura = generar_numero_factura(fecha_factura)
                        ciclo = CicloFacturacion.objects.create(
                            cliente_id=fila["cliente_id"],
                            fecha_factura=fecha_factura,
                            numero_factura=numero_factura,
                            numero_secuencial=int(numero_factura.rsplit("-", 1)[1]),
                            estado=CicloFacturacion.Estado.FACTURA_EMITIDA,
                            observaciones=fila["observaciones"],
                            creado_por=request.user.get_username(),
                        )
                        iva = (valor_neto * Decimal("0.19")).quantize(Decimal("0.01"))
                        LineaFacturaIngreso.objects.create(
                            ciclo=ciclo, descripcion=fila["concepto"],
                            cantidad=Decimal("1"), valor_unitario=valor_neto, total=valor_neto,
                        )
                        ciclo.subtotal = valor_neto
                        ciclo.iva = iva
                        ciclo.total = valor_neto + iva
                        ciclo.monto_facturado = ciclo.total
                        ciclo.save()
                        creadas += 1
                CargaFacturasIngreso.objects.create(
                    archivo_nombre=preview["archivo_nombre"], usuario=request.user.get_username(),
                    filas_total=len(preview["filas"]), filas_validas=len(preview["filas"]),
                    filas_creadas=creadas, filas_actualizadas=actualizadas, resultado="CONFIRMADA",
                )
            del request.session[clave]
            messages.success(
                request,
                f"Carga confirmada: {creadas} factura(s) creada(s), {actualizadas} actualizada(s).",
            )
            return redirect("financiero:facturas_ingresos")
        archivo = request.FILES.get("archivo")
        if not archivo:
            messages.error(request, "Seleccione un archivo CSV o XLSX.")
            return self.render_to_response(self.get_context_data())
        try:
            filas, errores = validar_filas(archivo, Cliente, MetodoPago, CicloFacturacion)
        except Exception as exc:
            errores, filas = [{"fila": 1, "error": str(exc)}], []
        preview = {
            "archivo_nombre": archivo.name,
            "filas": [
                {
                    campo: valor.isoformat() if hasattr(valor, "isoformat") else str(valor) if isinstance(valor, Decimal) else valor
                    for campo, valor in fila.items()
                }
                for fila in filas
            ],
            "errores": errores,
            "nuevas": sum(fila["accion_carga"] == "crear" for fila in filas),
            "actualizaciones": sum(fila["accion_carga"] == "actualizar" for fila in filas),
        }
        request.session[clave] = preview
        CargaFacturasIngreso.objects.create(
            archivo_nombre=archivo.name, usuario=request.user.get_username(),
            filas_total=len(filas) + len(errores), filas_validas=len(filas), filas_error=len(errores),
            resultado="PREVIEW" if not errores else "RECHAZADA", detalle_errores=errores,
        )
        return self.render_to_response(self.get_context_data())
