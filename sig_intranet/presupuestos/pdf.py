"""
Generación del PDF del presupuesto con ReportLab.

La presentación se alimenta de ConfiguracionEmpresa (editable en admin):
datos de la empresa, condiciones comerciales y pie de página.
"""
import io

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from .models import ConfiguracionEmpresa

AZUL = colors.HexColor('#1f3a5f')
GRIS_CLARO = colors.HexColor('#f2f4f7')
GRIS_BORDE = colors.HexColor('#d5dae2')


def _clp(valor):
    """Formatea 1234567 -> $1.234.567"""
    return '$' + f'{int(valor):,}'.replace(',', '.')


def generar_pdf_presupuesto(presupuesto):
    """Retorna los bytes del PDF de un presupuesto calculado."""
    empresa = ConfiguracionEmpresa.obtener()
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=f'Presupuesto {presupuesto.numero}',
    )

    styles = getSampleStyleSheet()
    normal = ParagraphStyle('normal', parent=styles['Normal'], fontSize=9, leading=12)
    pequeno = ParagraphStyle('pequeno', parent=normal, fontSize=8, textColor=colors.grey)
    titulo = ParagraphStyle(
        'titulo', parent=styles['Heading1'], fontSize=16, textColor=AZUL, spaceAfter=2
    )
    subtitulo = ParagraphStyle(
        'subtitulo', parent=styles['Heading2'], fontSize=11, textColor=AZUL,
        spaceBefore=10, spaceAfter=4
    )
    derecha = ParagraphStyle('derecha', parent=normal, alignment=TA_RIGHT)

    elementos = []

    # --- Encabezado: empresa + número de presupuesto ---
    datos_empresa = [Paragraph(f'<b>{empresa.nombre}</b>', normal)]
    for campo in (empresa.rut and f'RUT: {empresa.rut}', empresa.giro,
                  empresa.direccion, empresa.telefono, empresa.email):
        if campo:
            datos_empresa.append(Paragraph(campo, pequeno))

    caja_numero = Table(
        [
            [Paragraph('<b>PRESUPUESTO</b>', ParagraphStyle(
                'np', parent=normal, textColor=colors.white, fontSize=11))],
            [Paragraph(f'<b>N° {presupuesto.numero}</b>', derecha)],
            [Paragraph(f'Fecha: {presupuesto.fecha_emision.strftime("%d-%m-%Y")}', derecha)],
            [Paragraph(f'Validez: {presupuesto.validez_dias} días', derecha)],
        ],
        colWidths=[55 * mm],
    )
    caja_numero.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), AZUL),
        ('BOX', (0, 0), (-1, -1), 0.75, GRIS_BORDE),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))

    encabezado = Table(
        [[datos_empresa, caja_numero]],
        colWidths=[115 * mm, 60 * mm],
    )
    encabezado.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
    ]))
    elementos.append(encabezado)
    elementos.append(Spacer(1, 6 * mm))

    # --- Datos del cliente ---
    elementos.append(Paragraph('Datos del cliente', subtitulo))
    filas_cliente = [
        ['Cliente:', presupuesto.cliente_nombre, 'RUT:', presupuesto.cliente_rut or '-'],
        ['Contacto:', presupuesto.cliente_contacto or '-', 'Email:', presupuesto.cliente_email or '-'],
        ['Dirección:', presupuesto.cliente_direccion or '-', 'Área:', presupuesto.area.nombre],
    ]
    if presupuesto.zona:
        filas_cliente.append([
            'Zona:', presupuesto.zona.nombre,
            'Comuna:', presupuesto.comuna.nombre if presupuesto.comuna else '-',
        ])
    tabla_cliente = Table(filas_cliente, colWidths=[22 * mm, 76 * mm, 18 * mm, 59 * mm])
    tabla_cliente.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('BOX', (0, 0), (-1, -1), 0.75, GRIS_BORDE),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, GRIS_BORDE),
        ('BACKGROUND', (0, 0), (0, -1), GRIS_CLARO),
        ('BACKGROUND', (2, 0), (2, -1), GRIS_CLARO),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elementos.append(tabla_cliente)

    # --- Detalle ---
    elementos.append(Paragraph('Detalle del presupuesto', subtitulo))
    filas = [['Concepto', 'Unidad', 'Cant.', 'P. Unitario', 'Total']]
    for d in presupuesto.detalles.all():
        precio_txt = _clp(d.precio_unitario_clp)
        if d.moneda == 'UF':
            precio_txt += f'\n({d.precio_unitario.normalize()} UF)'
        filas.append([
            Paragraph(d.concepto, normal),
            d.unidad,
            f'{d.cantidad.normalize()}',
            precio_txt,
            _clp(d.total_clp),
        ])
    if presupuesto.costo_traslado:
        filas.append([
            Paragraph(
                f'Traslado ({presupuesto.distancia_km.normalize()} km'
                + (f', zona {presupuesto.zona.nombre}' if presupuesto.zona else '')
                + ')',
                normal,
            ),
            'km',
            f'{presupuesto.distancia_km.normalize()}',
            _clp(presupuesto.valor_km),
            _clp(presupuesto.costo_traslado),
        ])

    tabla_detalle = Table(filas, colWidths=[80 * mm, 20 * mm, 15 * mm, 30 * mm, 30 * mm], repeatRows=1)
    tabla_detalle.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), AZUL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, GRIS_CLARO]),
        ('BOX', (0, 0), (-1, -1), 0.75, GRIS_BORDE),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, GRIS_BORDE),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elementos.append(tabla_detalle)
    elementos.append(Spacer(1, 4 * mm))

    # --- Totales ---
    filas_totales = [
        ['Subtotal (neto)', _clp(presupuesto.subtotal)],
        [f'IVA ({presupuesto.porcentaje_iva.normalize()}%)', _clp(presupuesto.monto_iva)],
        ['TOTAL', _clp(presupuesto.total)],
    ]
    tabla_totales = Table(filas_totales, colWidths=[40 * mm, 35 * mm], hAlign='RIGHT')
    tabla_totales.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, -1), (-1, -1), AZUL),
        ('TEXTCOLOR', (0, -1), (-1, -1), colors.white),
        ('BOX', (0, 0), (-1, -1), 0.75, GRIS_BORDE),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, GRIS_BORDE),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elementos.append(tabla_totales)

    # --- Referencias de cálculo ---
    referencias = []
    if presupuesto.valor_uf:
        referencias.append(f'Valor UF aplicado: {_clp(presupuesto.valor_uf)}')
    if presupuesto.valor_km:
        referencias.append(f'Valor traslado: {_clp(presupuesto.valor_km)}/km')
    if referencias:
        elementos.append(Spacer(1, 2 * mm))
        elementos.append(Paragraph(' · '.join(referencias), pequeno))

    # --- Notas y condiciones ---
    if presupuesto.notas:
        elementos.append(Paragraph('Observaciones', subtitulo))
        elementos.append(Paragraph(presupuesto.notas.replace('\n', '<br/>'), normal))

    if empresa.condiciones:
        elementos.append(Paragraph('Condiciones comerciales', subtitulo))
        for linea in empresa.condiciones.splitlines():
            if linea.strip():
                elementos.append(Paragraph(f'• {linea.strip()}', pequeno))

    def _pie(canvas, _doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(colors.grey)
        texto = empresa.pie_pagina or f'{empresa.nombre} - Presupuesto {presupuesto.numero}'
        canvas.drawCentredString(letter[0] / 2, 10 * mm, texto)
        canvas.drawRightString(letter[0] - 18 * mm, 10 * mm, f'Página {canvas.getPageNumber()}')
        canvas.restoreState()

    doc.build(elementos, onFirstPage=_pie, onLaterPages=_pie)
    return buffer.getvalue()
