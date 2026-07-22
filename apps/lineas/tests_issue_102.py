"""
Tests #102 (bounce=2, FIX_INCOMPLETO) — Parser de texto libre español para
listas/rangos de vanos, resolución de Línea(s) por etiqueta del Excel real,
``Linea.sincronizar_vanos_set`` y la migración de datos versionada 0017.

Convención: flat file ``tests_issue_102.py`` (mismo patrón que
``tests_b21.py``/``tests_vanos_sync.py`` — TestCase de Django, runnable con
``python manage.py test apps.lineas.tests_issue_102``). La app ``lineas``
también tiene un paquete ``tests/`` (``test_issue_177.py``,
``test_issue_182.py``) pero esos usan clases ``@pytest.mark.django_db`` NO
discoverables por ``manage.py test`` (unittest discovery real) — se prefiere
el patrón flat+TestCase, consistente con el resto de B2.1.

Cubre:
- parse_vano_list: rango simple, rango con offset (no arranca en 1, caso
  LN842), lista explícita con "y", caso no-contiguo (LN734), tokens
  no-numéricos descartados (no fatal), sub-grupos etiquetados (";"+"(...)"),
  CASOS_ESPECIALES (LN807/808 S1), fail-loud (VanoParseError) sin override.
- MAPEO_EXCEL_A_LINEAS / _resolver_lineas: doble circuito -> 2 Líneas,
  etiqueta bloqueada -> lista vacía, exclusiones documentadas ausentes.
- Linea.sincronizar_vanos_set: idempotencia, no-destructivo, set arbitrario
  no contiguo, cap MAX_VANOS_AUTOGENERADOS, entradas inválidas.
- Migración 0017 (invocada directo, no vía `migrate`): dato legacy real
  LN5114 (100 Vano preexistentes de #101) no se rompe ni duplica.
"""

import importlib.util
import os

from django.test import TestCase

from apps.lineas.importers_b21 import (
    CASOS_ESPECIALES,
    MAPEO_EXCEL_A_LINEAS,
    VanoParseError,
    _resolver_lineas,
    parse_vano_list,
)
from apps.lineas.models import Linea, Vano
from apps.lineas.models_b21 import VanoSemestre


def _linea(codigo, nombre=None):
    return Linea.objects.create(
        codigo=codigo,
        nombre=nombre or f"Test {codigo}",
        cliente=Linea.Cliente.TRANSELCA,
    )


class TestParseVanoListRangoYLista(TestCase):
    """Casos "normales": rango simple y lista explícita."""

    def test_rango_simple_1_al_n(self):
        self.assertEqual(parse_vano_list("1 al 104"), set(range(1, 105)))

    def test_rango_simple_variantes_de_texto(self):
        # "1 a 104", "1 a la 35", "3 a 11" — todas variantes reales del Excel.
        self.assertEqual(parse_vano_list("1 a 104"), set(range(1, 105)))
        self.assertEqual(parse_vano_list("1 a la 35"), set(range(1, 36)))
        self.assertEqual(parse_vano_list("3 a 11"), set(range(3, 12)))

    def test_rango_con_offset_no_arranca_en_1_caso_ln842(self):
        # LN842 (bloqueada por Linea inexistente, pero el PARSER en sí debe
        # poder con el texto: "141 a la 240").
        self.assertEqual(parse_vano_list("141 a la 240"), set(range(141, 241)))

    def test_lista_explicita_con_y(self):
        self.assertEqual(
            parse_vano_list("2, 3, 4, 5, 7, 12, 16 y 17"),
            {2, 3, 4, 5, 7, 12, 16, 17},
        )

    def test_caso_no_contiguo_ln734(self):
        # LN734 S2: arranca en 3, con huecos (no incluye 5, 7, 10, 11...).
        texto = (
            "3, 4, 6, 8, 9, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, "
            "24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34 y 35"
        )
        resultado = parse_vano_list(texto)
        self.assertEqual(len(resultado), 29)
        self.assertNotIn(5, resultado)
        self.assertNotIn(7, resultado)
        self.assertIn(3, resultado)
        self.assertIn(35, resultado)

    def test_tokens_no_numericos_se_descartan_sin_fallar(self):
        # LN805 S2 trae "S/E Sabana Portico" mezclado con números reales.
        texto = "S/E Sabana Portico, 1, 2, 5"
        resultado = parse_vano_list(texto)
        self.assertEqual(resultado, {1, 2, 5})

    def test_sufijo_postes_se_ignora(self):
        # LN5156/5157: "1 al 264 postes".
        self.assertEqual(parse_vano_list("1 al 264 postes"), set(range(1, 265)))


