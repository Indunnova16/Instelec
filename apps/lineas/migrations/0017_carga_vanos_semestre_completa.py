# Generated for Django 5.1.15 on 2026-07-22
# Issue #102 (bounce=2, FIX_INCOMPLETO) — Carga masiva REAL de VanoSemestre
# a partir del Excel att_01.xlsx del cliente (Instelec, jul-2026).
#
# Contexto (ver Instelec/SPRINTS/RUN_2026-07-22_0819/agents/Instelec_102_f2.json
# para el análisis completo de F2): la migración 0011 creó el modelo
# VanoSemestre y el management command `cargar_semestres_vanos` cargó datos
# el 26-may-2026, pero esa carga usaba `TABLA_ISSUE_102` (solo CONTEOS por
# semestre, formato "primeros N vanos") y en la práctica solo alcanzó a
# LN5114 (100 vanos). Las otras 39 Líneas de la BD quedaron con 0 Vano y
# `vano_semestres` con 0 filas — confirmado por F2 contra BD prod
# (`SELECT count(*) FROM vano_semestres` = 0 el 22-jul-2026).
#
# Esta migración usa la LISTA REAL de vanos por línea/semestre (no un
# conteo) directamente del Excel adjunto por el cliente, ya parseada con
# `apps.lineas.importers_b21.parse_vano_list` (los números de abajo son el
# resultado de correr el parser contra cada celda del Excel real — no se
# lee el .xlsx en runtime, quedan hardcodeados aquí, mismo patrón que
# `TABLA_ISSUE_102`).
#
# Scope: 22 de las 24 filas del Excel (23 etiquetas de línea + 1 fila TA
# independiente). Excluidas explícitamente (decisiones de scope de F2, NO
# bugs a corregir — ver `MAPEO_EXCEL_A_LINEAS` en importers_b21.py):
#   - LN842, LN792: la Línea NO EXISTE en BD (0 filas con codigo/nombre
#     ILIKE). NO se crea ningún stub (violaría "nunca inventar evidencia") —
#     requieren datos maestros reales del cliente, issue/decisión aparte.
#   - LN813 (del grupo 811/812/813): 69 torres reales en BD vs 178 vanos
#     pedidos — desproporción severa, confianza baja.
#   - LN814 (del grupo 814/815/834): 23 torres reales en BD vs 171 vanos
#     pedidos — desproporción severa, confianza baja.
#   - LN821, LN822 (del grupo 821/822/826/838): 1 y 0 torres reales en BD
#     respectivamente — maestro de Torres prácticamente vacío, alto riesgo
#     de crear vanos "fantasma". Del sub-desglose S2 de ese grupo, solo los
#     sub-segmentos "(821/826)" y "(838/826)" se cargan (en LN826 y LN838
#     respectivamente); el sub-segmento "(821/822)" se excluye por completo.
#
# Idempotente y re-ejecutable: `sincronizar_vanos_set` (bulk_create +
# ignore_conflicts) para materializar Vano faltantes, `get_or_create` para
# VanoSemestre. NO destructivo: nunca borra ni modifica un Vano existente
# (preserva los 100 Vano preexistentes de LN5114 cargados por #101/0011).
#
# Nota de diseño: a diferencia del resto del portafolio (que usa
# `apps.get_model()` para RunPython), esta migración importa los modelos
# REALES (`apps.lineas.models`) porque necesita invocar el método de
# negocio `Linea.sincronizar_vanos_set()` (no disponible en los modelos
# históricos de `apps.get_model()`, que solo exponen campos). Es seguro acá
# porque el método se introduce en el mismo release que esta migración (no
# hay riesgo de "migration replay" contra una versión de código donde el
# método no exista todavía).
from django.db import migrations

