"""
Generación del PDF del presupuesto con ReportLab.

El formato replica estrictamente el presupuesto PELP de referencia
("PRESUPUESTO N°1888"): membrete PELP, caja R.U.T./PRESUPUESTO/N°,
referencia USD/UF, datos del cliente en grilla, barra verde de
"ALCANCES / OBSERVACIONES", tabla de detalle con encabezado gris,
totales (TOTAL NETO / IVA 19% / TOTAL A PAGAR) en verde claro y el pie
de condiciones. Fuente Arial Narrow (Helvetica como sustituto), 10 pt.
"""
import io
import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from django.conf import settings

from .models import ConfiguracionEmpresa

# Paleta exacta del Excel de referencia (tema Office: accent3 = verde 9BBB59)
VERDE_TITULO = colors.HexColor('#D7E4BD')   # accent3 tint 0.6  (barra observaciones)
VERDE_TOTAL = colors.HexColor('#EBF1DE')    # accent3 tint 0.8  (filas de total)
GRIS_HEADER = colors.HexColor('#D9D9D9')    # blanco tint -0.15 (encabezado tabla)
GRIS_TEXTO = colors.HexColor('#808080')     # blanco tint -0.5  (texto "PRESUPUESTO")
NEGRO = colors.black
BORDE = colors.HexColor('#000000')

DIR_LOGO = os.path.join(
    settings.BASE_DIR, 'presupuestos', 'static', 'presupuestos', 'img'
)
LOGO_MEMBRETE = os.path.join(DIR_LOGO, 'pelp_membrete.png')
LOGO_ARROW = os.path.join(DIR_LOGO, 'pelp_logo.png')


def _imagen_ajustada(ruta, ancho_max, alto_max):
    """
    Image de ReportLab escalado para caber dentro de (ancho_max, alto_max)
    conservando la proporción. Usado para el membrete PELP por defecto, que
    debe ocupar el ancho del encabezado.
    """
    img = Image(ruta)
    escala = min(ancho_max / img.imageWidth, alto_max / img.imageHeight)
    img.drawWidth = img.imageWidth * escala
    img.drawHeight = img.imageHeight * escala
    img.hAlign = 'LEFT'
    return img


def _imagen_por_alto(ruta, alto, ancho_max):
    """
    Image de ReportLab renderizado a una altura fija `alto` (el ancho se
    ajusta solo conservando la proporción), sin superar `ancho_max`. Pensado
    para el logo que sube el usuario: su tamaño no depende de la DPI ni de
    los píxeles del archivo, solo de la altura configurada en el admin.
    """
    img = Image(ruta)
    proporcion = img.imageWidth / img.imageHeight
    alto_final = alto
    ancho_final = alto_final * proporcion
    if ancho_final > ancho_max:  # logo muy ancho: limitar por ancho
        ancho_final = ancho_max
        alto_final = ancho_final / proporcion
    img.drawWidth = ancho_final
    img.drawHeight = alto_final
    img.hAlign = 'LEFT'
    return img


def _clp(valor):
    """Formatea 1234567 -> $1.234.567"""
    if valor is None:
        return '-'
    return '$' + f'{int(round(valor)):,}'.replace(',', '.')


