"""Instelec#267 — A7: Matriz de roles (cargar/ver/reportes-por-formato).

Contexto (comentario @Indunnova en el issue, tabla Rol×Cargar×Ver×Reportes):

    | Rol                 | Cargar | Ver | Reportes         |
    |----------------------|--------|-----|-------------------|
    | Admin Instelec        ✅      ✅    PDF/Excel/PPT/CSV |
    | Gerente Financiero     ✅      ✅    PDF/Excel/PPT/CSV |
    | Contador (Claudia)     ❌      ✅    Solo Excel        |
    | Gerente Proyecto        ✅      ✅    PDF/Excel         |
    | Supervisor               ❌      ✅    Solo lectura      |

Causa raíz auditada en BD prod antes del fix: ``admin_construccion`` solo
tenía ``ver`` (no podía cargar), y ``gerente_financiero``/``contador``/
``supervisor`` no tenían NINGUNA fila ``RoleModuloPermiso`` para el
submódulo ``FINANCIERO`` de ``CONSTRUCCION`` -- sin acceso total, ni
siquiera para VER. Corregido en BD PROD por la migración de datos
``core.0011_seed_construccion_financiero_matriz_roles_267``.

⚠️ **Esta suite NO depende de esa migración para pasar.** `pytest` corre con
``--nomigrations`` (``pyproject.toml``) -- ninguna migración de datos real
se ejecuta jamás en la suite. `conftest.py::django_db_setup` siembra RBAC
vía `apps/core/rbac_seed_data.py`, un snapshot **congelado** de los 15
roles legacy de #186 (2026-07-18): no incluye `contador`/`gerente_financiero`
(creados después por la migración 0008) ni la fila CONSTRUCCION/FINANCIERO
que #267 A7 agrega, y a `admin_construccion` le da `ver_editar` "de fábrica"
(mapeo nivel=admin -> ver_editar GLOBAL del snapshot legacy) aunque en BD
prod real solo tenía `ver` -- el snapshot y prod ya divergían ahí desde
antes de #267. Mismo patrón que `apps/financiero/tests/test_issue_248_gastos_v1.py`
(rol `contador` "sembrado por S1"): cada test file que necesita un rol/
permiso posterior al snapshot lo siembra él mismo, vía `_seed_matriz_roles_a7()`
abajo -- que reproduce EXACTAMENTE la migración 0011 (misma fuente, incluido
el mismo comentario de causa raíz), no una matriz alternativa.

Cobertura:
- Unit (``permissions_fin.formatos_reporte_permitidos`` / gate de
  cargar-ver) -- memoria feedback_usuarios_qa_sin_empresas_ocultan_fugas_de_scoping:
  usuarios REALES por rol (no superuser), nunca un fixture "admin todo-
  poderoso" disfrazando el gate.
- Integración (GET/POST reales contra la vista de Construcción):
  * contador REAL no puede cargar (POST 403) ni ve el botón PDF (solo Excel
    en el contexto ``formatos_reporte_permitidos``) -- caso EXPLÍCITO del
    issue #267 A7.
  * supervisor REAL ve (GET 200) pero no puede cargar (POST 403) y no tiene
    NINGÚN formato de descarga -- caso EXPLÍCITO del issue #267 A7.
  * gerente_financiero / director / admin_construccion: cargar+ver OK, con
    el tier de formatos correspondiente (todo / PDF+Excel / PDF+Excel).
  * Edge case dato legacy: el presupuesto PRE-EXISTENTE (creado antes de
    resolver el rol de la request) sigue siendo visible para un rol con
    ``ver`` -- el gate es sobre el USUARIO, no sobre el dato.
"""
import uuid

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.construccion.models import ProyectoConstruccion
from apps.construccion.models_fin import PresupuestoDetalladoConstruccion
from apps.construccion.permissions_fin import (
    FORMATO_CSV,
    FORMATO_EXCEL,
    FORMATO_PDF,
    FORMATO_PPT,
    formatos_reporte_permitidos,
    user_puede_cargar_financiero_construccion,
    user_puede_descargar_reporte,
    user_puede_ver_financiero_construccion,
)
from apps.contratos.models import Contrato

User = get_user_model()


def _crear_usuario(rol, suffix):
    """Usuario REAL con el rol dado -- NUNCA superuser (ver memoria de fugas
    de scoping: un superuser/admin-todopoderoso no ejercita el gate)."""
    return User.objects.create_user(
        email=f'qa_267a7_{suffix}_{uuid.uuid4().hex[:6]}@instelec.com',
        password='x',
        rol=rol,
    )


# Roles que _seed_matriz_roles_a7() toca -- compartido con la limpieza de
# cache de _invalidar_cache_roles_a7() (setUp Y tearDown, ver docstring).
_ROLES_TOCADOS_A7 = (
    'gerente_financiero', 'contador', 'supervisor', 'admin_construccion', 'director',
)


