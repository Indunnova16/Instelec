"""
URL patterns for the construccion (construction) app.
"""
from django.urls import path
from django.contrib.auth.decorators import login_required
from django.views.generic import RedirectView
from . import views
from .planillas import descargar_planilla_torre

app_name = 'construccion'

urlpatterns = [
    # Projects
    path('', views.ProyectoListView.as_view(), name='lista'),
    path('<uuid:pk>/', views.ProyectoDashboardView.as_view(), name='dashboard'),

    # Project tabs
    path('<uuid:proyecto_id>/contrato/', views.ContratoView.as_view(), name='contrato'),
    path('<uuid:proyecto_id>/ingenieria/', views.IngenieriaView.as_view(), name='ingenieria'),
    path('<uuid:proyecto_id>/preliminares/', views.PreliminaresView.as_view(), name='preliminares'),

    # Torres
    path('<uuid:proyecto_id>/torres/', views.TorresListView.as_view(), name='torres_lista'),
    path('<uuid:proyecto_id>/torres/crear/', views.TorreCreateView.as_view(), name='torre_crear'),
    path('<uuid:proyecto_id>/torres/<uuid:pk>/editar/', views.TorreEditView.as_view(), name='torre_editar'),
    path('<uuid:proyecto_id>/torres/<uuid:pk>/eliminar/', views.TorreDeleteView.as_view(), name='torre_eliminar'),

    # Seguimiento Diario
    path('<uuid:proyecto_id>/seguimiento/', views.SeguimientoDiarioView.as_view(), name='seguimiento_diario'),

    # Social Predial (#51) — lista + detalle por torre con 4 actas
    path('<uuid:proyecto_id>/social/', views.SocialPredialView.as_view(), name='social_predial'),
    path('<uuid:proyecto_id>/social/<uuid:torre_id>/',
         views.SocialPredialTorreView.as_view(), name='social_predial_torre'),

    # Ambiental (#52) — lista + detalle por torre con actividades que aplican
    path('<uuid:proyecto_id>/ambiental/', views.AmbientalView.as_view(), name='ambiental'),
    path('<uuid:proyecto_id>/ambiental/<uuid:torre_id>/',
         views.AmbientalTorreView.as_view(), name='ambiental_torre'),

    # Control de Lluvia
    path('<uuid:proyecto_id>/lluvia/', views.ControlLluviaView.as_view(), name='control_lluvia'),

    # Replanteo
    path('<uuid:proyecto_id>/replanteo/', views.ReplanteoView.as_view(), name='replanteo'),

    # SST
    path('<uuid:proyecto_id>/sst/', views.SSTView.as_view(), name='sst'),

    # Entrega
    path('<uuid:proyecto_id>/entrega/', views.EntregaView.as_view(), name='entrega'),
    path('<uuid:proyecto_id>/entrega/<uuid:torre_id>/editar/',
         views.EntregaTorreView.as_view(), name='entrega_torre'),

    # Pendientes
    path('<uuid:proyecto_id>/pendientes/', views.PendientesView.as_view(), name='pendientes'),

    # Programación
    path('<uuid:proyecto_id>/programacion/', views.ProgramacionView.as_view(), name='programacion'),

    # RS Data
    path('<uuid:proyecto_id>/rs-data/', views.RSDataView.as_view(), name='rs_data'),

    # Hochimin
    path('<uuid:proyecto_id>/hochimin/', views.HochimimView.as_view(), name='hochimin'),

    # Lectura
    path('<uuid:proyecto_id>/lectura/', views.LecturaView.as_view(), name='lectura'),

    # Entrega Flechas
    path('<uuid:proyecto_id>/entrega-flechas/', views.EntregaFlechasView.as_view(), name='entrega_flechas'),

    # Electromecánica
    path('<uuid:proyecto_id>/electromecanica/', views.ElectromecanicaView.as_view(), name='electromecanica'),

    # Planillas PDF para firma de interventoría (#64)
    path('planilla/<str:codigo_ft>/torre/<uuid:torre_id>/',
         login_required(descargar_planilla_torre), name='descargar_planilla'),

    # ====== Modelos nuevos: CRUDs UI ======

    # Obras de protección (#59)
    path('<uuid:proyecto_id>/protecciones/',
         views.ObraProteccionListView.as_view(), name='protecciones_lista'),
    path('<uuid:proyecto_id>/protecciones/crear/',
         views.ObraProteccionCreateView.as_view(), name='protecciones_crear'),
    path('<uuid:proyecto_id>/protecciones/<uuid:pk>/editar/',
         views.ObraProteccionUpdateView.as_view(), name='protecciones_editar'),

    # Pruebas técnicas (#60)
    path('<uuid:proyecto_id>/pruebas/',
         views.PruebaTecnicaListView.as_view(), name='pruebas_lista'),
    path('<uuid:proyecto_id>/pruebas/crear/',
         views.PruebaTecnicaCreateView.as_view(), name='pruebas_crear'),
    path('<uuid:proyecto_id>/pruebas/<uuid:pk>/editar/',
         views.PruebaTecnicaUpdateView.as_view(), name='pruebas_editar'),

    # Kits de cerramiento (#65)
    path('<uuid:proyecto_id>/kits/',
         views.KitCerramientoListView.as_view(), name='kits_lista'),
    path('<uuid:proyecto_id>/kits/crear/',
         views.KitCerramientoCreateView.as_view(), name='kits_crear'),
    path('<uuid:proyecto_id>/kits/<uuid:pk>/editar/',
         views.KitCerramientoUpdateView.as_view(), name='kits_editar'),

    # Cronograma (#68)
    path('<uuid:proyecto_id>/cronograma/',
         views.CronogramaView.as_view(), name='cronograma'),

    # Dashboards (#61 #70)
    path('<uuid:proyecto_id>/dashboard-avance/',
         views.DashboardAvanceView.as_view(), name='dashboard_avance'),
    path('<uuid:proyecto_id>/dashboard-financiero/',
         views.DashboardFinancieroView.as_view(), name='dashboard_financiero'),

    # Financiero PDEO (#69)
    path('<uuid:proyecto_id>/financiero/',
         views.FinancieroGridView.as_view(), name='financiero_grid'),
    path('<uuid:proyecto_id>/financiero/periodo/crear/',
         views.PeriodoFinancieroCreateView.as_view(), name='periodo_crear'),
    path('<uuid:proyecto_id>/financiero/movimiento/save/',
         views.MovimientoFinancieroSaveView.as_view(), name='movimiento_save'),

    # Cilindros pendientes (#55)
    path('<uuid:proyecto_id>/cilindros/',
         views.CilindrosPendientesView.as_view(), name='cilindros_pendientes'),

    # Obra Civil (#53 #54 #55) — UI por torre con 4 patas × 6 bloques
    path('<uuid:proyecto_id>/obra-civil/',
         views.ObraCivilMatrizView.as_view(), name='obra_civil_lista'),
    # AJAX endpoints para matriz #74
    path('<uuid:proyecto_id>/obra-civil/pesos/',
         views.ObraCivilPesosUpdateView.as_view(), name='obra_civil_pesos_update'),
    path('<uuid:proyecto_id>/obra-civil/torres/<uuid:torre_id>/avance/',
         views.ObraCivilAvanceUpdateView.as_view(), name='obra_civil_avance_update'),
    path('<uuid:proyecto_id>/obra-civil/torres/<uuid:torre_id>/fechas/',
         views.ObraCivilFechasUpdateView.as_view(), name='obra_civil_fechas_update'),
    path('<uuid:proyecto_id>/obra-civil/torres/<uuid:torre_id>/aplica/',
         views.ObraCivilAplicaUpdateView.as_view(), name='obra_civil_aplica_update'),
    # Detalle pata×actividad (vista legacy granular)
    path('<uuid:proyecto_id>/obra-civil/<uuid:torre_id>/patas/',
         views.ObraCivilTorreView.as_view(), name='obra_civil_torre_patas'),
    path('<uuid:proyecto_id>/obra-civil-legacy/',
         views.ObraCivilListView.as_view(), name='obra_civil_lista_legacy'),
    path('<uuid:proyecto_id>/obra-civil/<uuid:torre_id>/',
         views.ObraCivilTorreView.as_view(), name='obra_civil_torre'),

    # Montaje + SPT + Pintura (#56 #57) — UI por torre
    path('<uuid:proyecto_id>/montaje/',
         views.MontajeMatrizView.as_view(), name='montaje_lista'),
    # AJAX endpoints CANT MONTAJE #76
    path('<uuid:proyecto_id>/montaje/pesos/',
         views.MontajePesosUpdateView.as_view(), name='montaje_pesos_update'),
    path('<uuid:proyecto_id>/montaje/torres/<uuid:torre_id>/avance/',
         views.MontajeAvanceUpdateView.as_view(), name='montaje_avance_update'),
    # Drill-down fase-level (vista legacy)
    path('<uuid:proyecto_id>/montaje/<uuid:torre_id>/fase/',
         views.MontajeTorreView.as_view(), name='montaje_torre_fase'),
    path('<uuid:proyecto_id>/montaje-legacy/',
         views.MontajeListView.as_view(), name='montaje_lista_legacy'),
    path('<uuid:proyecto_id>/montaje/<uuid:torre_id>/',
         views.MontajeTorreView.as_view(), name='montaje_torre'),

    # Tendido (#58) — UI por torre con 2 circuitos × 3 fases + OPGW + guarda
    path('<uuid:proyecto_id>/tendido/',
         views.TendidoMatrizView.as_view(), name='tendido_lista'),
    # CANT TENDIDO AJAX #79
    path('<uuid:proyecto_id>/tendido/pesos/',
         views.TendidoPesosUpdateView.as_view(), name='tendido_pesos_update'),
    path('<uuid:proyecto_id>/tendido/torres/<uuid:torre_id>/toggle/',
         views.TendidoToggleView.as_view(), name='tendido_toggle'),
    path('<uuid:proyecto_id>/tendido/torres/<uuid:torre_id>/realizo/',
         views.TendidoRealizoUpdateView.as_view(), name='tendido_realizo_update'),
    path('<uuid:proyecto_id>/tendido-legacy/',
         views.TendidoListView.as_view(), name='tendido_lista_legacy'),

    # Hochiminh Fase 1 (#171) — matriz Marcación/Replanteo por torre
    path('<uuid:proyecto_id>/hochiminh/',
         views.HochiminhMatrizView.as_view(), name='hochiminh_lista'),
    path('<uuid:proyecto_id>/hochiminh/torres/<uuid:torre_id>/toggle/',
         views.HochiminhToggleView.as_view(), name='hochiminh_toggle'),
    path('<uuid:proyecto_id>/tendido/<uuid:torre_id>/fase/',
         views.TendidoTorreView.as_view(), name='tendido_torre_fase'),
    path('<uuid:proyecto_id>/tendido/<uuid:torre_id>/',
         views.TendidoTorreView.as_view(), name='tendido_torre'),

    # Iteración 2 — deuda técnica
    path('<uuid:proyecto_id>/financiero/categoria/<uuid:categoria_id>/',
         views.CategoriaDrilldownView.as_view(), name='categoria_drilldown'),
    path('<uuid:proyecto_id>/kits/dashboard/',
         views.DashboardKitsView.as_view(), name='kits_dashboard'),

    # Sidebar #73 — placeholders para módulos pendientes (se reemplazan en Fases 2 y 3)
    # Dashboards Curva S (#75 #77)
    path('<uuid:proyecto_id>/dashboard-obra-civil/',
         views.DashboardObraCivilView.as_view(), name='dashboard_obra_civil'),
    # #141 — datos JSON de las 3 gráficas del Dashboard de Obra Civil
    path('<uuid:proyecto_id>/dashboard-obra-civil/datos-graficas/',
         views.DashboardGraficasDataView.as_view(), name='dashboard_graficas_data'),
    path('<uuid:proyecto_id>/dashboard-montaje/',
         views.DashboardMontajeView.as_view(), name='dashboard_montaje'),
    path('<uuid:proyecto_id>/dashboard/semana/',
         views.DashboardSemanaUpsertView.as_view(), name='dashboard_semana_upsert'),
    path('<uuid:proyecto_id>/dashboard/semana/<uuid:pk>/delete/',
         views.DashboardSemanaDeleteView.as_view(), name='dashboard_semana_delete'),
    path('<uuid:proyecto_id>/dashboard/chart/',
         views.DashboardChartDataView.as_view(), name='dashboard_chart_data'),
    # SPT y Pintura — captura por torre #78
    path('<uuid:proyecto_id>/spt-pintura/',
         views.SPTPinturaIndexView.as_view(), name='spt_pintura'),
    path('<uuid:proyecto_id>/spt-pintura/<uuid:torre_id>/',
         views.SPTPinturaTorreView.as_view(), name='spt_pintura_torre'),
    path('<uuid:proyecto_id>/spt-pintura/<uuid:torre_id>/update/',
         views.SPTPinturaTorreUpdateView.as_view(), name='spt_pintura_update'),
    # Obras de Protección (Trinchos y Cunetas) (#80, #149)
    # #149: el PATH se renombró trinchos-cunetas/ → obras-proteccion/ (lo que el
    # cliente espera ver en la URL). Los `name=` se MANTIENEN intactos
    # (trinchos_cunetas*) para no romper ningún {% url %} / reverse() existente.
    path('<uuid:proyecto_id>/obras-proteccion/',
         views.TrinchosCunetasListView.as_view(), name='trinchos_cunetas'),
    path('<uuid:proyecto_id>/obras-proteccion/upsert/',
         views.TrinchosCunetasUpsertView.as_view(), name='trinchos_cunetas_upsert'),
    path('<uuid:proyecto_id>/obras-proteccion/<uuid:pk>/delete/',
         views.TrinchosCunetasDeleteView.as_view(), name='trinchos_cunetas_delete'),
    # Resumen de Materiales (#154) — consolidado de solo lectura (total + por torre).
    # Slug DEBE ser 'resumen-materiales/' (el sidebar arma catUrl('resumen-materiales')).
    path('<uuid:proyecto_id>/resumen-materiales/',
         views.ResumenMaterialesView.as_view(), name='resumen_materiales'),
    # #149: redirects 301 de los paths viejos /trinchos-cunetas/* → nuevos, para
    # no romper backlinks/bookmarks que el cliente tenga guardados. RedirectView
    # con pattern_name reenvía los kwargs capturados (proyecto_id, pk).
    path('<uuid:proyecto_id>/trinchos-cunetas/',
         RedirectView.as_view(pattern_name='construccion:trinchos_cunetas',
                              permanent=True)),
    path('<uuid:proyecto_id>/trinchos-cunetas/upsert/',
         RedirectView.as_view(pattern_name='construccion:trinchos_cunetas_upsert',
                              permanent=True)),
    path('<uuid:proyecto_id>/trinchos-cunetas/<uuid:pk>/delete/',
         RedirectView.as_view(pattern_name='construccion:trinchos_cunetas_delete',
                              permanent=True)),
]

