import json
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import services
from .models import AreaServicio, Comuna, ItemMatriz, Parametro, Presupuesto, Zona
from .pdf import generar_pdf_presupuesto


@login_required
def lista_view(request):
    """Listado de presupuestos con filtro por estado y búsqueda simple."""
    presupuestos = Presupuesto.objects.select_related('area', 'zona', 'creado_por')

    estado = request.GET.get('estado', '')
    if estado:
        presupuestos = presupuestos.filter(estado=estado)

    q = request.GET.get('q', '').strip()
    if q:
        from django.db.models import Q
        presupuestos = presupuestos.filter(
            Q(numero__icontains=q) | Q(cliente_nombre__icontains=q) | Q(cliente_rut__icontains=q)
        )

    return render(request, 'presupuestos/lista.html', {
        'presupuestos': presupuestos[:200],
        'estados': Presupuesto.ESTADOS,
        'estado_actual': estado,
        'q': q,
    })


@login_required
def nuevo_view(request):
    """Formulario de creación. Las líneas llegan como JSON en un campo oculto."""
    areas = AreaServicio.objects.filter(activo=True)
    zonas = Zona.objects.filter(activo=True)

    # Aviso si la UF no tiene valor para hoy (se usaría el último valor cargado)
    aviso_uf = None
    try:
        uf = Parametro.objects.get(codigo=Parametro.COD_UF)
        registro = uf.valor_vigente()
        if registro is None:
            aviso_uf = 'No hay valor UF cargado. Cárguelo en el admin antes de usar ítems en UF.'
        elif registro.vigente_desde < timezone.localdate():
            aviso_uf = (
                f'El valor UF vigente es del {registro.vigente_desde.strftime("%d-%m-%Y")} '
                f'(${registro.valor}). Si necesita el valor de hoy, actualícelo en el admin '
                f'o ejecute el comando "actualizar_uf".'
            )
    except Parametro.DoesNotExist:
        aviso_uf = 'No existe el parámetro UF. Ejecute las migraciones o créelo en el admin.'

    if request.method == 'POST':
        try:
            presupuesto = _guardar_desde_post(request)
            messages.success(request, f'Presupuesto {presupuesto.numero} creado correctamente.')
            return redirect('presupuesto_detalle', presupuesto_id=presupuesto.pk)
        except (ValidationError, ValueError, InvalidOperation, KeyError) as e:
            mensaje = '; '.join(e.messages) if isinstance(e, ValidationError) else str(e)
            messages.error(request, f'No se pudo crear el presupuesto: {mensaje}')

    return render(request, 'presupuestos/form.html', {
        'areas': areas,
        'zonas': zonas,
        'aviso_uf': aviso_uf,
        'datos': request.POST if request.method == 'POST' else {},
    })


def _guardar_desde_post(request):
    """Crea el Presupuesto y delega el cálculo al motor de servicios."""
    post = request.POST

    area = get_object_or_404(AreaServicio, pk=post.get('area'), activo=True)
    zona = None
    if post.get('zona'):
        zona = get_object_or_404(Zona, pk=post['zona'], activo=True)

    comuna = None
    if post.get('comuna'):
        comuna = get_object_or_404(Comuna, pk=post['comuna'], zona=zona, activo=True)

    try:
        distancia = Decimal(post.get('distancia_km') or '0')
    except InvalidOperation:
        raise ValidationError('La distancia en km no es un número válido.')

    lineas = json.loads(post.get('lineas_json') or '[]')
    if not isinstance(lineas, list) or not lineas:
        raise ValidationError('Debe agregar al menos una línea al presupuesto.')

    cliente_nombre = (post.get('cliente_nombre') or '').strip()
    if not cliente_nombre:
        raise ValidationError('El nombre del cliente es obligatorio.')

    presupuesto = Presupuesto.objects.create(
        cliente_nombre=cliente_nombre,
        cliente_rut=(post.get('cliente_rut') or '').strip(),
        cliente_contacto=(post.get('cliente_contacto') or '').strip(),
        cliente_email=(post.get('cliente_email') or '').strip(),
        cliente_direccion=(post.get('cliente_direccion') or '').strip(),
        area=area,
        zona=zona,
        comuna=comuna,
        distancia_km=distancia,
        validez_dias=int(post.get('validez_dias') or 30),
        titulo_trabajo=(post.get('titulo_trabajo') or '').strip(),
        notas=(post.get('notas') or '').strip(),
        creado_por=request.user,
    )
    try:
        services.calcular_presupuesto(presupuesto, lineas)
    except ValidationError:
        presupuesto.delete()
        raise
    return presupuesto


