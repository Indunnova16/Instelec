"""
Maestro 3: Cargos (issue #176, bounce 2).

Catálogo editable de cargos/roles de cuadrilla, análogo a TipoActividad
(apps/actividades/models.py) y al maestro de Colaboradores. Reemplaza el
TextChoices `RolCuadrilla` hoy duplicado byte-a-byte en
`PersonalCuadrilla.rol_cuadrilla` y `CuadrillaMiembro.rol_cuadrilla`
(models_base.py).

NEW MODELS GO IN A NEW FILE (ver models.py:10) — re-exportado en
apps/cuadrillas/models.py.
"""

from django.db import models

from apps.core.models import BaseModel


class Cargo(BaseModel):
    """Catálogo editable de cargos/roles de cuadrilla (issue #176, Maestro 3).

    NO confundir con CuadrillaMiembro.CargoJerarquico (JT_CTA/MIEMBRO) —
    ese es un concepto distinto (jerarquía dentro de la cuadrilla), no
    tocado por este maestro. El campo que referencia este catálogo en
    PersonalCuadrilla/CuadrillaMiembro sigue llamándose `rol_cuadrilla`
    (no `cargo`) precisamente para no colisionar con ese otro concepto.

    `codigo` es de solo lectura una vez creado (ver CargoEditView, A2):
    con el FK `to_field='codigo'` que referencian PersonalCuadrilla y
    CuadrillaMiembro (A3), Postgres bloquea el UPDATE de un código ya
    referenciado por al menos una fila (IntegrityError de FK).
    """

    codigo = models.CharField("Código", max_length=20, unique=True)
    nombre = models.CharField("Nombre", max_length=100)
    activo = models.BooleanField("Activo", default=True)
    salario_base = models.DecimalField(
        "Salario base",
        max_digits=12,
        decimal_places=2,
        default=0,
        blank=True,
        help_text=(
            "Salario mensual sugerido para este cargo (default/sugerencia al "
            "autocompletar el salario de un Colaborador; el valor efectivo para "
            "costos/reportes sigue siendo PersonalCuadrilla.salario_base, issue #176 A1)."
        ),
    )

    class Meta:
        db_table = "cargos"
        verbose_name = "Cargo"
        verbose_name_plural = "Cargos"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"
