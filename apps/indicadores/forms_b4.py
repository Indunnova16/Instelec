"""
B4 — ModelForms para CRUD de indicadores de mantenimiento detallado.

Uno por modelo:
- ``IndicadorMantenimientoFinancieroForm``
- ``IndicadorMantenimientoTecnicoForm``
- ``IndicadorANSContractualForm``

Excluyen los campos calculados (margen, desviacion, puntaje, estado) porque
el modelo los recalcula en save(). Si el usuario los viera editables, podria
crear inconsistencias.
"""
from django import forms

from .models_b4_mantenimiento_detallado import (
    IndicadorANSContractual,
    IndicadorMantenimientoFinanciero,
    IndicadorMantenimientoTecnico,
)


INPUT_CLS = (
    "block w-full rounded-md border border-gray-300 dark:border-gray-600 "
    "bg-white dark:bg-gray-800 px-3 py-2 text-sm "
    "focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
)


def _apply_tailwind(form: forms.ModelForm) -> None:
    """Aplica clases Tailwind a todos los widgets (consistente con base.html)."""
    for name, field in form.fields.items():
        existing = field.widget.attrs.get("class", "")
        field.widget.attrs["class"] = f"{existing} {INPUT_CLS}".strip()
        if isinstance(field.widget, forms.Textarea):
            field.widget.attrs.setdefault("rows", 3)


class IndicadorMantenimientoFinancieroForm(forms.ModelForm):
    class Meta:
        model = IndicadorMantenimientoFinanciero
        fields = [
            "linea",
            "fecha",
            "anio",
            "mes",
            "ingresos_ejecutados",
            "costos_directos",
            "gastos",
            "costo_real",
            "costo_presupuestado",
            "observaciones",
        ]
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date"}),
            "observaciones": forms.Textarea(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_tailwind(self)

    def clean_mes(self):
        mes = self.cleaned_data.get("mes")
        if mes is not None and (mes < 1 or mes > 12):
            raise forms.ValidationError("El mes debe estar entre 1 y 12.")
        return mes

    def clean(self):
        cleaned = super().clean()
        # Edge case: si el usuario carga solo % calculados sin insumos, OK.
        # Pero si carga ingresos sin costos (o viceversa) avisar.
        ingresos = cleaned.get("ingresos_ejecutados") or 0
        cd = cleaned.get("costos_directos") or 0
        g = cleaned.get("gastos") or 0
        if ingresos and not (cd or g):
            self.add_error(
                "costos_directos",
                "Ingresos cargados sin costos: el margen sera 100 %. Verifica.",
            )
        return cleaned


class IndicadorMantenimientoTecnicoForm(forms.ModelForm):
    class Meta:
        model = IndicadorMantenimientoTecnico
        fields = [
            "linea",
            "fecha",
            "anio",
            "mes",
            "facturacion_real",
            "meta_facturacion",
            "produccion_real",
            "meta_produccion",
            "valor_facturado",
            "costo_cuadrilla",
            "observaciones",
        ]
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date"}),
            "observaciones": forms.Textarea(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_tailwind(self)

    def clean_mes(self):
        mes = self.cleaned_data.get("mes")
        if mes is not None and (mes < 1 or mes > 12):
            raise forms.ValidationError("El mes debe estar entre 1 y 12.")
        return mes

    def clean(self):
        cleaned = super().clean()
        # Edge: meta_facturacion 0 produciria division por cero (manejada en
        # modelo) pero deja indicador en 0; avisar al usuario.
        meta = cleaned.get("meta_facturacion") or 0
        fr = cleaned.get("facturacion_real") or 0
        if fr and not meta:
            self.add_error(
                "meta_facturacion",
                "Facturacion real cargada pero meta=0; los indicadores % no se calcularan.",
            )
        return cleaned


class IndicadorANSContractualForm(forms.ModelForm):
    class Meta:
        model = IndicadorANSContractual
        fields = [
            "linea",
            "fecha",
            "anio",
            "mes",
            "cumplimiento_programacion",
            "cumplimiento_ejecucion",
            "cumplimiento_informacion_contractual",
            "cumplimiento_informacion_ambiental",
            "cumplimiento_disponibilidad_circuitos",
            "observaciones",
        ]
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date"}),
            "observaciones": forms.Textarea(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_tailwind(self)
        # Los 5 % aceptan 0..100, ya validado a nivel modelo; reforzar widget.
        for f in (
            "cumplimiento_programacion",
            "cumplimiento_ejecucion",
            "cumplimiento_informacion_contractual",
            "cumplimiento_informacion_ambiental",
            "cumplimiento_disponibilidad_circuitos",
        ):
            self.fields[f].widget.attrs.update({"min": 0, "max": 100, "step": "0.01"})

    def clean_mes(self):
        mes = self.cleaned_data.get("mes")
        if mes is not None and (mes < 1 or mes > 12):
            raise forms.ValidationError("El mes debe estar entre 1 y 12.")
        return mes