# === /modulo indicadores_construccion_sub_run_a — split de archivo magnet ===
# F2 scaffolding eliminó los placeholders 'actividades-finales' e
# 'indicadores-financieros' (que apuntaban a ModuloPlaceholderView) y
# delegó a urls_b1/b2/b3. B1 re-define 'actividades_finales',
# B3 re-define 'indicadores_financieros' (mismo slug, view nueva),
# B2 agrega los CRUD bajo /indicadores/.
from . import (
    urls_b1_actividades_finales,
    urls_b2_indicadores,
    urls_b3_dashboard_indicadores,
)

urlpatterns += urls_b1_actividades_finales.urlpatterns
urlpatterns += urls_b2_indicadores.urlpatterns
urlpatterns += urls_b3_dashboard_indicadores.urlpatterns

# === /modulo excel_paridad_oc_montaje — split de archivo magnet ===
# F2 scaffolding: B2b (OC detalle URLs) y B3b (Montaje detalle URLs) en F3.
from . import urls_b3_oc_detalle, urls_b3_mont_detalle  # noqa: E402

urlpatterns += urls_b3_oc_detalle.urlpatterns
urlpatterns += urls_b3_mont_detalle.urlpatterns

# === Complemento financiero #103 — TransaccionesList/Upload/Reportes + PyG drill-down ===
from . import urls_pdeo_complement  # noqa: E402
urlpatterns += urls_pdeo_complement.urlpatterns