def _invalidar_cache_roles_a7():
    from apps.core.permissions import invalidate_role_cache
    for codigo in _ROLES_TOCADOS_A7:
        invalidate_role_cache(codigo)


def _seed_matriz_roles_a7():
    """Siembra Role/RoleModuloPermiso para los 5 roles de la matriz #267 A7.

    Reproduce EXACTAMENTE (misma fuente, mismos niveles) lo que
    ``core.0011_seed_construccion_financiero_matriz_roles_267`` hace en BD
    real -- ver el docstring del módulo para por qué hace falta duplicarlo
    acá (``--nomigrations`` + snapshot congelado de ``rbac_seed_data.py``).
    Idempotente (``get_or_create``/``update_or_create``): segura de llamar
    en el ``setUp`` de cada test sin acumular filas duplicadas.

    ⚠️ **El caller TAMBIÉN debe invalidar en ``tearDown``** (llamar
    ``_invalidar_cache_roles_a7()`` de nuevo ahí, no solo acá). `_get_role_permisos`
    cachea en un `LocMemCache` de PROCESO (sobrevive al rollback transaccional
    de `TestCase` -- el cache NO es parte de la transacción de BD). Sin la
    invalidación en tearDown: este test dispara un GET real que LEE la matriz
    modificada (aún sin commitear) y la CACHEA; `TestCase` hace rollback de
    las filas al terminar, pero el cache queda con el valor viejo (con
    `supervisor` ya con acceso a CONSTRUCCION/FINANCIERO) durante el resto de
    la sesión de pytest -- síntoma real detectado: `tests/unit/
    test_issue_186_paridad_rbac.py::test_paridad_modulos[supervisor]` empezó
    a fallar (PARIDAD ROTA) al correr en la MISMA sesión que este archivo,
    sin que ese test tocara nada de #267.
    """
    from apps.core.models import Role, RoleModuloPermiso

    # (codigo, nombre, nivel_acceso módulo-completo Y submódulo FINANCIERO)
    filas_roles_nuevos = [
        ('gerente_financiero', 'Gerente Financiero', 'ver_editar'),
        ('contador', 'Contador', 'ver'),
        ('supervisor', 'Supervisor de Cuadrilla (legacy)', 'ver'),
    ]
    for codigo, nombre, nivel in filas_roles_nuevos:
        role, _creado = Role.objects.get_or_create(
            codigo=codigo,
            defaults={'nombre': nombre, 'nivel': 'operario', 'activo': True},
        )
        RoleModuloPermiso.objects.update_or_create(
            role=role, modulo='CONSTRUCCION', submodulo='',
            defaults={'nivel_acceso': nivel},
        )
        RoleModuloPermiso.objects.update_or_create(
            role=role, modulo='CONSTRUCCION', submodulo='FINANCIERO',
            defaults={'nivel_acceso': nivel},
        )

    # admin_construccion: upgrade ver -> ver_editar (causa raíz real de #267
    # A7 en BD prod -- ver docstring de la migración 0011). El snapshot de
    # `rbac_seed_data.py` YA le da 'ver_editar' de fábrica (mapeo nivel=admin
    # global, no refleja el gap real que había en prod), así que esta línea
    # es un no-op bajo el snapshot de test -- se deja explícita para que el
    # test siga siendo correcto el día que alguien corrija también el
    # snapshot legacy para que refleje la matriz real por submódulo.
    role_ac, _creado = Role.objects.get_or_create(
        codigo='admin_construccion',
        defaults={'nombre': 'Administrador de Construcción', 'nivel': 'admin', 'activo': True},
    )
    RoleModuloPermiso.objects.update_or_create(
        role=role_ac, modulo='CONSTRUCCION', submodulo='FINANCIERO',
        defaults={'nivel_acceso': 'ver_editar'},
    )

    _invalidar_cache_roles_a7()


def _crear_proyecto(nombre='Proyecto A7 test #267'):
    contrato = Contrato.objects.create(
        codigo=f"CONS-{uuid.uuid4().hex[:10]}",
        nombre='Contrato test construcción #267 A7',
        unidad_negocio='CONSTRUCCION',
    )
    return ProyectoConstruccion.objects.create(contrato=contrato, nombre=nombre)