class TestParseVanoListSubgrupos(TestCase):
    """Caso ambiguo: sub-grupos etiquetados con ';' + '(...)' (único caso
    real del dataset: LN 821/822, LN 821/826, LN 838/826, LN 822/826 S2)."""

    def test_subgrupos_etiquetados_devuelve_dict(self):
        texto = "(821/822) 5, 7, 10 y 23; (838/826) 13, 21, 22 y 31"
        resultado = parse_vano_list(texto)
        self.assertIsInstance(resultado, dict)
        self.assertEqual(set(resultado.keys()), {"821/822", "838/826"})
        self.assertEqual(resultado["821/822"], {5, 7, 10, 23})
        self.assertEqual(resultado["838/826"], {13, 21, 22, 31})

    def test_subgrupo_no_reconocido_falla_ruidoso(self):
        with self.assertRaises(VanoParseError):
            parse_vano_list("(821/822) 5, 7; sin-parentesis 10 y 23")


class TestParseVanoListCasoAmbiguo807808(TestCase):
    """Caso ambiguo LN807/808 S1 — texto irresoluble por regex puro, override
    manual vía CASOS_ESPECIALES."""

    def test_texto_literal_807_808_s1_usa_caso_especial(self):
        texto = "Torre 5 (propiedad EEB) a la 42 y de la 42 a la 148"
        resultado = parse_vano_list(texto, etiqueta_excel="LN 807/808", semestre="S1")
        self.assertEqual(resultado, set(range(5, 113)))
        self.assertEqual(len(resultado), 108)

    def test_caso_especial_esta_documentado_en_el_dict(self):
        self.assertIn(("LN 807/808", "S1"), CASOS_ESPECIALES)

    def test_mismo_texto_sin_etiqueta_semestre_falla_ruidoso(self):
        # Sin (etiqueta_excel, semestre) no hay match en CASOS_ESPECIALES —
        # debe fallar ruidoso, NUNCA devolver set vacío en silencio.
        texto = "Torre 5 (propiedad EEB) a la 42 y de la 42 a la 148"
        with self.assertRaises(VanoParseError):
            parse_vano_list(texto)


class TestParseVanoListFailLoud(TestCase):
    """Fail-loud: nunca set vacío silencioso."""

    def test_texto_vacio_falla(self):
        with self.assertRaises(VanoParseError):
            parse_vano_list("")

    def test_texto_none_falla(self):
        with self.assertRaises(VanoParseError):
            parse_vano_list(None)

    def test_texto_solo_no_numerico_falla(self):
        with self.assertRaises(VanoParseError):
            parse_vano_list("S/E Sabana Portico, Torre 5 (propiedad EEB)")


class TestMapeoExcelALineas(TestCase):
    """MAPEO_EXCEL_A_LINEAS documenta doble-circuito y bloqueos/exclusiones."""

    def test_doble_circuito_2_lineas(self):
        self.assertEqual(MAPEO_EXCEL_A_LINEAS["LN 764/765"], ["LN764", "LN765"])

    def test_lineas_bloqueadas_lista_vacia(self):
        self.assertEqual(MAPEO_EXCEL_A_LINEAS["LN 842"], [])
        self.assertEqual(MAPEO_EXCEL_A_LINEAS["LN 792"], [])

    def test_exclusiones_confianza_baja_ausentes_del_grupo(self):
        # LN813 excluida del grupo 811/812/813 (desproporción severa).
        self.assertNotIn("LN813", MAPEO_EXCEL_A_LINEAS["LN 811/812 y LN 812/813"])
        # LN814 excluida del grupo 814/815/834.
        self.assertNotIn("LN814", MAPEO_EXCEL_A_LINEAS["LN 814/815 y LN 834/815"])
        # LN821/LN822 excluidas del grupo 821/822/826/838 (torres≈0 en BD).
        grupo_821 = MAPEO_EXCEL_A_LINEAS["LN 821/822, LN 821/826, LN 838/826, LN 822/826"]
        self.assertNotIn("LN821", grupo_821)
        self.assertNotIn("LN822", grupo_821)


class TestResolverLineas(TestCase):
    def test_resuelve_doble_circuito_a_2_lineas(self):
        _linea("LN764")
        _linea("LN765")
        lineas = _resolver_lineas("LN 764/765")
        self.assertEqual({ln.codigo for ln in lineas}, {"LN764", "LN765"})

    def test_etiqueta_bloqueada_devuelve_lista_vacia(self):
        self.assertEqual(_resolver_lineas("LN 842"), [])

    def test_etiqueta_no_mapeada_devuelve_lista_vacia(self):
        self.assertEqual(_resolver_lineas("LN 99999"), [])

    def test_codigo_mapeado_pero_ausente_en_bd_se_omite(self):
        # LN764 mapeada pero no creada en BD -> se omite (no crashea).
        _linea("LN765")
        lineas = _resolver_lineas("LN 764/765")
        self.assertEqual({ln.codigo for ln in lineas}, {"LN765"})


