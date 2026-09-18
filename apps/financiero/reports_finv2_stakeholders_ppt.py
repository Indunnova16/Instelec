"""PPT para stakeholders del dashboard financiero integrado (#246 Sprint D).

Consume el mismo ``payload`` que ``reports_finv2_ejecutivo_pdf`` -- ver su
docstring.

**Sin dependencia nueva a propósito**: ``python-pptx`` NO está declarado en
ningún ``requirements/*.txt`` del repo (verificado con
``grep -riE "reportlab|weasyprint|openpyxl|pptx" requirements/*.txt`` antes
de escribir este archivo -- solo WeasyPrint y openpyxl existen, para PDF y
Excel respectivamente) y ``requirements/*.txt`` no está en el
``FILES_OWNED`` de esta sub-feature, así que agregarlo ahí queda fuera de
alcance (habría que pedir scope ampliado). En vez de bloquear la
sub-feature por una dependencia de infraestructura, este módulo construye el
``.pptx`` directamente como el paquete OOXML que es -- un zip con partes XML
bien formadas (``[Content_Types].xml``, ``_rels``, ``ppt/presentation.xml``,
un slide master + layout mínimos y un ``<p:sld>`` por diapositiva con cajas
de texto planas, sin placeholders heredados de layout). Es exactamente lo
que produce cualquier librería de generación de pptx por debajo; aquí se
arma explícito con ``zipfile`` + XML de la librería estándar, sin más
dependencias que las que Python ya trae.
"""

from __future__ import annotations

import zipfile
from decimal import Decimal
from html import escape as _xml_escape
from io import BytesIO
from typing import Any

ZERO = Decimal("0.00")

_EMU_ANCHO = 12192000  # 13.33in, 16:9
_EMU_ALTO = 6858000  # 7.5in, 16:9

_CONTENT_TYPES_TMPL = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
  <Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
  <Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
{slide_overrides}  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
"""

_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"""

_PRESENTATION_TMPL = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldMasterIdLst>
    <p:sldMasterId id="2147483648" r:id="rId1"/>
  </p:sldMasterIdLst>
  <p:sldIdLst>
{sld_id_list}  </p:sldIdLst>
  <p:sldSz cx="{ancho}" cy="{alto}" type="screen16x9"/>
  <p:notesSz cx="6858000" cy="9144000"/>
</p:presentation>
"""

_PRESENTATION_RELS_TMPL = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>
{slide_rels}  <Relationship Id="rIdTheme" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/>
</Relationships>
"""

_SLIDE_MASTER_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:bg><p:bgPr><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr/>
    </p:spTree>
  </p:cSld>
  <p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>
  <p:sldLayoutIdLst>
    <p:sldLayoutId id="2147483649" r:id="rId1"/>
  </p:sldLayoutIdLst>
</p:sldMaster>
"""

_SLIDE_MASTER_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>
"""

_SLIDE_LAYOUT_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1">
  <p:cSld name="Blank">
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr/>
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sldLayout>
"""

_SLIDE_LAYOUT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>
"""

_SLIDE_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
</Relationships>
"""

# Theme mínimo pero completo (colores/fuentes/formatScheme con los 3 niveles
# que PowerPoint espera en fmtScheme -- omitir alguno produce "reparación
# necesaria" al abrir el archivo).
_THEME_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Instelec Financiero">
  <a:themeElements>
    <a:clrScheme name="Instelec">
      <a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>
      <a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>
      <a:dk2><a:srgbClr val="1E3A8A"/></a:dk2>
      <a:lt2><a:srgbClr val="E5E7EB"/></a:lt2>
      <a:accent1><a:srgbClr val="1E3A8A"/></a:accent1>
      <a:accent2><a:srgbClr val="047857"/></a:accent2>
      <a:accent3><a:srgbClr val="B91C1C"/></a:accent3>
      <a:accent4><a:srgbClr val="B45309"/></a:accent4>
      <a:accent5><a:srgbClr val="4338CA"/></a:accent5>
      <a:accent6><a:srgbClr val="0E7490"/></a:accent6>
      <a:hlink><a:srgbClr val="2563EB"/></a:hlink>
      <a:folHlink><a:srgbClr val="7C3AED"/></a:folHlink>
    </a:clrScheme>
    <a:fontScheme name="Instelec">
      <a:majorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>
      <a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont>
    </a:fontScheme>
    <a:fmtScheme name="Instelec">
      <a:fillStyleLst>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
      </a:fillStyleLst>
      <a:lnStyleLst>
        <a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>
        <a:ln w="12700"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>
        <a:ln w="19050"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>
      </a:lnStyleLst>
      <a:effectStyleLst>
        <a:effectStyle><a:effectLst/></a:effectStyle>
        <a:effectStyle><a:effectLst/></a:effectStyle>
        <a:effectStyle><a:effectLst/></a:effectStyle>
      </a:effectStyleLst>
      <a:bgFillStyleLst>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
      </a:bgFillStyleLst>
    </a:fmtScheme>
  </a:themeElements>
</a:theme>
"""

