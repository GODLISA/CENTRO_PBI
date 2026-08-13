"""
URL configuration for sig_intranet project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.views.static import serve
import os

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('panel.urls')),
    path('presupuestos/', include('presupuestos.urls')),
    path('inventarios/', include('inventarios.urls')),
]

# Servir archivos estáticos y media con DEBUG=False (válido para intranet)
# En producción con internet se usaría nginx/apache, pero en intranet esto es suficiente
if not settings.DEBUG:
    urlpatterns += [
        path('static/<path:path>', serve, {
            'document_root': settings.STATIC_ROOT,
        }),
        path('media/<path:path>', serve, {
            'document_root': settings.MEDIA_ROOT,
        }),
    ]