class TestSincronizarVanosSet(TestCase):
    """Generaliza sincronizar_vanos (#101) a un set arbitrario no contiguo."""

    def test_crea_set_no_contiguo(self):
        linea = _linea("L-102A")
        creados = linea.sincronizar_vanos_set({2, 3, 4, 5, 7, 12, 16, 17})
        self.assertEqual(creados, 8)
        self.assertEqual(linea.vanos.count(), 8)
        numeros = set(linea.vanos.values_list("numero", flat=True))
        self.assertEqual(numeros, {"2", "3", "4", "5", "7", "12", "16", "17"})

    def test_rango_con_offset(self):
        # Caso LN842: "141 a la 240" — NO debe crear vanos 1..140.
        linea = _linea("L-102B")
        creados = linea.sincronizar_vanos_set(set(range(141, 241)))
        self.assertEqual(creados, 100)
        self.assertEqual(linea.vanos.count(), 100)
        self.assertFalse(linea.vanos.filter(numero="1").exists())
        self.assertTrue(linea.vanos.filter(numero="141").exists())
        self.assertTrue(linea.vanos.filter(numero="240").exists())

    def test_idempotente(self):
        linea = _linea("L-102C")
        self.assertEqual(linea.sincronizar_vanos_set({1, 2, 3}), 3)
        # Segunda corrida con el MISMO set: 0 nuevos, sin duplicados.
        self.assertEqual(linea.sincronizar_vanos_set({1, 2, 3}), 0)
        self.assertEqual(linea.vanos.count(), 3)

    def test_ampliar_solo_crea_faltantes(self):
        linea = _linea("L-102D")
        linea.sincronizar_vanos_set({1, 2, 3})
        creados = linea.sincronizar_vanos_set({2, 3, 4, 5})
        self.assertEqual(creados, 2)  # solo 4 y 5 son nuevos
        self.assertEqual(linea.vanos.count(), 5)

    def test_no_destructivo_preserva_estado(self):
        linea = _linea("L-102E")
        linea.sincronizar_vanos_set({1, 2, 3})
        v = linea.vanos.get(numero="2")
        v.estado = Vano.Estado.EJECUTADO
        v.save(update_fields=["estado"])
        linea.sincronizar_vanos_set({1, 2, 3})  # re-run
        self.assertEqual(linea.vanos.get(numero="2").estado, Vano.Estado.EJECUTADO)

    def test_cap_max_autogenerados(self):
        linea = _linea("L-102F")
        numeros = set(range(1, Linea.MAX_VANOS_AUTOGENERADOS + 501))
        creados = linea.sincronizar_vanos_set(numeros)
        self.assertEqual(creados, Linea.MAX_VANOS_AUTOGENERADOS)
        self.assertEqual(linea.vanos.count(), Linea.MAX_VANOS_AUTOGENERADOS)

    def test_entradas_invalidas_se_ignoran(self):
        linea = _linea("L-102G")
        creados = linea.sincronizar_vanos_set({1, "abc", None, -5, 0, 2})
        self.assertEqual(creados, 2)
        self.assertEqual(linea.vanos.count(), 2)

    def test_set_vacio_devuelve_cero(self):
        linea = _linea("L-102H")
        self.assertEqual(linea.sincronizar_vanos_set(set()), 0)
        self.assertEqual(linea.sincronizar_vanos_set(None), 0)


