import urllib.request
import urllib.error
import json

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.views.decorators.http import require_POST
from django.conf import settings
from .models import Panel, PerfilUsuario


@login_required
def panel_view(request):
    """
    Vista principal protegida.
    Muestra solo los paneles asignados al usuario autenticado.
    Todo el filtrado ocurre en backend.
    """
    # Obtener o crear perfil del usuario
    perfil, _ = PerfilUsuario.objects.get_or_create(usuario=request.user)

    # Filtrar solo paneles activos asignados a este usuario
    paneles = perfil.paneles.filter(activo=True)

    return render(request, 'panel/panel.html', {
        'paneles': paneles,
    })


@login_required
def panel_detalle_view(request, panel_id):
    """
    Vista individual de un panel específico (pantalla completa).
    Valida que el usuario tenga acceso antes de renderizar.
    """
    panel = get_object_or_404(Panel, pk=panel_id, activo=True)

    # Validar que el usuario tenga acceso a este panel
    perfil, _ = PerfilUsuario.objects.get_or_create(usuario=request.user)
    if not perfil.paneles.filter(pk=panel.pk).exists():
        return HttpResponseForbidden(
            '<h1>403 - Acceso denegado</h1>'
            '<p>No tienes permiso para ver este panel.</p>'
        )

    return render(request, 'panel/panel_detalle.html', {
        'panel': panel,
    })


@login_required
@require_POST
def actualizar_paneles_view(request):
    """
    Proxy seguro: recibe petición del frontend y hace POST a la API externa.
    El token nunca se expone al navegador.
    """
    api_url = f"{settings.API_BASE_URL}/ejecutar-script"
    api_token = settings.API_BASE_TOKEN

    if not api_url or not api_token:
        return JsonResponse(
            {'success': False, 'message': 'API no configurada en el servidor.'},
            status=500
        )

    try:
        data = json.dumps({'ejecutar': 1}).encode('utf-8')
        req = urllib.request.Request(
            api_url,
            data=data,
            headers={
                'Authorization': f'Bearer {api_token}',
                'Content-Type': 'application/json',
            },
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode('utf-8'))
            return JsonResponse(body)

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8', errors='replace')
        return JsonResponse(
            {'success': False, 'message': f'Error de la API ({e.code}): {error_body}'},
            status=502
        )
    except urllib.error.URLError as e:
        return JsonResponse(
            {'success': False, 'message': f'No se pudo conectar a la API: {str(e.reason)}'},
            status=502
        )
    except Exception as e:
        return JsonResponse(
            {'success': False, 'message': f'Error inesperado: {str(e)}'},
            status=500
        )


@login_required
def estado_job_view(request, job_id):
    """
    Proxy seguro: consulta el estado de un job en la API externa.
    Polling desde el frontend cada 2 segundos.
    """
    api_url = f"{settings.API_BASE_URL}/estado-job/{job_id}"
    api_token = settings.API_BASE_TOKEN

    if not api_url or not api_token:
        return JsonResponse(
            {'success': False, 'message': 'API no configurada.'},
            status=500
        )

    try:
        req = urllib.request.Request(
            api_url,
            headers={
                'Authorization': f'Bearer {api_token}',
                'Content-Type': 'application/json',
            },
            method='GET'
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode('utf-8'))
            return JsonResponse(body)

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8', errors='replace')
        return JsonResponse(
            {'success': False, 'message': f'Error de la API ({e.code}): {error_body}'},
            status=502
        )
    except urllib.error.URLError as e:
        return JsonResponse(
            {'success': False, 'message': f'No se pudo conectar: {str(e.reason)}'},
            status=502
        )
    except Exception as e:
        return JsonResponse(
            {'success': False, 'message': f'Error inesperado: {str(e)}'},
            status=500
        )