_CORE_XML_TMPL = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{titulo}</dc:title>
  <dc:creator>Sistema financiero Instelec</dc:creator>
  <cp:lastModifiedBy>Sistema financiero Instelec</cp:lastModifiedBy>
</cp:coreProperties>
"""

_APP_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Indunnova Financiero</Application>
</Properties>
"""


def _money(valor: Any) -> str:
    if valor is None:
        return "--"
    try:
        return f"${Decimal(valor).quantize(Decimal('0.01')):,.2f}"
    except Exception:
        return str(valor)


def _run(texto: str, *, tamano: int = 1800, negrita: bool = False, color: str | None = None) -> str:
    props = f'lang="es-CO" sz="{tamano}"' + (' b="1"' if negrita else "")
    fill = f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>' if color else ""
    return f"<a:r><a:rPr {props}>{fill}</a:rPr><a:t>{_xml_escape(texto)}</a:t></a:r>"


def _parrafo(
    texto: str,
    *,
    tamano: int = 1800,
    negrita: bool = False,
    color: str | None = None,
    vineta: bool = False,
) -> str:
    p_props = (
        '<a:pPr marL="285750" indent="-285750"><a:buChar char="&#8226;"/></a:pPr>'
        if vineta
        else "<a:pPr/>"
    )
    return f"<a:p>{p_props}{_run(texto, tamano=tamano, negrita=negrita, color=color)}</a:p>"


def _caja_texto(
    shape_id: int, nombre: str, *, x: int, y: int, cx: int, cy: int, parrafos: str
) -> str:
    return f"""<p:sp>
  <p:nvSpPr>
    <p:cNvPr id="{shape_id}" name="{_xml_escape(nombre)}"/>
    <p:cNvSpPr txBox="1"/>
    <p:nvPr/>
  </p:nvSpPr>
  <p:spPr>
    <a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>
    <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
  </p:spPr>
  <p:txBody>
    <a:bodyPr wrap="square"><a:normAutofit/></a:bodyPr>
    <a:lstStyle/>
    {parrafos}
  </p:txBody>
</p:sp>"""


