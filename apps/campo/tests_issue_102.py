"""
Tests #102 (bounce=2, FIX_INCOMPLETO) — Wiring de ``?semestre=S1|S2|TA`` en
``RegistroAvanceCreateView._build_context()``.

Causa raíz (F2): la vista NUNCA leía ``request.GET.get('semestre')`` ni
consultaba ``VanoSemestre`` — el dropdown "Período" del template
(``lineas/_filtro_semestre.html``, construido en mayo por B2.1) era un
gancho visual sin efecto real; las 4 stats (total/pendientes/ejecutados/
porcentaje) siempre se calculaban desde ``Vano.objects.filter(linea=linea)``
global, sin importar el semestre elegido.

Cubre:
- Wiring real: ``?semestre=S1`` vs ``?semestre=S2`` de la MISMA línea
  devuelven ``total_vanos`` DISTINTO (discriminante — antes del fix ambos
  daban el mismo número).
- Sin ``?semestre=``: comportamiento IDÉNTICO al actual (regresión, mismo
  contrato que B1.2/#101 — ``tests_b12.py``).
- Semestre inválido / minúsculas: mismo criterio case-insensitive que
  ``filter_vanos_by_semestre`` (ya testeado en ``tests_b21.py``).
- Estado independiente por semestre se refleja en ``vanos_ejecutados``/
  ``porcentaje`` filtrados (marcar EJECUTADO en S1 no afecta el cálculo de S2).
- Dato legacy: línea con Vano preexistentes pero SIN VanoSemestre (nunca
  configurada por B2.1) — filtrada da grid vacío + stats en 0 sin 500 por
  división por cero.
"""

from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.campo.views import RegistroAvanceCreateView
from apps.lineas.models import Linea, Vano
from apps.lineas.models_b21 import VanoSemestre
from apps.usuarios.models import Usuario


def _invoke_get_context(user, linea_id=None, semestre=None):
    """Mismo patrón que ``apps/campo/tests_b12.py`` — llama
    ``get_context_data`` directo vía ``RequestFactory``, sin renderizar el
    template (evita depender de includes de otras sub-features)."""
    rf = RequestFactory()
    query = {}
    if linea_id is not None:
        query["linea_id"] = linea_id
    if semestre is not None:
        query["semestre"] = semestre
    request = rf.get(reverse("campo:avance_registrar"), query)
    request.user = user

    view = RegistroAvanceCreateView()
    view.setup(request)
    return view.get_context_data()


def _linea(codigo="LT-102"):
    return Linea.objects.create(
        codigo=codigo,
        nombre=f"Línea {codigo}",
        cliente=Linea.Cliente.TRANSELCA,
        activa=True,
    )


