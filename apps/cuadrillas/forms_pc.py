"""
Forms del módulo Programación / Ejecución semanal de cuadrillas (#155, B2).

`ProgramacionSemanalCuadrillaForm` es un ModelForm sobre
`models_pc.ProgramacionSemanalCuadrilla` (scaffolding S1). Se usa para crear y
editar la programación semanal desde la subsección administrativa de
Construcción.

`EjecucionSemanalCuadrillaForm` lo deja preparado B2 para que B3 lo reutilice en
el guardado inline AJAX (lectura compartida declarada en el BLUEPRINT). Es un
ModelForm sobre `EjecucionSemanalCuadrilla` (`torres_ejecutadas` + `vehiculo`
[#270 sub-item B] + `observaciones`; la FK `programacion` la asigna la vista).

Notas es-CO (lecciones de memoria):
- Los campos numéricos (`anio`, `semana`, `torres_programadas`,
  `torres_ejecutadas`) usan `NumberInput` con enteros — NO hay floats ni fechas,
  así que no aplica el bug de `floatformat`/`input type=date` con coma decimal.
- No se inyecta JSON/float crudo en `x-data`; el form no usa Alpine.
"""
from django import forms
from django.db.models import Q
from django.urls import reverse_lazy

from apps.construccion.models import TorreConstruccion
from apps.construccion.views import ordenar_torres_construccion

from .models_base import Vehiculo
from .models_pc import EjecucionSemanalCuadrilla, ProgramacionSemanalCuadrilla

# Clase Tailwind compartida (espeja apps/construccion/forms.py::INPUT_CLS).
INPUT_CLS = (
    'mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 '
    'px-3 py-2 shadow-sm focus:border-blue-500 focus:ring-blue-500 '
    'bg-white dark:bg-gray-700 text-gray-900 dark:text-white sm:text-sm'
)