# ==============================================================================
# Datos parseados del Excel real (att_01.xlsx, hoja "Vanos por Semestre").
# Cada entrada: etiqueta del Excel -> {'lineas': [codigos...], 'semestres':
# {'S1'/'S2'/'TA': set(numeros)}}.
# ==============================================================================
FILAS_EXCEL = {
    'LN 5114': {
        'lineas': ['LN5114'],
        'semestres': {'S1': set(range(1, 105)), 'S2': set(range(1, 105))},
    },
    'LN 733': {
        'lineas': ['LN733'],
        'semestres': {'S1': set(range(1, 19)), 'S2': {2, 3, 4, 5, 7, 12, 16, 17}},
    },
    'LN 734': {
        'lineas': ['LN734'],
        'semestres': {
            'S1': set(range(1, 36)),
            'S2': {3, 4, 6, 8, 9, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23,
                   24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35},
        },
    },
    'LN 764/765': {
        'lineas': ['LN764', 'LN765'],
        'semestres': {'S1': set(range(1, 34)), 'S2': set(range(1, 34))},
    },
    'LN 801/802': {
        'lineas': ['LN801', 'LN802'],
        'semestres': {
            'S1': set(range(1, 88)),
            'S2': {2, 3, 5, 6, 7, 9, 10, 12, 13, 17, 18, 20, 21, 22, 23, 25, 26,
                   27, 28, 29, 32, 33, 36, 37, 38, 39, 40, 41, 44, 45, 49, 50,
                   52, 54, 55, 56, 59, 61, 62, 64, 65, 66, 68, 70, 71, 72, 76,
                   82, 85},
        },
    },
    'LN 803/804': {
        'lineas': ['LN803', 'LN804'],
        'semestres': {'S1': set(range(3, 12)), 'S2': {3, 8}},
    },
    'LN 805': {
        'lineas': ['LN805'],
        'semestres': {
            'S1': set(range(1, 247)),
            # "S/E Sabana Portico" (token no-numérico) descartado por el
            # parser (warning, no fatal) — quedan 129 números reales.
            'S2': {1, 2, 5, 7, 8, 9, 11, 12, 19, 21, 22, 25, 26, 27, 28, 29, 30,
                   31, 32, 36, 37, 38, 39, 40, 47, 48, 50, 59, 62, 63, 64, 65,
                   66, 75, 76, 79, 80, 81, 86, 91, 92, 93, 95, 104, 109, 110,
                   112, 113, 114, 115, 116, 118, 119, 120, 121, 122, 124, 125,
                   127, 128, 132, 137, 138, 139, 140, 141, 142, 143, 152, 153,
                   155, 156, 157, 158, 159, 160, 161, 162, 164, 165, 166, 167,
                   168, 169, 170, 171, 172, 173, 176, 177, 178, 179, 181, 182,
                   183, 184, 185, 186, 187, 188, 193, 194, 195, 196, 197, 198,
                   199, 200, 201, 202, 203, 205, 207, 209, 215, 218, 229, 230,
                   231, 233, 235, 236, 239, 240, 241, 242, 243, 244, 245},
        },
    },
    'LN 806/816': {
        'lineas': ['LN806', 'LN816'],
        'semestres': {
            'S1': set(range(1, 201)),
            'S2': {1, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 17, 18, 20, 22, 23,
                   24, 25, 26, 27, 28, 29, 30, 36, 38, 39, 40, 42, 43, 44, 47,
                   48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 61, 62, 63, 64,
                   66, 67, 70, 71, 74, 75, 76, 77, 78, 80, 103, 104, 106, 108,
                   109, 112, 116, 118, 121, 123, 124, 125, 131, 132, 134, 135,
                   137, 138, 139, 140, 141, 143, 148, 156, 161, 162, 163, 165,
                   168, 176, 177, 178, 182, 185, 186, 187, 192, 194, 197},
        },
    },
    'LN 839/840': {
        'lineas': ['LN839', 'LN840'],
        'semestres': {
            'S1': set(range(1, 42)),
            'S2': {1, 2, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 24, 25, 34, 35,
                   36, 37, 40, 41},
            # Fila TA independiente del Excel ("S1 y S2 (verde)", "aparece
            # igual en ambos semestres").
            'TA': {1, 2, 4, 5, 7, 10, 11, 12, 14, 23, 28, 36, 37},
        },
    },
    'LN 807/808': {
        'lineas': ['LN807', 'LN808'],
        'semestres': {
            # Texto literal del Excel: "Torre 5 (propiedad EEB) a la 42 y de
            # la 42 a la 148" (Total declarado=108). No matchea rango simple
            # ni lista explícita (parse_vano_list -> VanoParseError). F2
            # adoptó el override CASOS_ESPECIALES: rango 5-112 (108 vanos
            # EXACTOS, 112-5+1=108) porque 112 coincide EXACTO con el
            # conteo real de torres de LN807 en BD — fuerte evidencia de que
            # "148" es un error de trascripción por "112". Mismo rango
            # aplicado a LN808 (113 torres reales, 1 de más, tolerable).
            'S1': set(range(5, 113)),
            'S2': {44, 45, 48, 50, 51, 52, 53, 54, 59, 61, 63, 66, 67, 69, 72,
                   75, 77, 79, 80, 83, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94,
                   95, 96, 97, 98, 99, 100, 101, 102, 104, 106, 107, 108, 109,
                   110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121,
                   122, 123, 126, 129, 131, 133, 134, 135, 136, 137, 138, 139,
                   140, 142, 144, 145},
            # Fila TA independiente del Excel ("S1 y S2 (verde)").
            'TA': {43, 48, 49, 50, 51, 52, 53, 69, 88, 89, 90, 98, 120, 121,
                   122, 133, 134, 135, 136, 137, 138, 139, 140, 142, 143, 144,
                   145, 147},
        },
    },
    'LN 809': {
        'lineas': ['LN809'],
        'semestres': {
            'S1': set(range(1, 125)),
            'S2': {2, 3, 4, 5, 7, 8, 10, 24, 25, 26, 28, 29, 37, 72, 76, 82, 85,
                   87, 90, 92, 93, 101, 102, 104, 105, 107, 108, 116, 120, 122},
        },
    },
    'LN 810': {
        'lineas': ['LN810'],
        'semestres': {
            'S1': set(range(1, 205)),
            'S2': {1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20,
                   21, 22, 23, 24, 26, 27, 29, 30, 32, 33, 36, 39, 40, 41, 42,
                   43, 44, 45, 47, 54, 56, 67, 68, 69, 71, 72, 73, 74, 75, 76,
                   77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91,
                   92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104,
                   105, 106, 107, 111, 116, 117, 118, 119, 120, 121, 122, 123,
                   124, 128, 130, 131, 133, 135, 137, 139, 140, 141, 142, 143,
                   144, 145, 146, 147, 149, 150, 151, 152, 153, 154, 155, 156,
                   157, 158, 159, 161, 163, 164, 165, 166, 167, 168, 169, 170,
                   171, 172, 173, 174, 175, 176, 178, 179, 180, 181, 182, 183,
                   184, 185, 186, 187, 188, 189, 190, 191, 192, 193, 194, 195,
                   196, 197, 198, 199, 200, 201, 202, 203, 204, 205},
        },
    },
    # LN813 EXCLUIDA (69 torres reales vs 178 vanos pedidos — ver docstring).
    'LN 811/812 y LN 812/813': {
        'lineas': ['LN811', 'LN812'],
        'semestres': {
            'S1': set(range(1, 179)),
            'S2': {1, 2, 3, 10, 11, 18, 19, 22, 23, 24, 25, 26, 30, 31, 33, 35,
                   36, 37, 38, 39, 40, 49, 52, 53, 54, 55, 56, 57, 58, 59, 60,
                   61, 62, 63, 65, 66, 68, 69, 70, 71, 72, 73, 74, 75, 77, 78,
                   79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93,
                   94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106,
                   107, 108, 112, 114, 115, 116, 117, 118, 119, 120, 121, 122,
                   123, 124, 125, 126, 127, 128, 132, 133, 139, 141, 142, 143,
                   144, 145, 146, 148, 149, 152, 153, 156, 157, 159, 160, 162,
                   163, 164, 165, 167, 168, 172, 175, 176, 177, 178},
        },
    },
    # LN814 EXCLUIDA (23 torres reales vs 171 vanos pedidos — ver docstring).
    # Incluye la fila TA independiente 'LN 834/815, S1 y S2 (verde)'.
    'LN 814/815 y LN 834/815': {
        'lineas': ['LN815', 'LN834'],
        'semestres': {
            'S1': set(range(1, 172)),
            'S2': {1, 3, 4, 5, 7, 9, 11, 12, 13, 15, 16, 17, 20, 21, 23, 25, 29,
                   30, 31, 33, 35, 36, 37, 40, 41, 43, 44, 49, 50, 53, 56, 57,
                   60, 61, 64, 66, 70, 71, 72, 74, 75, 76, 77, 78, 79, 80, 81,
                   82, 83, 84, 85, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98,
                   99, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111,
                   112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123,
                   124, 125, 126, 127, 128, 129, 130, 131, 132, 133, 134, 135,
                   136, 137, 138, 139, 140, 141, 142, 143, 144, 146, 148, 151,
                   152, 154, 158, 159, 160, 162, 163, 165, 168, 170, 171},
            'TA': {76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 101, 102, 103, 104,
                   105, 106, 107, 108, 109, 110},
        },
    },
    'LN 817/818': {
        'lineas': ['LN817', 'LN818'],
        'semestres': {
            'S1': set(range(1, 176)),
            'S2': {1, 6, 8, 9, 10, 12, 14, 24, 27, 29, 31, 32, 33, 34, 46, 52,
                   53, 54, 55, 57, 58, 59, 60, 61, 65, 66, 67, 69, 70, 78, 80,
                   82, 83, 85, 98, 100, 108, 111, 147, 149, 158, 170, 171},
        },
    },
    'LN 819': {
        'lineas': ['LN819'],
        'semestres': {'S1': set(range(1, 141)), 'S2': {2, 3, 18, 21}},
    },
    # LN 842: Línea NO EXISTE en BD — BLOQUEADA, excluida por completo (ver
    # docstring). NO incluida en FILAS_EXCEL.
    'LN 824/825': {
        'lineas': ['LN824', 'LN825'],
        'semestres': {
            'S1': set(range(1, 46)),
            'S2': {3, 26, 31, 33, 35, 37, 38, 40, 41},
        },
    },
    'LN 827/828': {
        'lineas': ['LN827', 'LN828'],
        'semestres': {
            'S1': set(range(1, 124)),
            'S2': {6, 21, 23, 28, 31, 42, 59, 61, 63, 64, 66, 67, 68, 70, 83,
                   89, 93, 94, 99, 105, 118, 119},
        },
    },
    'LN 829/830': {
        'lineas': ['LN829', 'LN830'],
        'semestres': {'S1': set(range(1, 8)), 'S2': {1, 2, 4, 5, 6, 7}},
    },
    'LN 5156/5157': {
        'lineas': ['LN5156', 'LN5157'],
        # Doble circuito de POSTES. Solo S1 (264 vanos) -- el Excel dice
        # EXPLÍCITAMENTE "Sin trabajo registrado en S2": NO se crea
        # VanoSemestre S2 para este par (señal negativa real, no un olvido).
        'semestres': {'S1': set(range(1, 265))},
    },
    # LN 792: Línea NO EXISTE en BD — BLOQUEADA, excluida por completo (ver
    # docstring). NO incluida en FILAS_EXCEL.
}