# === /modulo financiero_construccion_runB — rutas financieras ===
# F2 scaffolding: B4 (#123) llena urls_fin con las 6 rutas /financiero/<subruta>/.
from . import urls_fin  # noqa: E402
urlpatterns += urls_fin.urlpatterns

# === /modulo dashboards (#139) — dashboards de avance real por fase ===
# F2 scaffolding (S2): partición física de views.py/urls.py. B1 cablea la
# Curva S real de Obra Civil; B2–B5 agregan Montaje/Tendido/Vista-torres/General.
from .urls_dashboards import urlpatterns as dashboards_urls  # noqa: E402
from .urls_dashboards_b2_montaje import urlpatterns as dashboards_b2_urls  # noqa: E402
from .urls_dashboards_b3_tendido import urlpatterns as dashboards_b3_urls  # noqa: E402
from .urls_dashboards_b4_torres import urlpatterns as dashboards_b4_urls  # noqa: E402
from .urls_dashboards_b5_general import urlpatterns as dashboards_b5_urls  # noqa: E402
urlpatterns += dashboards_urls
urlpatterns += dashboards_b2_urls + dashboards_b3_urls + dashboards_b4_urls + dashboards_b5_urls

# === F4 wiring (#139): el menú/selector abre los dashboards REALES ===
# El sidebar construye URLs por path literal (catUrl(slug) -> /construccion/<id>/
# <slug>/), NO por reverse(). Por eso el override de *name* que hicieron B1/B2 no
# basta para que el menú abra la vista real: el request entrante a la ruta legacy
# (matching first-wins, declarada arriba) seguía cayendo en la vista del semanal
# vacío. Aquí re-apuntamos las rutas legacy de menú a las vistas reales del
# backbone para que TODOS los dashboards que el usuario abre desde el menú
# muestren el avance real, consistente con lo que B1 hizo para Obra Civil.
from django.urls import path as _df_path  # noqa: E402, I001
from .views_dashboards import DashboardObraCivilRealView as _DObraCivilReal  # noqa: E402, I001
from .views_dashboards_b2_montaje import DashboardMontajeRealView as _DMontajeReal  # noqa: E402, I001

# Reemplazar in-place la ruta legacy 'dashboard-obra-civil/' y 'dashboard-montaje/'
# por las vistas reales (mismo name + mismo path → el menú abre el dashboard real).
_DASHBOARD_MENU_OVERRIDES = {
    'dashboard_obra_civil': _DObraCivilReal,
    'dashboard_montaje': _DMontajeReal,
}
for _i, _p in enumerate(urlpatterns):
    _name = getattr(_p, 'name', None)
    if _name in _DASHBOARD_MENU_OVERRIDES:
        urlpatterns[_i] = _df_path(
            str(_p.pattern),
            _DASHBOARD_MENU_OVERRIDES[_name].as_view(),
            name=_name,
        )

# === /modulo programacion_cuadrillas (#155) — subsección admin de Construcción ===
# F2 scaffolding (S1): bloque importer add-only. B1 crea `urls_pc.py` con los 6
# paths bajo el namespace `construccion:`. Import protegido para que el repo siga
# importable en la rama base ANTES de que B1 escriba urls_pc.py.
try:
    from . import urls_pc  # noqa: E402
    urlpatterns += urls_pc.urlpatterns
except Exception:
    pass