def _slide_xml(titulo: str, lineas: list[str], *, subtitulo: str = "") -> str:
    """Título (arriba) + cuerpo con viñetas (abajo) -- layout de todas las
    diapositivas salvo la portada."""
    titulo_box = _caja_texto(
        2,
        "Título",
        x=457200,
        y=274638,
        cx=_EMU_ANCHO - 914400,
        cy=914400,
        parrafos=_parrafo(titulo, tamano=3200, negrita=True, color="1E3A8A"),
    )
    cuerpo_parrafos = "".join(
        _parrafo(linea, tamano=1800, vineta=True) for linea in lineas
    ) or _parrafo("Sin datos para este período/proyecto.", tamano=1800)
    if subtitulo:
        cuerpo_parrafos = _parrafo(subtitulo, tamano=1400, color="6B7280") + cuerpo_parrafos
    cuerpo_box = _caja_texto(
        3,
        "Cuerpo",
        x=457200,
        y=1257300,
        cx=_EMU_ANCHO - 914400,
        cy=_EMU_ALTO - 1600200,
        parrafos=cuerpo_parrafos,
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr/>
      {titulo_box}
      {cuerpo_box}
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>
"""


def _slide_portada(titulo: str, subtitulo: str) -> str:
    titulo_box = _caja_texto(
        2,
        "Título portada",
        x=685800,
        y=2286000,
        cx=_EMU_ANCHO - 1371600,
        cy=1143000,
        parrafos=_parrafo(titulo, tamano=4000, negrita=True, color="1E3A8A"),
    )
    subtitulo_box = _caja_texto(
        3,
        "Subtítulo portada",
        x=685800,
        y=3429000,
        cx=_EMU_ANCHO - 1371600,
        cy=914400,
        parrafos=_parrafo(subtitulo, tamano=2000, color="374151"),
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr/>
      {titulo_box}
      {subtitulo_box}
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>
"""


def _valor_indicador(indicador: dict) -> str:
    if indicador.get("sin_base") or indicador.get("valor") is None:
        return "Sin base comparable"
    if indicador.get("unidad") == "%":
        return f"{indicador['valor']}%"
    return _money(indicador["valor"])


def _construir_slides(payload: dict) -> list[str]:
    """Portada, resumen, 6 slides de indicadores, conclusiones -- 9
    diapositivas, versión 1.0 completa (Sprint D)."""
    proyecto = payload.get("proyecto")
    proyecto_nombre = str(proyecto) if proyecto else "Todos los proyectos"
    periodo = f"{payload['mes']:02d}/{payload['anio']}"

    slides = [
        _slide_portada("Reporte Financiero Ejecutivo", f"{proyecto_nombre} · Período {periodo}")
    ]

    resumen_totales = payload.get("resumen_totales") or {}
    gastos = payload.get("integracion_gastos") or {}
    ingresos = payload.get("integracion_ingresos") or {}
    resumen_lineas = [
        f"Costo real del período: {_money(resumen_totales.get('costo_real'))}",
        f"Costo presupuestado: {_money(resumen_totales.get('costo_presupuestado'))}",
        f"Gastos registrados: {_money(gastos.get('total'))} ({gastos.get('cantidad', 0)} facturas)",
        f"Ingresos facturados: {_money(ingresos.get('total'))} ({ingresos.get('cantidad', 0)} facturas)",
    ]
    slides.append(_slide_xml("Resumen ejecutivo", resumen_lineas))

    indicadores = payload.get("indicadores") or []
    if not indicadores:
        indicadores = [
            {
                "nombre": f"Indicador {i + 1}",
                "valor": None,
                "sin_base": True,
                "alerta": False,
                "causa": "",
            }
            for i in range(6)
        ]
    for indicador in indicadores[:6]:
        lineas = [f"Valor: {_valor_indicador(indicador)}"]
        lineas.append("Estado: ⚠ Alerta" if indicador.get("alerta") else "Estado: OK")
        if indicador.get("causa"):
            lineas.append(indicador["causa"])
        slides.append(_slide_xml(str(indicador.get("nombre", "Indicador")), lineas))

    conclusiones = [i.get("causa") for i in indicadores if i.get("alerta") and i.get("causa")]
    if not conclusiones:
        conclusiones = [
            "Sin alertas activas: la ejecución del período está dentro de lo presupuestado."
        ]
    slides.append(_slide_xml("Conclusiones", conclusiones))
    return slides


def generar_ppt_stakeholders(payload: dict) -> bytes:
    """Portada, resumen, 6 slides de indicadores, conclusiones -- versión
    1.0 completa (Sprint D). Ver docstring del módulo: `.pptx` construido a
    mano vía OOXML/zipfile, sin dependencia nueva."""
    slides = _construir_slides(payload)
    n = len(slides)

    slide_overrides = "".join(
        f'  <Override PartName="/ppt/slides/slide{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>\n'
        for i in range(1, n + 1)
    )
    sld_id_list = "".join(
        f'    <p:sldId id="{256 + i - 1}" r:id="rIdSlide{i}"/>\n' for i in range(1, n + 1)
    )
    slide_rels = "".join(
        f'  <Relationship Id="rIdSlide{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{i}.xml"/>\n'
        for i in range(1, n + 1)
    )

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "[Content_Types].xml", _CONTENT_TYPES_TMPL.format(slide_overrides=slide_overrides)
        )
        z.writestr("_rels/.rels", _ROOT_RELS)
        z.writestr(
            "docProps/core.xml", _CORE_XML_TMPL.format(titulo="Reporte Financiero Ejecutivo")
        )
        z.writestr("docProps/app.xml", _APP_XML)
        z.writestr(
            "ppt/presentation.xml",
            _PRESENTATION_TMPL.format(sld_id_list=sld_id_list, ancho=_EMU_ANCHO, alto=_EMU_ALTO),
        )
        z.writestr(
            "ppt/_rels/presentation.xml.rels", _PRESENTATION_RELS_TMPL.format(slide_rels=slide_rels)
        )
        z.writestr("ppt/slideMasters/slideMaster1.xml", _SLIDE_MASTER_XML)
        z.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", _SLIDE_MASTER_RELS)
        z.writestr("ppt/slideLayouts/slideLayout1.xml", _SLIDE_LAYOUT_XML)
        z.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", _SLIDE_LAYOUT_RELS)
        z.writestr("ppt/theme/theme1.xml", _THEME_XML)
        for i, slide_xml in enumerate(slides, start=1):
            z.writestr(f"ppt/slides/slide{i}.xml", slide_xml)
            z.writestr(f"ppt/slides/_rels/slide{i}.xml.rels", _SLIDE_RELS)

    return buffer.getvalue()
