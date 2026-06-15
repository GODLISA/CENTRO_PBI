"""
Motor de cálculo de presupuestos.

Separa la lógica de negocio de las vistas: aquí se resuelven los parámetros
vigentes (UF, valor km, IVA) y se calculan las líneas y totales de un
presupuesto, guardando snapshots de todos los valores usados.
"""
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    DetallePresupuesto,
    ItemMatriz,
    Parametro,
    Presupuesto,
)

CERO = Decimal('0')


def valor_parametro(codigo, fecha=None, zona=None):
    """
    Retorna (Decimal valor, ValorParametro registro) del parámetro vigente.
    Lanza ValidationError con mensaje claro si no hay valor definido.
    """
    try:
        parametro = Parametro.objects.get(codigo=codigo)
    except Parametro.DoesNotExist:
        raise ValidationError(
            f'No existe el parámetro "{codigo}". Créelo en el admin (Presupuestos → Parámetros).'
        )

    registro = parametro.valor_vigente(fecha=fecha, zona=zona)
    if registro is None:
        raise ValidationError(
            f'El parámetro "{parametro.nombre}" no tiene valor vigente. '
            f'Agregue un valor en el admin (Presupuestos → Valores de parámetros).'
        )
    return registro.valor, registro


def _a_clp(monto):
    """Redondea a peso entero (CLP no usa decimales)."""
    return monto.quantize(Decimal('1'), rounding=ROUND_HALF_UP)


@transaction.atomic
def calcular_presupuesto(presupuesto, lineas):
    """
    Calcula y persiste el detalle y los totales de un presupuesto.

    `lineas` es una lista de dicts:
        {'item_id': int|None, 'concepto': str (solo ítems manuales),
         'cantidad': Decimal, 'precio_unitario': Decimal (solo manuales),
         'moneda': 'CLP'|'UF' (solo manuales)}

    Para líneas con item_id se toma concepto/precio/moneda desde la matriz
    (snapshot). Reemplaza el detalle existente y recalcula totales.
    """
    fecha = presupuesto.fecha_emision or timezone.localdate()

    # --- Parámetros vigentes (snapshot) ---
    necesita_uf = any(
        (l.get('moneda') == ItemMatriz.MONEDA_UF) or l.get('item_id')
        for l in lineas
    )
    valor_uf = None
    if necesita_uf:
        # Se resuelve siempre que haya ítems de matriz, porque pueden venir en UF
        valor_uf, _ = valor_parametro(Parametro.COD_UF, fecha=fecha)

    valor_km = None
    costo_traslado = CERO
    if presupuesto.distancia_km and presupuesto.distancia_km > 0:
        valor_km, _ = valor_parametro(
            Parametro.COD_VALOR_KM, fecha=fecha, zona=presupuesto.zona
        )
        costo_traslado = _a_clp(Decimal(presupuesto.distancia_km) * valor_km)

    porcentaje_iva, _ = valor_parametro(Parametro.COD_IVA, fecha=fecha)

    # USD es referencial (aparece en el encabezado del PDF); si no está cargado
    # no se interrumpe el cálculo.
    valor_usd = None
    try:
        valor_usd, _ = valor_parametro(Parametro.COD_USD, fecha=fecha)
    except ValidationError:
        valor_usd = None

    # --- Construcción del detalle ---
    presupuesto.detalles.all().delete()
    subtotal = CERO
    detalles = []

    for orden, linea in enumerate(lineas):
        cantidad = Decimal(str(linea.get('cantidad', '1')))
        if cantidad <= 0:
            continue

        item = None
        if linea.get('item_id'):
            try:
                item = ItemMatriz.objects.get(
                    pk=linea['item_id'], area=presupuesto.area, activo=True
                )
            except ItemMatriz.DoesNotExist:
                raise ValidationError(
                    f'El ítem id={linea["item_id"]} no existe o no pertenece '
                    f'al área "{presupuesto.area}".'
                )
            concepto = item.concepto
            unidad = item.unidad
            moneda = item.moneda
            precio = item.precio_unitario
        else:
            concepto = (linea.get('concepto') or '').strip()
            if not concepto:
                raise ValidationError('Las líneas manuales requieren un concepto.')
            unidad = linea.get('unidad') or 'unidad'
            moneda = linea.get('moneda') or ItemMatriz.MONEDA_CLP
            precio = Decimal(str(linea.get('precio_unitario', '0')))

        if moneda == ItemMatriz.MONEDA_UF:
            if valor_uf is None:
                valor_uf, _ = valor_parametro(Parametro.COD_UF, fecha=fecha)
            precio_clp = _a_clp(precio * valor_uf)
        else:
            precio_clp = _a_clp(precio)

        total_linea = _a_clp(precio_clp * cantidad)
        subtotal += total_linea

        detalles.append(DetallePresupuesto(
            presupuesto=presupuesto,
            item=item,
            concepto=concepto,
            unidad=unidad,
            cantidad=cantidad,
            moneda=moneda,
            precio_unitario=precio,
            precio_unitario_clp=precio_clp,
            total_clp=total_linea,
            orden=orden,
        ))

    if not detalles:
        raise ValidationError('El presupuesto debe tener al menos una línea con cantidad mayor a 0.')

    DetallePresupuesto.objects.bulk_create(detalles)

    # --- Totales ---
    subtotal += costo_traslado
    monto_iva = _a_clp(subtotal * porcentaje_iva / Decimal('100'))

    presupuesto.valor_uf = valor_uf
    presupuesto.valor_usd = valor_usd
    presupuesto.valor_km = valor_km
    presupuesto.porcentaje_iva = porcentaje_iva
    presupuesto.costo_traslado = costo_traslado
    presupuesto.subtotal = subtotal
    presupuesto.monto_iva = monto_iva
    presupuesto.total = subtotal + monto_iva
    presupuesto.save()
    return presupuesto
