from django.urls import path

from . import views

urlpatterns = [
    path('', views.lista_view, name='presupuestos_lista'),
    path('nuevo/', views.nuevo_view, name='presupuesto_nuevo'),
    path('<int:presupuesto_id>/', views.detalle_view, name='presupuesto_detalle'),
    path('<int:presupuesto_id>/pdf/', views.pdf_view, name='presupuesto_pdf'),
    path('<int:presupuesto_id>/estado/', views.cambiar_estado_view, name='presupuesto_estado'),
    path('api/items-area/<int:area_id>/', views.api_items_area_view, name='presupuestos_api_items'),
    path('api/comunas-zona/<int:zona_id>/', views.api_comunas_zona_view, name='presupuestos_api_comunas'),
]
