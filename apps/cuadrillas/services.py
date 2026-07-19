"""Servicios compartidos del módulo cuadrillas.

Issue #188 (A5): extrae ``_resolver_o_crear_usuario`` de
``CuadrillaMiembroAddView`` (views.py) para reusarlo también desde
``ProgramacionSemanalMiembroAgregarView`` (views_semanal.py, grid editable
del nuevo diseño) sin duplicar el patrón ni romper el comportamiento YA
validado en prod de ``CuadrillaMiembroAddView`` (issue #176).
"""


def resolver_o_crear_usuario(personal):
    """Resuelve el ``Usuario`` vinculado a un ``PersonalCuadrilla`` por
    documento, o lo crea si es la primera vez que se asigna (mismo patrón de
    ``apps.cuadrillas.importers._crear_usuario`` para altas masivas S18):
    email sintético determinístico, ``is_active=False``, sin password
    utilizable -- es solo un registro de vínculo, no una cuenta operativa.
    """
    from apps.usuarios.models import Usuario

    usuario = Usuario.objects.filter(documento=personal.documento).first()
    if usuario:
        return usuario

    nombre = personal.nombre or f'Colaborador {personal.documento}'
    partes = nombre.split()
    first = partes[0] if partes else nombre
    last = ' '.join(partes[1:]) if len(partes) > 1 else ''
    email = f'{personal.documento}@instelec-colaborador.local'

    usuario = Usuario.objects.create(
        email=email,
        first_name=first[:150],
        last_name=last[:150],
        documento=personal.documento,
        rol='operario_general',
        is_active=False,
    )
    usuario.set_unusable_password()
    usuario.save(update_fields=['password'])
    return usuario
