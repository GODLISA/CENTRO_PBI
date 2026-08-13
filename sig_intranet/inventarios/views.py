from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from . import services
from .services import InventarioError


def _incluir_vacias(request):
    """Lee el check "incluir bodegas sin stock" desde GET o POST."""
    origen = request.POST if request.method == 'POST' else request.GET
    return origen.get('incluir_vacias') in ('1', 'on', 'true')


@login_required
def stock_repuestos_view(request):
    """
    Pantalla del módulo: consulta StockRepuestos en SQL Server y muestra el
    resumen por bodega, con descarga del ZIP y del PDF individual.
    """
    incluir_vacias = _incluir_vacias(request)
    resumen = []
    error = None
    totales = {'bodegas': 0, 'repuestos': 0, 'unidades': 0}

    try:
        grupos = services.obtener_stock_por_bodega(incluir_vacias=incluir_vacias)
        resumen = services.resumen_bodegas(grupos)
        totales = {
            'bodegas': len(resumen),
            'repuestos': sum(r['repuestos'] for r in resumen),
            'unidades': sum(r['unidades'] for r in resumen),
        }
    except InventarioError as e:
        error = str(e)

    return render(request, 'inventarios/stock_repuestos.html', {
        'resumen': resumen,
        'totales': totales,
        'error': error,
        'incluir_vacias': incluir_vacias,
        'carpeta_salida': settings.INVENTARIOS_OUTPUT_DIR,
    })


@login_required
@require_POST
def descargar_zip_view(request):
    """
    Genera un PDF por bodega (también en OUTPUT_DIR) y devuelve todos
    comprimidos en un único archivo .zip.
    """
    incluir_vacias = _incluir_vacias(request)
    try:
        grupos = services.obtener_stock_por_bodega(incluir_vacias=incluir_vacias)
        if not grupos:
            messages.warning(
                request,
                'No hay repuestos con stock mayor a 0. No se generó ningún PDF.',
            )
            return redirect('inventarios_stock_repuestos')
        nombre, contenido = services.generar_zip(grupos)
    except InventarioError as e:
        messages.error(request, f'No se pudieron generar los PDF: {e}')
        return redirect('inventarios_stock_repuestos')

    response = HttpResponse(contenido, content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{nombre}"'
    return response


@login_required
def pdf_bodega_view(request):
    """PDF de una sola bodega, para revisar en pantalla (?bodega=NOMBRE)."""
    bodega = request.GET.get('bodega', '').strip()
    if not bodega:
        raise Http404('Falta el parámetro bodega.')

    try:
        grupos = services.obtener_stock_por_bodega(incluir_vacias=True)
    except InventarioError as e:
        messages.error(request, f'No se pudo generar el PDF: {e}')
        return redirect('inventarios_stock_repuestos')

    if bodega not in grupos:
        raise Http404(f'La bodega "{bodega}" no existe en StockRepuestos.')

    contenido = services.pdf_de_bodega(bodega, grupos[bodega])
    archivo = services.nombre_archivo_seguro(bodega)
    response = HttpResponse(contenido, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{archivo}.pdf"'
    return response