# ===========================================================================
# Unit -- formatos_reporte_permitidos / user_puede_descargar_reporte
# ===========================================================================
class FormatosReportePermitidosTests(TestCase):
    def test_contador_solo_excel(self):
        """Fila literal del issue: Contador -> 'Solo Excel'."""
        user = _crear_usuario('contador', 'contador')
        self.assertEqual(formatos_reporte_permitidos(user), {FORMATO_EXCEL})
        self.assertTrue(user_puede_descargar_reporte(user, FORMATO_EXCEL))
        self.assertFalse(user_puede_descargar_reporte(user, FORMATO_PDF))
        self.assertFalse(user_puede_descargar_reporte(user, FORMATO_PPT))
        self.assertFalse(user_puede_descargar_reporte(user, FORMATO_CSV))

    def test_supervisor_sin_descargas(self):
        """Fila literal del issue: Supervisor -> 'Solo lectura' (nada)."""
        user = _crear_usuario('supervisor', 'supervisor')
        self.assertEqual(formatos_reporte_permitidos(user), set())
        for formato in (FORMATO_PDF, FORMATO_EXCEL, FORMATO_PPT, FORMATO_CSV):
            self.assertFalse(user_puede_descargar_reporte(user, formato))

    def test_gerente_financiero_todos_los_formatos(self):
        user = _crear_usuario('gerente_financiero', 'gf')
        self.assertEqual(
            formatos_reporte_permitidos(user),
            {FORMATO_PDF, FORMATO_EXCEL, FORMATO_PPT, FORMATO_CSV},
        )

    def test_director_pdf_y_excel_sin_ppt(self):
        """Mapeo F2 'Gerente Proyecto' -> director: PDF/Excel, no PPT/CSV."""
        user = _crear_usuario('director', 'director')
        self.assertEqual(formatos_reporte_permitidos(user), {FORMATO_PDF, FORMATO_EXCEL})

    def test_admin_construccion_pdf_y_excel_sin_ppt(self):
        """Mapeo F2 'Gerente Proyecto' -> admin_construccion: mismo tier que
        director, NO el tier 'todo' de un admin genérico -- carve-out
        explícito aunque su `nivel` en BD sea 'admin'."""
        user = _crear_usuario('admin_construccion', 'adminconst')
        self.assertEqual(
            formatos_reporte_permitidos(user), {FORMATO_PDF, FORMATO_EXCEL})

    def test_admin_general_todos_los_formatos_via_bypass_generico(self):
        """Un rol admin* SIN carve-out explícito (admin_general) cae en el
        bypass genérico `user_es_admin` -> todos los formatos ('Admin
        Instelec' del issue)."""
        user = _crear_usuario('admin_general', 'admingral')
        self.assertEqual(
            formatos_reporte_permitidos(user),
            {FORMATO_PDF, FORMATO_EXCEL, FORMATO_PPT, FORMATO_CSV},
        )

    def test_rol_desconocido_sin_formatos(self):
        """Rol operativo sin matriz conocida (p.ej. liniero) -> set() vacío,
        nunca lanza."""
        user = _crear_usuario('liniero', 'liniero')
        self.assertEqual(formatos_reporte_permitidos(user), set())

    def test_anonimo_sin_formatos(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertEqual(formatos_reporte_permitidos(AnonymousUser()), set())


# ===========================================================================
# Unit -- user_puede_ver_financiero_construccion / cargar (espejo de RBAC)
# ===========================================================================
class GateCargarVerTests(TestCase):
    def setUp(self):
        _seed_matriz_roles_a7()
        # Limpieza de cache OBLIGATORIA al cerrar -- ver docstring de
        # _seed_matriz_roles_a7() (el rollback de TestCase no alcanza al
        # LocMemCache de proceso). `addCleanup` en vez de `tearDown` para no
        # tener que acordarme de encadenar `super().tearDown()`.
        self.addCleanup(_invalidar_cache_roles_a7)

    def test_contador_ve_pero_no_carga(self):
        user = _crear_usuario('contador', 'contador2')
        self.assertTrue(user_puede_ver_financiero_construccion(user))
        self.assertFalse(user_puede_cargar_financiero_construccion(user))

    def test_supervisor_ve_pero_no_carga(self):
        user = _crear_usuario('supervisor', 'supervisor2')
        self.assertTrue(user_puede_ver_financiero_construccion(user))
        self.assertFalse(user_puede_cargar_financiero_construccion(user))

    def test_gerente_financiero_ve_y_carga(self):
        user = _crear_usuario('gerente_financiero', 'gf2')
        self.assertTrue(user_puede_ver_financiero_construccion(user))
        self.assertTrue(user_puede_cargar_financiero_construccion(user))

    def test_admin_construccion_ve_y_carga(self):
        """Causa raíz del bug pre-#267: antes solo tenía 'ver'."""
        user = _crear_usuario('admin_construccion', 'adminconst2')
        self.assertTrue(user_puede_ver_financiero_construccion(user))
        self.assertTrue(user_puede_cargar_financiero_construccion(user))


# ===========================================================================
# Integración -- GET/POST reales contra la vista de Construcción
# ===========================================================================
class MatrizRolesIntegracionTests(TestCase):
    """Usuarios REALES (no superuser) contra
    ``construccion:fin_presupuesto_planeado`` -- gate server-side, no solo
    UI (#267 A7)."""

    def setUp(self):
        _seed_matriz_roles_a7()
        self.proyecto = _crear_proyecto()
        self.url = reverse(
            'construccion:fin_presupuesto_planeado',
            kwargs={'proyecto_id': self.proyecto.pk},
        )
        self.addCleanup(_invalidar_cache_roles_a7)
        # Edge case dato legacy: presupuesto PRE-EXISTENTE, creado antes de
        # que cualquier usuario de este test haga login -- el gate es sobre
        # el usuario de la request, no sobre cuándo se cargó el dato.
        PresupuestoDetalladoConstruccion.objects.create(
            proyecto=self.proyecto, anio=2026,
            tipo=PresupuestoDetalladoConstruccion.Tipo.PLANEADO,
            datos={'ingreso': {'enero': 1000}, 'variables': {}, 'fijos': {}},
        )

    def _login(self, rol, suffix):
        user = _crear_usuario(rol, suffix)
        client = Client()
        client.force_login(user)
        return client, user

    def test_contador_ve_pero_no_puede_cargar_ni_pdf(self):
        client, _user = self._login('contador', 'int_contador')
        resp_get = client.get(self.url, {'anio': 2026})
        self.assertEqual(resp_get.status_code, 200)
        self.assertEqual(
            resp_get.context['formatos_reporte_permitidos'], {FORMATO_EXCEL})

        resp_post = client.post(self.url, {'anio': 2026})
        self.assertEqual(resp_post.status_code, 403)
        # El intento de carga NO debe dejar rastro (ni historial ni datos
        # tocados) -- el 403 ocurre en dispatch(), antes de tocar el modelo.
        self.assertEqual(
            PresupuestoDetalladoConstruccion.objects.filter(
                proyecto=self.proyecto, anio=2026).count(), 1)

    def test_supervisor_ve_pero_no_puede_cargar_ni_descargar_nada(self):
        client, _user = self._login('supervisor', 'int_supervisor')
        resp_get = client.get(self.url, {'anio': 2026})
        self.assertEqual(resp_get.status_code, 200)
        self.assertEqual(resp_get.context['formatos_reporte_permitidos'], set())

        resp_post = client.post(self.url, {'anio': 2026})
        self.assertEqual(resp_post.status_code, 403)

    def test_gerente_financiero_ve_y_puede_cargar_todos_los_formatos(self):
        client, _user = self._login('gerente_financiero', 'int_gf')
        resp_get = client.get(self.url, {'anio': 2026})
        self.assertEqual(resp_get.status_code, 200)
        self.assertEqual(
            resp_get.context['formatos_reporte_permitidos'],
            {FORMATO_PDF, FORMATO_EXCEL, FORMATO_PPT, FORMATO_CSV},
        )
        # POST sin archivo -> 302 (redirect + mensaje de error de form, NO
        # 403): confirma que el gate de ROL ya lo dejó pasar y lo que sigue
        # es la validación normal de la vista.
        resp_post = client.post(self.url, {'anio': 2026})
        self.assertEqual(resp_post.status_code, 302)

    def test_director_y_admin_construccion_ven_y_cargan_pdf_excel(self):
        for rol, suffix in (('director', 'int_dir'), ('admin_construccion', 'int_ac')):
            with self.subTest(rol=rol):
                client, _user = self._login(rol, suffix)
                resp_get = client.get(self.url, {'anio': 2026})
                self.assertEqual(resp_get.status_code, 200)
                self.assertEqual(
                    resp_get.context['formatos_reporte_permitidos'],
                    {FORMATO_PDF, FORMATO_EXCEL},
                )
                resp_post = client.post(self.url, {'anio': 2026})
                self.assertEqual(resp_post.status_code, 302)

    def test_rol_sin_matriz_no_ve_el_modulo(self):
        """Un rol sin NINGUNA fila RoleModuloPermiso para el módulo
        CONSTRUCCION completo (auxiliar -- verificado en BD prod, a
        diferencia de 'liniero' que sí trae un 'ver' de FINANCIERO
        pre-existente ajeno a #267) no puede abrir el módulo financiero de
        Construcción. `RBACModuloMiddleware` (Nivel 2, gate coarse de
        módulo) lo intercepta ANTES de llegar a la vista -- 302 (redirect +
        mensaje de error), NO un 200 con contenido vacío. Ver
        ``apps/core/middleware.py::_denegar``: un deny de módulo completo
        es redirect, no 403 (ese status se reserva para el gate MÁS FINO
        de submódulo/hoja del propio ``RoleRequiredMixin``, ver los tests
        de contador/supervisor arriba)."""
        client, _user = self._login('auxiliar', 'int_auxiliar')
        resp_get = client.get(self.url, {'anio': 2026}, follow=False)
        self.assertEqual(resp_get.status_code, 302)
