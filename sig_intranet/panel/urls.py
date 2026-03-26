from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Vista principal - lista de paneles del usuario (protegida)
    path('', views.panel_view, name='panel'),

    # Vista individual de un panel en pantalla completa (protegida + validada)
    path('panel/<int:panel_id>/', views.panel_detalle_view, name='panel_detalle'),

    # API interna - Actualizar paneles (proxy seguro al backend externo)
    path('api/actualizar-paneles/', views.actualizar_paneles_view, name='actualizar_paneles'),

    # API interna - Consultar estado de un job
    path('api/estado-job/<str:job_id>/', views.estado_job_view, name='estado_job'),

    # Login
    path('login/', auth_views.LoginView.as_view(
        template_name='panel/login.html'
    ), name='login'),

    # Logout
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
]
