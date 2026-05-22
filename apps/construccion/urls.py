"""
URL patterns for the construccion (construction) app.
"""
from django.urls import path
from django.contrib.auth.decorators import login_required
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

    # Social Predial
    path('<uuid:proyecto_id>/social/', views.SocialPredialView.as_view(), name='social_predial'),

    # Ambiental
    path('<uuid:proyecto_id>/ambiental/', views.AmbientalView.as_view(), name='ambiental'),

    # Control de Lluvia
    path('<uuid:proyecto_id>/lluvia/', views.ControlLluviaView.as_view(), name='control_lluvia'),

    # Replanteo
    path('<uuid:proyecto_id>/replanteo/', views.ReplanteoView.as_view(), name='replanteo'),

    # SST
    path('<uuid:proyecto_id>/sst/', views.SSTView.as_view(), name='sst'),

    # Entrega
    path('<uuid:proyecto_id>/entrega/', views.EntregaView.as_view(), name='entrega'),

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
         views.ObraCivilListView.as_view(), name='obra_civil_lista'),
    path('<uuid:proyecto_id>/obra-civil/<uuid:torre_id>/',
         views.ObraCivilTorreView.as_view(), name='obra_civil_torre'),

    # Montaje + SPT + Pintura (#56 #57) — UI por torre
    path('<uuid:proyecto_id>/montaje/',
         views.MontajeListView.as_view(), name='montaje_lista'),
    path('<uuid:proyecto_id>/montaje/<uuid:torre_id>/',
         views.MontajeTorreView.as_view(), name='montaje_torre'),

    # Tendido (#58) — UI por torre con 2 circuitos × 3 fases + OPGW + guarda
    path('<uuid:proyecto_id>/tendido/',
         views.TendidoListView.as_view(), name='tendido_lista'),
    path('<uuid:proyecto_id>/tendido/<uuid:torre_id>/',
         views.TendidoTorreView.as_view(), name='tendido_torre'),

    # Iteración 2 — deuda técnica
    path('<uuid:proyecto_id>/financiero/categoria/<uuid:categoria_id>/',
         views.CategoriaDrilldownView.as_view(), name='categoria_drilldown'),
    path('<uuid:proyecto_id>/kits/dashboard/',
         views.DashboardKitsView.as_view(), name='kits_dashboard'),
]