class TestMigracion0017CargaVanosSemestre(TestCase):
    """
    Invoca la función RunPython de la migración 0017 directamente (no vía
    ``manage.py migrate`` — la suite corre con ``--nomigrations``/BD SQLite
    efímera por test; invocar la función a mano sobre los modelos REALES ya
    creados en `setUp` es equivalente y más rápido). Cubre el requisito de
    "test contra dato legacy real": LN5114 con 100 Vano preexistentes (como
    en prod, #101) no se rompe ni duplica.
    """

    @classmethod
    def _cargar_funcion_migracion(cls):
        ruta = os.path.join(
            os.path.dirname(__file__),
            "migrations",
            "0017_carga_vanos_semestre_completa.py",
        )
        spec = importlib.util.spec_from_file_location("mig_0017_test", ruta)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        return modulo

    def setUp(self):
        self.mig = self._cargar_funcion_migracion()
        # Dato legacy real: LN5114 con 100 Vano preexistentes (numero 1..100),
        # igual que en prod tras #101.
        self.ln5114 = _linea("LN5114")
        Vano.objects.bulk_create([Vano(linea=self.ln5114, numero=str(i)) for i in range(1, 101)])
        # Resto de líneas usadas por el subconjunto de filas que ejercito
        # en este test (no las 35 completas — cubierto end-to-end contra
        # SQLite real durante el desarrollo de F3, ver JSON de salida).
        for codigo in ("LN733", "LN5156", "LN5157", "LN826", "LN838"):
            _linea(codigo)

    def test_dato_legacy_ln5114_no_se_rompe_ni_duplica(self):
        self.mig.cargar_vanos_semestre(None, None)

        self.ln5114.refresh_from_db()
        # 104 vanos totales: 100 preexistentes + 4 nuevos (101-104, S1='1 al 104').
        self.assertEqual(self.ln5114.vanos.count(), 104)
        # El vano #1 preexistente sigue siendo el mismo registro (no duplicado).
        self.assertEqual(self.ln5114.vanos.filter(numero="1").count(), 1)
        s1_count = VanoSemestre.objects.filter(vano__linea=self.ln5114, semestre="S1").count()
        self.assertEqual(s1_count, 104)

    def test_discriminante_ln733_s1_vs_s2(self):
        self.mig.cargar_vanos_semestre(None, None)
        linea = Linea.objects.get(codigo="LN733")
        s1 = VanoSemestre.objects.filter(vano__linea=linea, semestre="S1").count()
        s2 = VanoSemestre.objects.filter(vano__linea=linea, semestre="S2").count()
        self.assertEqual(s1, 18)
        self.assertEqual(s2, 8)
        self.assertNotEqual(s1, s2)

    def test_ln5156_5157_s1_sin_s2_senal_negativa(self):
        # "Sin trabajo registrado en S2" -- NO debe crear VanoSemestre S2.
        self.mig.cargar_vanos_semestre(None, None)
        ln5156 = Linea.objects.get(codigo="LN5156")
        ln5157 = Linea.objects.get(codigo="LN5157")
        self.assertEqual(
            VanoSemestre.objects.filter(vano__linea=ln5156, semestre="S1").count(), 264
        )
        self.assertEqual(VanoSemestre.objects.filter(vano__linea=ln5156, semestre="S2").count(), 0)
        self.assertEqual(
            VanoSemestre.objects.filter(vano__linea=ln5157, semestre="S1").count(), 264
        )

    def test_subgrupo_821_826_838_826_no_mezcla_lineas(self):
        # S1 solo LN826; S2 desglosado (LN826 sub-segmento 821/826, LN838
        # sub-segmento 838/826), sub-segmento 821/822 EXCLUIDO por completo.
        self.mig.cargar_vanos_semestre(None, None)
        ln826 = Linea.objects.get(codigo="LN826")
        ln838 = Linea.objects.get(codigo="LN838")
        self.assertEqual(VanoSemestre.objects.filter(vano__linea=ln826, semestre="S1").count(), 90)
        self.assertEqual(VanoSemestre.objects.filter(vano__linea=ln826, semestre="S2").count(), 43)
        self.assertEqual(VanoSemestre.objects.filter(vano__linea=ln838, semestre="S1").count(), 0)
        self.assertEqual(VanoSemestre.objects.filter(vano__linea=ln838, semestre="S2").count(), 4)

    def test_idempotente_re_ejecutar_no_duplica(self):
        self.mig.cargar_vanos_semestre(None, None)
        primero = VanoSemestre.objects.count()
        self.mig.cargar_vanos_semestre(None, None)
        segundo = VanoSemestre.objects.count()
        self.assertEqual(primero, segundo)

    def test_linea_bloqueada_no_crashea_la_migracion_completa(self):
        # LN842/LN792 no están en FILAS_EXCEL -- no deberían generar ningún
        # intento de resolución. El resto de líneas SÍ deben cargar bien
        # (la migración no aborta por completo ante bloqueos).
        self.mig.cargar_vanos_semestre(None, None)  # no debe lanzar excepción
        self.assertGreater(VanoSemestre.objects.count(), 0)

    def test_reverse_borra_solo_vanosemestre_no_vanos(self):
        self.mig.cargar_vanos_semestre(None, None)
        total_vanos_antes = Vano.objects.count()
        self.assertGreater(VanoSemestre.objects.count(), 0)

        self.mig.revertir_vanos_semestre(None, None)

        self.assertEqual(VanoSemestre.objects.count(), 0)
        # No destructivo: los Vano materializados quedan (incluidos los 100
        # preexistentes de LN5114 + los nuevos que la migración creó).
        self.assertEqual(Vano.objects.count(), total_vanos_antes)