# Fila especial: la única del dataset con sub-grupos etiquetados en S2 (ver
# parser_spec en importers_b21.py, paso de sub-grupos). S1 y S2 aplican a
# SUBCONJUNTOS DISTINTOS de líneas dentro de la misma etiqueta-fila del
# Excel, así que no encaja en la forma uniforme {'lineas': [...], 'semestres':
# {...}} de FILAS_EXCEL.
FILA_821_822_826_838 = {
    'etiqueta': 'LN 821/822, LN 821/826, LN 838/826, LN 822/826',
    # S1 (rango completo 1-90) solo a LN826 (mejor ajuste, 92 torres reales).
    's1_lineas': ['LN826'],
    's1_numeros': set(range(1, 91)),
    # S2 desglosado por sub-segmento (ver texto original: "(821/822) ...;
    # (821/826) ...; (838/826) ..."). "(821/822)" se EXCLUYE por completo
    # (LN821=1 torre, LN822=0 torres reales en BD -- maestro de Torres casi
    # inexistente, alto riesgo de vanos fantasma).
    's2_subgrupos': {
        '821/826': {
            'lineas': ['LN826'],
            'numeros': {24, 26, 27, 28, 29, 31, 33, 34, 38, 39, 40, 41, 42, 43,
                        48, 49, 51, 53, 54, 55, 56, 57, 58, 59, 60, 61, 64, 65,
                        66, 67, 68, 69, 71, 73, 75, 77, 78, 83, 85, 86, 87, 88,
                        89},
        },
        '838/826': {
            'lineas': ['LN838'],
            'numeros': {13, 21, 22, 31},
        },
        # '821/822': EXCLUIDO — LN821/LN822 fuera de scope (ver docstring).
    },
}


