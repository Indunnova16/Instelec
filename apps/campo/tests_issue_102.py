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


class RegistroAvanceCreateViewSelectorSemestreTests(TestCase):
    """Tests #102 (bounce=3) — Wiring de ``?semestre=`` en el SELECTOR de
    líneas (rama ``if not linea_id:`` de ``_build_context``), la pantalla
    ``/campo/avance/registrar/`` SIN ``linea_id`` (tarjetas por línea, antes
    de elegir una).

    Causa raíz (F2, confirmada contra prod con 4 líneas reales — LN5114,
    LN5156, LN5157, LN733, LN734): esta rama nunca leía ``?semestre=`` —
    las tarjetas del template usaban ``{{ l.vanos.count }}`` (total fijo de
    ``Vano``), por eso el selector mostraba EXACTAMENTE los mismos números
    para S1/S2/"Todos los semestres" en las 4 capturas del comentario
    actual del cliente ("son iguales"). Esta rama es DISTINTA de la ya
    cableada en bounce=2 (grid CON ``linea_id`` elegida, cubierta arriba
    por ``RegistroAvanceCreateViewFiltroSemestreTests``).

    Cubre el escenario del cliente con >1 registro (3 líneas con perfiles
    de datos distintos — replica el patrón real de prod: LN733 18/8,
    LN5156 264/0, LN5114 104/104 "con suerte") para no repetir el error de
    ``validado_1_registro`` del post-mortem de bounce=2.
    """

    def setUp(self):
        # ``get_lineas_activas()`` (apps/core/cache.py) cachea la lista de
        # líneas activas 1h (``django.core.cache``, independiente de la
        # transacción de test) — sin esto, las líneas de este test class
        # quedan invisibles si otro test ya calentó el caché antes con un
        # snapshot distinto de la tabla ``lineas``.
        from django.core.cache import cache

        cache.clear()

    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_user(
            email="admin_102_sel@test.com",
            password="testpass123!",
            first_name="Admin",
            last_name="102Sel",
            rol="admin",
            is_staff=True,
            is_superuser=True,
        )

        # Línea A — equivalente LN733: S1=18, S2=8 (subset, distintos).
        cls.linea_a = _linea("LT-102SEL-A-733")
        for i in range(1, 19):
            Vano.objects.create(linea=cls.linea_a, numero=str(i))
        for n in range(1, 19):
            VanoSemestre.objects.create(
                vano=cls.linea_a.vanos.get(numero=str(n)), semestre="S1"
            )
        for n in (2, 3, 4, 5, 7, 12, 16, 17):
            VanoSemestre.objects.create(
                vano=cls.linea_a.vanos.get(numero=str(n)), semestre="S2"
            )

        # Línea B — equivalente LN5156: SOLO tiene trabajo en S1 (S2=0),
        # replica el caso real de prod donde el selector mostraba 264 en
        # AMBOS semestres cuando S2 debía ser 0 / "Sin vanos en este período".
        cls.linea_b = _linea("LT-102SEL-B-5156")
        for i in range(1, 11):
            Vano.objects.create(linea=cls.linea_b, numero=str(i))
        for n in range(1, 11):
            VanoSemestre.objects.create(
                vano=cls.linea_b.vanos.get(numero=str(n)), semestre="S1"
            )
        # 0 VanoSemestre con semestre="S2" para esta línea — a propósito.

        # Línea C — equivalente LN5114: coincide en ambos semestres
        # (la línea "con suerte" que no expone el bug por sí sola — de ahí
        # la necesidad de A y B en el mismo test).
        cls.linea_c = _linea("LT-102SEL-C-5114")
        for i in range(1, 6):
            Vano.objects.create(linea=cls.linea_c, numero=str(i))
        for n in range(1, 6):
            VanoSemestre.objects.create(
                vano=cls.linea_c.vanos.get(numero=str(n)), semestre="S1"
            )
            VanoSemestre.objects.create(
                vano=cls.linea_c.vanos.get(numero=str(n)), semestre="S2"
            )

    def _counts_by_linea(self, semestre=None):
        ctx = _invoke_get_context(self.admin, linea_id=None, semestre=semestre)
        return {
            linea_obj.codigo: linea_obj.vanos_semestre_count
            for linea_obj in ctx["lineas"]
        }

    def test_selector_s1_vs_s2_conteos_distintos_multiples_lineas(self):
        """El discriminante central del bug: S1 y S2 deben dar conteos
        DISTINTOS para las líneas A y B — antes del fix daban el mismo
        número (el total) para las 3 líneas en las 3 variantes del filtro."""
        counts_s1 = self._counts_by_linea(semestre="S1")
        counts_s2 = self._counts_by_linea(semestre="S2")

        self.assertEqual(counts_s1["LT-102SEL-A-733"], 18)
        self.assertEqual(counts_s2["LT-102SEL-A-733"], 8)
        self.assertNotEqual(
            counts_s1["LT-102SEL-A-733"], counts_s2["LT-102SEL-A-733"]
        )

        self.assertEqual(counts_s1["LT-102SEL-B-5156"], 10)
        self.assertEqual(counts_s2["LT-102SEL-B-5156"], 0)

    def test_selector_sin_filtro_usa_total_vano_no_vanosemestre(self):
        """Sin ?semestre=, el selector debe seguir mostrando el TOTAL de
        Vano por línea (comportamiento histórico) — regresión."""
        counts = self._counts_by_linea(semestre=None)
        self.assertEqual(counts["LT-102SEL-A-733"], 18)
        self.assertEqual(counts["LT-102SEL-B-5156"], 10)
        self.assertEqual(counts["LT-102SEL-C-5114"], 5)

    def test_selector_linea_con_suerte_igual_en_ambos_semestres(self):
        """Línea C (equivalente LN5114 real) da el MISMO número en S1 y S2
        porque sus vanos genuinamente están configurados en ambos — esto
        NO prueba que el filtro funcione (es justo el fixture que 'por
        casualidad' no expone el bug, documentado en el post-mortem de
        bounce=2). Se incluye para dejar registrado por qué validar solo
        contra LN5114 no es suficiente."""
        counts_s1 = self._counts_by_linea(semestre="S1")
        counts_s2 = self._counts_by_linea(semestre="S2")
        self.assertEqual(counts_s1["LT-102SEL-C-5114"], 5)
        self.assertEqual(counts_s2["LT-102SEL-C-5114"], 5)

    def test_selector_semestre_invalido_se_comporta_como_sin_filtro(self):
        counts = self._counts_by_linea(semestre="XX")
        self.assertEqual(counts["LT-102SEL-A-733"], 18)

    def test_selector_context_semestre_disponible_para_preservar_en_link(self):
        """``context['semestre']`` debe estar disponible en la rama del
        selector (antes solo se seteaba en la rama con línea elegida) para
        que el template arme ``?linea_id=...&semestre=...`` al navegar."""
        ctx = _invoke_get_context(self.admin, linea_id=None, semestre="S1")
        self.assertEqual(ctx["semestre"], "S1")

    def test_selector_ta_da_cero_si_nadie_configuro_todo_el_ano(self):
        counts_ta = self._counts_by_linea(semestre="TA")
        self.assertEqual(counts_ta["LT-102SEL-A-733"], 0)
        self.assertEqual(counts_ta["LT-102SEL-B-5156"], 0)
        self.assertEqual(counts_ta["LT-102SEL-C-5114"], 0)