class ProgramacionSemanalCuadrillaForm(forms.ModelForm):
    """Crear/editar una programación semanal de cuadrilla."""

    class Meta:
        model = ProgramacionSemanalCuadrilla
        fields = [
            'cuadrilla', 'proyecto', 'bloque', 'anio', 'semana',
            'torres_programadas', 'torres', 'horas_planeadas',
            'actividades_programadas', 'observaciones',
        ]
        widgets = {
            # #155: clase js-tomselect → buscador (init global único en base.html).
            'cuadrilla': forms.Select(attrs={'class': INPUT_CLS + ' js-tomselect'}),
            # #269: al cambiar 'proyecto', HTMX pide el fragmento de <option>
            # de torres ACTIVAS de ese proyecto y reemplaza el innerHTML del
            # <select id="id_torres"> -- mismo patrón que la cascada
            # Línea→Tramo (#188/#209, TramosPorLineaAPIView). El listener
            # global de base.html (htmx:afterSwap) re-sincroniza el TomSelect
            # de 'torres' tras el swap (sync()+clear()), sin JS propio.
            'proyecto': forms.Select(attrs={
                'class': INPUT_CLS + ' js-tomselect',
                'hx-get': reverse_lazy('construccion:torres_activas_fragmento'),
                'hx-trigger': 'change',
                'hx-target': '#id_torres',
                'hx-swap': 'innerHTML',
            }),
            'bloque': forms.Select(attrs={'class': INPUT_CLS}),
            'anio': forms.NumberInput(attrs={
                'class': INPUT_CLS, 'min': 2000, 'max': 2100, 'step': 1,
                'placeholder': 'Ej: 2026',
            }),
            'semana': forms.NumberInput(attrs={
                'class': INPUT_CLS, 'min': 1, 'max': 53, 'step': 1,
                'placeholder': '1-53',
            }),
            'torres_programadas': forms.NumberInput(attrs={
                'class': INPUT_CLS, 'min': 0, 'step': 1, 'placeholder': '0',
            }),
            # #269: multi-select TomSelect. `placeholder` lo lee TomSelect del
            # atributo nativo del <select> cuando no hay <option> (proyecto
            # todavía sin elegir) -- sin JS propio.
            'torres': forms.SelectMultiple(attrs={
                'class': INPUT_CLS + ' js-tomselect',
                'placeholder': 'Selecciona primero un proyecto',
            }),
            'horas_planeadas': forms.NumberInput(attrs={
                'class': INPUT_CLS, 'min': 0, 'step': '0.01', 'placeholder': '0.00',
            }),
            'actividades_programadas': forms.Textarea(attrs={
                'class': INPUT_CLS, 'rows': 3,
                'placeholder': 'Actividades planeadas para la semana',
            }),
            'observaciones': forms.Textarea(attrs={
                'class': INPUT_CLS, 'rows': 2,
                'placeholder': 'Observaciones (opcional)',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Proyecto es opcional: dejar etiqueta vacía explícita.
        self.fields['proyecto'].required = False
        self.fields['proyecto'].empty_label = '— Sin proyecto —'
        # Ordenar cuadrillas por código para una selección predecible.
        self.fields['cuadrilla'].queryset = (
            self.fields['cuadrilla'].queryset.order_by('codigo')
        )
        # #269: 'torres' es opcional y depende de 'proyecto' (cascada HTMX en
        # el widget). El queryset del ModelMultipleChoiceField DEBE incluir
        # los ids que el POST puede traer -- si se deja `.none()` a secas, un
        # submit real con torres elegidas falla la validación ("esa opción no
        # es una de las disponibles") aunque el HTML las haya listado bien.
        self.fields['torres'].required = False
        proyecto_id = None
        if self.data.get('proyecto'):
            proyecto_id = self.data.get('proyecto')
        elif self.instance and self.instance.pk and self.instance.proyecto_id:
            proyecto_id = self.instance.proyecto_id
        if proyecto_id:
            self.fields['torres'].queryset = ordenar_torres_construccion(
                TorreConstruccion.objects.filter(
                    proyecto_id=proyecto_id, anulada=False,
                )
            )
        else:
            self.fields['torres'].queryset = TorreConstruccion.objects.none()

    def clean_semana(self):
        """Edge case: semana ISO válida (1..53)."""
        semana = self.cleaned_data.get('semana')
        if semana is not None and not (1 <= semana <= 53):
            raise forms.ValidationError(
                'La semana ISO debe estar entre 1 y 53.'
            )
        return semana

    def clean_anio(self):
        """Edge case: año en un rango razonable (evita typos tipo 20226)."""
        anio = self.cleaned_data.get('anio')
        if anio is not None and not (2000 <= anio <= 2100):
            raise forms.ValidationError(
                'El año debe estar entre 2000 y 2100.'
            )
        return anio

    def clean(self):
        """
        Edge case: respetar `unique_together` (cuadrilla, anio, semana) con un
        mensaje de dominio claro en vez del IntegrityError crudo. El ModelForm
        ya valida unique_together, pero personalizamos el mensaje.
        """
        cleaned = super().clean()
        cuadrilla = cleaned.get('cuadrilla')
        anio = cleaned.get('anio')
        semana = cleaned.get('semana')
        if cuadrilla and anio and semana:
            qs = ProgramacionSemanalCuadrilla.objects.filter(
                cuadrilla=cuadrilla, anio=anio, semana=semana,
            )
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    f'Ya existe una programación para la cuadrilla '
                    f'{cuadrilla} en {anio}-S{semana:02d}.'
                )
        return cleaned


class EjecucionSemanalCuadrillaForm(forms.ModelForm):
    """
    Form de ejecución semanal — preparado por B2 para reuso de B3 (inline AJAX).
    La FK `programacion` la asigna la vista (no se expone en el form).

    #270 (sub-item B): `vehiculo` es editable/reasignable. El queryset ofrecido
    solo incluye vehículos ACTIVOS (mismo criterio que
    `apps/construccion/views_psc_asignacion.py::ProgramacionSemanalConstruccionAgregarVehiculoView`)
    -- MÁS el vehículo ya asignado a esta instancia aunque haya pasado a
    EN_MANTENIMIENTO/INACTIVO después de asignarlo, para no romper el render de
    una ejecución existente ni forzar su desasignación silenciosa.
    """

    class Meta:
        model = EjecucionSemanalCuadrilla
        fields = ['torres_ejecutadas', 'vehiculo', 'observaciones']
        widgets = {
            'torres_ejecutadas': forms.NumberInput(attrs={
                'class': INPUT_CLS, 'min': 0, 'step': 1,
                'name': 'torres_ejecutadas',
            }),
            # Select2/TomSelect (js-tomselect, init global en base.html) —
            # el label muestra placa/tipo/capacidad vía label_from_instance
            # (ver __init__), no hay <option> anidado que romper.
            'vehiculo': forms.Select(attrs={'class': INPUT_CLS + ' js-tomselect'}),
            'observaciones': forms.Textarea(attrs={
                'class': INPUT_CLS, 'rows': 2,
                'placeholder': 'Observaciones de la ejecución (opcional)',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['vehiculo'].required = False
        self.fields['vehiculo'].empty_label = '— Sin vehículo asignado —'
        vehiculo_qs = Vehiculo.objects.filter(estado=Vehiculo.Estado.ACTIVO)
        if self.instance and self.instance.pk and self.instance.vehiculo_id:
            vehiculo_qs = Vehiculo.objects.filter(
                Q(estado=Vehiculo.Estado.ACTIVO)
                | Q(pk=self.instance.vehiculo_id)
            )
        self.fields['vehiculo'].queryset = vehiculo_qs.order_by('placa')
        self.fields['vehiculo'].label_from_instance = (
            lambda v: f"{v.placa} — {v.get_tipo_display()} (cap. {v.capacidad_personas})"
        )

    def clean_torres_ejecutadas(self):
        torres = self.cleaned_data.get('torres_ejecutadas')
        if torres is not None and torres < 0:
            raise forms.ValidationError(
                'Las torres ejecutadas no pueden ser negativas.'
            )
        return torres

    def clean_vehiculo(self):
        """Edge case: solo se puede ASIGNAR (cambiar a) un vehículo ACTIVO.
        Un vehículo ya asignado que pasó a EN_MANTENIMIENTO/INACTIVO se puede
        seguir viendo/mantener sin cambios, pero no volver a elegir tras
        haberlo quitado."""
        vehiculo = self.cleaned_data.get('vehiculo')
        if vehiculo is None:
            return vehiculo
        ya_asignado = (
            self.instance and self.instance.pk
            and self.instance.vehiculo_id == vehiculo.pk
        )
        if not ya_asignado and vehiculo.estado != Vehiculo.Estado.ACTIVO:
            raise forms.ValidationError(
                'Solo se pueden asignar vehículos activos.'
            )
        return vehiculo