def _sincronizar_y_cargar_semestre(Linea, linea_codigo, semestre, numeros, resumen):
    """Resuelve 1 código de Línea, materializa los Vano faltantes con
    ``sincronizar_vanos_set`` y crea/asegura VanoSemestre (idempotente,
    ``get_or_create``) para cada número. Acumula contadores en ``resumen``
    (dict mutable) en vez de retornarlos — se llama muchas veces en el loop
    principal."""
    from apps.lineas.models import Vano, VanoSemestre

    if not numeros:
        return
    try:
        linea = Linea.objects.get(codigo=linea_codigo)
    except Linea.DoesNotExist:
        resumen['fallidas'].append(
            f"{linea_codigo}/{semestre}: Linea no existe en BD (revisar mapeo)"
        )
        return

    linea.sincronizar_vanos_set(numeros)

    vanos_por_numero = {
        v.numero: v.id
        for v in Vano.objects.filter(linea=linea, numero__in=[str(n) for n in numeros])
    }
    for n in sorted(numeros):
        vano_id = vanos_por_numero.get(str(n))
        if vano_id is None:
            # Defensivo — no debería pasar, se acaba de sincronizar.
            resumen['fallidas'].append(
                f"{linea_codigo}/{semestre}: vano {n} no se materializó (inesperado)"
            )
            continue
        _, created = VanoSemestre.objects.get_or_create(
            vano_id=vano_id,
            semestre=semestre,
            defaults={'estado': 'pendiente'},
        )
        if created:
            resumen['creados'] += 1
        else:
            resumen['existentes'] += 1


