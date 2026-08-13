from django.urls import path

from . import views

urlpatterns = [
    path('', views.stock_repuestos_view, name='inventarios_stock_repuestos'),
    path('stock-repuestos/zip/', views.descargar_zip_view, name='inventarios_stock_zip'),
    path('stock-repuestos/pdf/', views.pdf_bodega_view, name='inventarios_stock_pdf'),
]