def _num(valor, dec=2):
    """Formato numérico con separador de miles chileno (para UF/USD)."""
    if valor is None:
        return '-'
    return f'{float(valor):,.{dec}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def generar_pdf_presupuesto(presupuesto):
    """Retorna los bytes del PDF de un presupuesto calculado."""
    empresa = ConfiguracionEmpresa.obtener()
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=14 * mm,
        title=f'Presupuesto N°{presupuesto.numero}',
    )

    base = getSampleStyleSheet()['Normal']
    st = ParagraphStyle('st', parent=base, fontName='Helvetica', fontSize=8, leading=10)
    st_b = ParagraphStyle('st_b', parent=st, fontName='Helvetica-Bold')
    st_c = ParagraphStyle('st_c', parent=st, alignment=TA_CENTER)
    st_cb = ParagraphStyle('st_cb', parent=st_b, alignment=TA_CENTER)
    st_r = ParagraphStyle('st_r', parent=st, alignment=TA_RIGHT)
    pres_titulo = ParagraphStyle(
        'pres_titulo', parent=st_b, alignment=TA_CENTER, fontSize=11, textColor=GRIS_TEXTO
    )

    ancho = doc.width  # ancho útil
    elementos = []

    # ============================================================
    # 1. ENCABEZADO: membrete (izq) + caja RUT/PRESUPUESTO/N° (der)
    # ============================================================
    # Logo subido desde el admin → altura configurable (logo_alto_mm).
    # Sin logo subido → membrete PELP por defecto a su tamaño habitual.
    logo_subido = empresa.logo and os.path.exists(empresa.logo.path)

    # Bloque de datos de la empresa (texto): nombre + giro + dirección + tel + email
    def _datos_empresa():
        st_nombre = ParagraphStyle('mb', parent=st_b, fontSize=12, leading=14)
        partes = [Paragraph(empresa.nombre, st_nombre)]
        for txt in (empresa.giro, empresa.direccion, empresa.telefono, empresa.email):
            if txt:
                partes.append(Paragraph(txt, st))
        return partes

    if empresa.mostrar_logo and logo_subido:
        # Logo subido + datos de la empresa como texto debajo
        logo = _imagen_por_alto(
            empresa.logo.path,
            alto=(empresa.logo_alto_mm or 22) * mm,
            ancho_max=96 * mm,
        )
        membrete = [logo, Spacer(1, 2 * mm)] + _datos_empresa()
    elif empresa.mostrar_logo and os.path.exists(LOGO_MEMBRETE):
        # Membrete PELP por defecto (ya trae los datos incrustados en la imagen)
        membrete = _imagen_ajustada(LOGO_MEMBRETE, ancho_max=96 * mm, alto_max=41 * mm)
    else:
        # Sin logo: solo datos de la empresa como texto
        membrete = _datos_empresa()

    caja_rut = Table(
        [
            [Paragraph(f'R.U.T. :   {empresa.rut}', st_cb)],
            [Paragraph('PRESUPUESTO', pres_titulo)],
            [Paragraph(f'N°&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;'
                       f'<b>{presupuesto.numero}</b>', st_cb)],
        ],
        colWidths=[58 * mm],
        rowHeights=[8 * mm, 9 * mm, 8 * mm],
    )
    caja_rut.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, BORDE),
        ('LINEBELOW', (0, 0), (0, 0), 0.75, BORDE),
        ('LINEBELOW', (0, 1), (0, 1), 0.75, BORDE),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))

    encabezado = Table(
        [[membrete, caja_rut]],
        colWidths=[ancho - 58 * mm, 58 * mm],
    )
    encabezado.setStyle(TableStyle([
        ('VALIGN', (0, 0), (0, 0), 'TOP'),
        ('VALIGN', (1, 0), (1, 0), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    elementos.append(encabezado)
    elementos.append(Spacer(1, 3 * mm))

    # ============================================================
    # 2. Fecha + referencia (USD) / (UF)
    # ============================================================
    ref = Table(
        [
            ['', Paragraph('Fecha:', st_b), Paragraph(presupuesto.fecha_emision.strftime('%d-%m-%Y'), st_r)],
            ['', Paragraph('(USD)', st_b), Paragraph(_num(presupuesto.valor_usd), st_r)],
            ['', Paragraph('(UF)', st_b), Paragraph(_num(presupuesto.valor_uf), st_r)],
        ],
        colWidths=[ancho - 60 * mm, 25 * mm, 35 * mm],
    )
    ref.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
    ]))
    elementos.append(ref)
    elementos.append(Spacer(1, 2 * mm))

    # ============================================================
    # 3. Datos del cliente (grilla con bordes)
    # ============================================================
    filas_cli = [
        [Paragraph('RAZÓN SOC.', st_b), Paragraph(presupuesto.cliente_nombre, st)],
        [Paragraph('DIRECCIÓN', st_b), Paragraph(presupuesto.cliente_direccion or '', st)],
        [Paragraph('CONTACTO', st_b), Paragraph(presupuesto.cliente_contacto or '', st)],
        [Paragraph('RUT', st_b), Paragraph(presupuesto.cliente_rut or '', st)],
        [Paragraph('EMAIL', st_b), Paragraph(presupuesto.cliente_email or '', st)],
    ]
    tabla_cli = Table(filas_cli, colWidths=[34 * mm, ancho - 34 * mm])
    tabla_cli.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.75, BORDE),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
    ]))
    elementos.append(tabla_cli)
    elementos.append(Spacer(1, 3 * mm))

    # ============================================================
    # 4. ALCANCES / OBSERVACIONES + barra verde de título
    # ============================================================
    elementos.append(Paragraph('ALCANCES / OBSERVACIONES:', st_b))
    elementos.append(Spacer(1, 1 * mm))

    titulo_trabajo = presupuesto.titulo_trabajo or presupuesto.area.nombre.upper()
    barra = Table([[Paragraph(titulo_trabajo, st_b)]], colWidths=[ancho])
    barra.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), VERDE_TITULO),
        ('BOX', (0, 0), (-1, -1), 0.75, BORDE),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
    ]))
    elementos.append(barra)
    elementos.append(Spacer(1, 1.5 * mm))

    if presupuesto.notas:
        elementos.append(Paragraph(presupuesto.notas.replace('\n', '<br/>'), st))
        elementos.append(Spacer(1, 1 * mm))
    if empresa.texto_reenvio:
        elementos.append(Paragraph(empresa.texto_reenvio.replace('\n', '<br/>'), st))
    if empresa.nota_aprobacion:
        elementos.append(Spacer(1, 1 * mm))
        elementos.append(Paragraph(f'<b>{empresa.nota_aprobacion}</b>', st))
    elementos.append(Spacer(1, 3 * mm))

    # ============================================================
    # 5. Tabla de detalle (encabezado gris) + totales (verde claro)
    # ============================================================
    filas = [[
        Paragraph('DETALLE', st_b),
        Paragraph('Valor Un.(*)', st_cb),
        Paragraph('Cantidad', st_cb),
        Paragraph('Subtotal(*)', st_cb),
    ]]
    for d in presupuesto.detalles.all():
        concepto = d.concepto
        if d.moneda == 'UF':
            concepto += f' ({_num(d.precio_unitario)} UF)'
        filas.append([
            Paragraph(concepto, st),
            Paragraph(_clp(d.precio_unitario_clp), st_r),
            Paragraph(_num(d.cantidad, 0) if d.cantidad == d.cantidad.to_integral()
                      else _num(d.cantidad), st_c),
            Paragraph(_clp(d.total_clp), st_r),
        ])
    if presupuesto.costo_traslado:
        etiqueta = f'TRASLADO ({_num(presupuesto.distancia_km, 0)} km'
        if presupuesto.comuna:
            etiqueta += f' - {presupuesto.comuna.nombre}'
        etiqueta += ')'
        filas.append([
            Paragraph(etiqueta, st),
            Paragraph(_clp(presupuesto.valor_km) + '/km', st_r),
            Paragraph(_num(presupuesto.distancia_km, 0), st_c),
            Paragraph(_clp(presupuesto.costo_traslado), st_r),
        ])

    n_detalle = len(filas)  # filas hasta aquí (incluye header)

    # Filas de totales
    filas.append([Paragraph('TOTAL NETO', st_b), '', '', Paragraph(_clp(presupuesto.subtotal), st_r)])
    filas.append([
        Paragraph(f'IVA {_num(presupuesto.porcentaje_iva, 0)}%', st_b), '', '',
        Paragraph(_clp(presupuesto.monto_iva), st_r),
    ])
    filas.append([Paragraph('TOTAL A PAGAR', st_b), '', '', Paragraph(_clp(presupuesto.total), st_r)])

    col_detalle = ancho - (28 * mm + 22 * mm + 30 * mm)
    tabla = Table(
        filas,
        colWidths=[col_detalle, 28 * mm, 22 * mm, 30 * mm],
        repeatRows=1,
    )
    fila_neto = n_detalle
    fila_total = n_detalle + 2
    tabla.setStyle(TableStyle([
        # Encabezado gris
        ('BACKGROUND', (0, 0), (-1, 0), GRIS_HEADER),
        # Grilla del detalle
        ('GRID', (0, 0), (-1, n_detalle - 1), 0.75, BORDE),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ('LEFTPADDING', (0, 0), (0, -1), 4),
        # Totales: fondo verde claro, etiqueta abarca 3 columnas
        ('BACKGROUND', (0, fila_neto), (-1, fila_total), VERDE_TOTAL),
        ('SPAN', (0, fila_neto), (2, fila_neto)),
        ('SPAN', (0, fila_neto + 1), (2, fila_neto + 1)),
        ('SPAN', (0, fila_total), (2, fila_total)),
        ('BOX', (0, fila_neto), (-1, fila_total), 0.75, BORDE),
        ('LINEBELOW', (0, fila_neto), (-1, fila_neto), 0.5, BORDE),
        ('LINEBELOW', (0, fila_neto + 1), (-1, fila_neto + 1), 0.5, BORDE),
        ('BOX', (3, fila_neto), (3, fila_total), 0.75, BORDE),
        ('FONTSIZE', (0, fila_total), (-1, fila_total), 9),
    ]))
    elementos.append(tabla)
    elementos.append(Spacer(1, 2 * mm))
    elementos.append(Paragraph('(*) VALORES NO INCLUYEN IVA', st))
    elementos.append(Spacer(1, 4 * mm))

    # ============================================================
    # 6. Validez + condiciones
    # ============================================================
    if empresa.validez_texto:
        elementos.append(Paragraph(f'<b>{empresa.validez_texto}</b>', st))
        elementos.append(Spacer(1, 2 * mm))
    for linea in empresa.condiciones.splitlines():
        if linea.strip():
            elementos.append(Paragraph(linea.strip(), st))

    # ============================================================
    # Pie de página (logo + número)
    # ============================================================
    def _pie(canvas, _doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(colors.grey)
        if empresa.pie_pagina:
            canvas.drawCentredString(letter[0] / 2, 8 * mm, empresa.pie_pagina)
        canvas.drawRightString(
            letter[0] - 14 * mm, 8 * mm,
            f'Presupuesto N°{presupuesto.numero} · Pág. {canvas.getPageNumber()}'
        )
        canvas.restoreState()

    doc.build(elementos, onFirstPage=_pie, onLaterPages=_pie)
    return buffer.getvalue()