def cargar_vanos_semestre(apps, schema_editor):
    # Se usan los modelos REALES (no `apps.get_model`) — ver nota de diseño
    # en el docstring del módulo: se necesita `sincronizar_vanos_set`, que
    # los modelos históricos de `apps.get_model` no exponen.
    from apps.lineas.models import Linea

    resumen = {'creados': 0, 'existentes': 0, 'fallidas': []}

    for _etiqueta, datos in FILAS_EXCEL.items():
        for linea_codigo in datos['lineas']:
            for semestre, numeros in datos['semestres'].items():
                _sincronizar_y_cargar_semestre(
                    Linea, linea_codigo, semestre, numeros, resumen
                )

    # Fila especial multi-subgrupo (821/822/826/838).
    for linea_codigo in FILA_821_822_826_838['s1_lineas']:
        _sincronizar_y_cargar_semestre(
            Linea, linea_codigo, 'S1', FILA_821_822_826_838['s1_numeros'], resumen
        )
    for _sub_etiqueta, sub in FILA_821_822_826_838['s2_subgrupos'].items():
        for linea_codigo in sub['lineas']:
            _sincronizar_y_cargar_semestre(
                Linea, linea_codigo, 'S2', sub['numeros'], resumen
            )

    print(
        f"\n[0017_carga_vanos_semestre_completa] VanoSemestre creados={resumen['creados']} "
        f"existentes={resumen['existentes']} fallidas={len(resumen['fallidas'])}"
    )
    for f in resumen['fallidas']:
        print(f"  - {f}")


def revertir_vanos_semestre(apps, schema_editor):
    """Reversa: elimina SOLO los VanoSemestre (vano, semestre) que esta
    migración es responsable de crear — re-derivados de las mismas
    ``FILAS_EXCEL``/``FILA_821_822_826_838`` de arriba, no por un flag de
    "creado por esta migración" (el modelo no tiene uno).

    NO toca la tabla `vanos`: los Vano materializados por
    `sincronizar_vanos_set` quedan (pueden ser reusados por trabajo futuro,
    incluida la propia re-ejecución de esta migración) — mismo criterio no
    destructivo documentado en 0016_vano_historial_backfill.

    Nota: si algo AJENO a esta migración crease independientemente un
    VanoSemestre idéntico (mismo vano+semestre) entre el forward y el
    reverse, quedaría también borrado — edge case aceptado y documentado,
    no hay forma de distinguirlo sin un campo de proveniencia dedicado.
    """
    from apps.lineas.models import VanoSemestre

    def _borrar(linea_codigo, semestre, numeros):
        if not numeros:
            return
        VanoSemestre.objects.filter(
            vano__linea__codigo=linea_codigo,
            vano__numero__in=[str(n) for n in numeros],
            semestre=semestre,
        ).delete()

    for _etiqueta, datos in FILAS_EXCEL.items():
        for linea_codigo in datos['lineas']:
            for semestre, numeros in datos['semestres'].items():
                _borrar(linea_codigo, semestre, numeros)

    for linea_codigo in FILA_821_822_826_838['s1_lineas']:
        _borrar(linea_codigo, 'S1', FILA_821_822_826_838['s1_numeros'])
    for sub in FILA_821_822_826_838['s2_subgrupos'].values():
        for linea_codigo in sub['lineas']:
            _borrar(linea_codigo, 'S2', sub['numeros'])


class Migration(migrations.Migration):

    dependencies = [
        ('lineas', '0016_vano_historial_backfill'),
    ]

    operations = [
        migrations.RunPython(cargar_vanos_semestre, revertir_vanos_semestre),
    ]