@login_required
def detalle_view(request, presupuesto_id):
    presupuesto = get_object_or_404(
        Presupuesto.objects.select_related('area', 'zona', 'creado_por'),
        pk=presupuesto_id,
    )
    return render(request, 'presupuestos/detalle.html', {
        'presupuesto': presupuesto,
        'detalles': presupuesto.detalles.all(),
        'estados': Presupuesto.ESTADOS,
    })


@login_required
@require_POST
def cambiar_estado_view(request, presupuesto_id):
    presupuesto = get_object_or_404(Presupuesto, pk=presupuesto_id)
    estado = request.POST.get('estado')
    if estado not in dict(Presupuesto.ESTADOS):
        messages.error(request, 'Estado no válido.')
    else:
        presupuesto.estado = estado
        presupuesto.save(update_fields=['estado', 'updated_at'])
        messages.success(request, f'Presupuesto {presupuesto.numero} marcado como {presupuesto.get_estado_display()}.')
    return redirect('presupuesto_detalle', presupuesto_id=presupuesto.pk)


@login_required
def pdf_view(request, presupuesto_id):
    presupuesto = get_object_or_404(
        Presupuesto.objects.select_related('area', 'zona'),
        pk=presupuesto_id,
    )
    contenido = generar_pdf_presupuesto(presupuesto)
    response = HttpResponse(contenido, content_type='application/pdf')
    response['Content-Disposition'] = (
        f'inline; filename="Presupuesto_{presupuesto.numero}.pdf"'
    )
    return response


@login_required
def api_items_area_view(request, area_id):
    """
    Retorna los ítems activos de la matriz de un área + parámetros vigentes,
    para que el formulario calcule precios referenciales en vivo.
    """
    area = get_object_or_404(AreaServicio, pk=area_id, activo=True)
    items = [
        {
            'id': i.pk,
            'codigo': i.codigo,
            'concepto': i.concepto,
            'unidad': i.unidad,
            'moneda': i.moneda,
            'precio_unitario': str(i.precio_unitario),
        }
        for i in area.items.filter(activo=True)
    ]

    parametros = {}
    for codigo in (Parametro.COD_UF, Parametro.COD_IVA):
        try:
            valor, _ = services.valor_parametro(codigo)
            parametros[codigo] = str(valor)
        except ValidationError:
            parametros[codigo] = None

    # Valor km por zona (para mostrar el costo de traslado estimado)
    valores_km = {}
    try:
        param_km = Parametro.objects.get(codigo=Parametro.COD_VALOR_KM)
        global_km = param_km.valor_vigente()
        if global_km:
            valores_km['global'] = str(global_km.valor)
        for zona in Zona.objects.filter(activo=True):
            registro = param_km.valor_vigente(zona=zona)
            if registro:
                valores_km[str(zona.pk)] = str(registro.valor)
    except Parametro.DoesNotExist:
        pass

    return JsonResponse({'items': items, 'parametros': parametros, 'valores_km': valores_km})


@login_required
def api_comunas_zona_view(request, zona_id):
    """Comunas activas de una zona, con sus km (ida + regreso) para autocompletar."""
    zona = get_object_or_404(Zona, pk=zona_id, activo=True)
    comunas = [
        {
            'id': c.pk,
            'nombre': c.nombre,
            'region': c.region,
            'km': str(c.km_ida_regreso),
        }
        for c in zona.comunas.filter(activo=True)
    ]
    return JsonResponse({'comunas': comunas})