class RegistroAvanceCreateViewFiltroSemestreTests(TestCase):
    """Tests del wiring #102 sobre ``RegistroAvanceCreateView``."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_user(
            email="admin_102@test.com",
            password="testpass123!",
            first_name="Admin",
            last_name="102",
            rol="admin",
            is_staff=True,
            is_superuser=True,
        )

        # Línea LN733-equivalente: S1=18 vanos (1..18, todos pendientes),
        # S2=8 vanos (subconjunto de S1: 2,3,4,5,7,12,16,17) — mismo
        # discriminante state-independent que usa el journey de F2/F3
        # (no depende de que se haya marcado ningún estado todavía).
        cls.linea = _linea("LT-102-733")
        for i in range(1, 19):
            Vano.objects.create(linea=cls.linea, numero=str(i))
        s1_numeros = set(range(1, 19))
        s2_numeros = {2, 3, 4, 5, 7, 12, 16, 17}
        for n in s1_numeros:
            vano = cls.linea.vanos.get(numero=str(n))
            VanoSemestre.objects.create(vano=vano, semestre="S1")
        for n in s2_numeros:
            vano = cls.linea.vanos.get(numero=str(n))
            VanoSemestre.objects.create(vano=vano, semestre="S2")

        # Línea legacy: tiene Vano pero NUNCA se configuraron VanoSemestre
        # (dato real posible — B2.1 es opt-in por vano, ver modal de
        # configuración en views_b21.py).
        cls.linea_legacy = _linea("LT-102-LEGACY")
        for i in range(1, 6):
            Vano.objects.create(linea=cls.linea_legacy, numero=str(i))

    # ------------------------------------------------------------------
    # Wiring real — discriminante S1 vs S2
    # ------------------------------------------------------------------
    def test_filtro_s1_vs_s2_misma_linea_totales_distintos(self):
        ctx_s1 = _invoke_get_context(self.admin, linea_id=str(self.linea.id), semestre="S1")
        ctx_s2 = _invoke_get_context(self.admin, linea_id=str(self.linea.id), semestre="S2")

        self.assertEqual(ctx_s1["total_vanos"], 18)
        self.assertEqual(ctx_s2["total_vanos"], 8)
        self.assertNotEqual(ctx_s1["total_vanos"], ctx_s2["total_vanos"])
        self.assertEqual(ctx_s1["semestre"], "S1")
        self.assertEqual(ctx_s2["semestre"], "S2")

    def test_filtro_s1_grid_tiene_18_vanos_s2_tiene_8(self):
        ctx_s1 = _invoke_get_context(self.admin, linea_id=str(self.linea.id), semestre="S1")
        ctx_s2 = _invoke_get_context(self.admin, linea_id=str(self.linea.id), semestre="S2")
        self.assertEqual(len(ctx_s1["vanos"]), 18)
        self.assertEqual(len(ctx_s2["vanos"]), 8)

    def test_filtro_pendientes_coincide_con_total_sin_estados_marcados(self):
        ctx_s1 = _invoke_get_context(self.admin, linea_id=str(self.linea.id), semestre="S1")
        self.assertEqual(ctx_s1["vanos_pendientes"], 18)
        self.assertEqual(ctx_s1["vanos_ejecutados"], 0)
        self.assertEqual(ctx_s1["porcentaje"], 0)

    # ------------------------------------------------------------------
    # Estado independiente por semestre (marcar S1 no afecta cálculo S2)
    # ------------------------------------------------------------------
    def test_marcar_ejecutado_en_s1_no_afecta_stats_de_s2(self):
        vs1 = VanoSemestre.objects.filter(
            vano__linea=self.linea, vano__numero="2", semestre="S1"
        ).get()
        vs1.marcar(VanoSemestre.Estado.EJECUTADO)

        ctx_s1 = _invoke_get_context(self.admin, linea_id=str(self.linea.id), semestre="S1")
        ctx_s2 = _invoke_get_context(self.admin, linea_id=str(self.linea.id), semestre="S2")

        self.assertEqual(ctx_s1["vanos_ejecutados"], 1)
        self.assertEqual(ctx_s1["porcentaje"], round(1 / 18 * 100))
        # El vano #2 en S2 sigue PENDIENTE — aislamiento entre semestres.
        self.assertEqual(ctx_s2["vanos_ejecutados"], 0)

    # ------------------------------------------------------------------
    # Regresión — sin filtro, comportamiento IDÉNTICO al actual
    # ------------------------------------------------------------------
    def test_sin_filtro_usa_conteo_global_de_vano_no_vanosemestre(self):
        """Sin ?semestre=, las stats deben venir de Vano.objects global (18
        vanos únicos en la línea) — NO de VanoSemestre (que tendría 18+8=26
        filas si se sumaran S1+S2). Prueba que el path viejo no se tocó."""
        ctx = _invoke_get_context(self.admin, linea_id=str(self.linea.id))
        self.assertEqual(ctx["total_vanos"], 18)  # NO 26
        self.assertEqual(len(ctx["vanos"]), 18)
        self.assertEqual(ctx["semestre"], "")

    def test_semestre_ausente_devuelve_string_vacio_en_contexto(self):
        ctx = _invoke_get_context(self.admin, linea_id=str(self.linea.id))
        self.assertIn("semestre", ctx)
        self.assertEqual(ctx["semestre"], "")

    # ------------------------------------------------------------------
    # Edge cases del parámetro
    # ------------------------------------------------------------------
    def test_semestre_invalido_se_comporta_como_sin_filtro(self):
        ctx = _invoke_get_context(self.admin, linea_id=str(self.linea.id), semestre="XX")
        self.assertEqual(ctx["total_vanos"], 18)
        self.assertEqual(ctx["semestre"], "")

    def test_semestre_minuscula_aceptado_case_insensitive(self):
        ctx = _invoke_get_context(self.admin, linea_id=str(self.linea.id), semestre="s1")
        self.assertEqual(ctx["total_vanos"], 18)
        self.assertEqual(ctx["semestre"], "S1")

    def test_semestre_con_espacios_se_normaliza(self):
        ctx = _invoke_get_context(self.admin, linea_id=str(self.linea.id), semestre="  s2  ")
        self.assertEqual(ctx["total_vanos"], 8)
        self.assertEqual(ctx["semestre"], "S2")

    # ------------------------------------------------------------------
    # Dato legacy: Vano preexistente sin VanoSemestre configurado
    # ------------------------------------------------------------------
    def test_linea_legacy_sin_vanosemestre_filtrada_da_vacio_sin_crashear(self):
        ctx = _invoke_get_context(self.admin, linea_id=str(self.linea_legacy.id), semestre="S1")
        self.assertEqual(ctx["total_vanos"], 0)
        self.assertEqual(len(ctx["vanos"]), 0)
        self.assertEqual(ctx["porcentaje"], 0)  # sin división por cero
        self.assertFalse(ctx.get("error"))

    def test_linea_legacy_sin_filtro_sigue_mostrando_sus_5_vanos(self):
        # Regresión: el dato legacy (Vano sin VanoSemestre) NO debe
        # desaparecer del path sin filtro.
        ctx = _invoke_get_context(self.admin, linea_id=str(self.linea_legacy.id))
        self.assertEqual(ctx["total_vanos"], 5)
        self.assertEqual(len(ctx["vanos"]), 5)
