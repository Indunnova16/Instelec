"""
Core URL patterns.
"""
from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.HomeView.as_view(), name='home'),
    path('health/', views.health_check, name='health'),
    path('api/health/', views.health_check, name='api_health'),
    path('api/health/simple/', views.health_check_simple, name='api_health_simple'),
]
