"""
Generación del PDF de stock por bodega con ReportLab.

Mismo formato del script original `stock_repuestos_pdf.py` (título con el
nombre de la bodega, subtítulo con totales y tabla COD_SAP / STOCK), pero
devolviendo bytes en memoria para servirlos por HTTP o comprimirlos.
"""
import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

AZUL_HEADER = colors.HexColor('#1F3864')
AZUL_FILA = colors.HexColor('#F2F5FA')
GRIS_BORDE = colors.HexColor('#B4B4B4')
GRIS_TEXTO = colors.HexColor('#555555')

AUTOR = 'Grupo Pelp - Control de Inventarios'


def _estilos():
    base = getSampleStyleSheet()
    titulo = ParagraphStyle(
        'TituloBodega',
        parent=base['Title'],
        fontName='Helvetica-Bold',
        fontSize=16,
        leading=20,
        alignment=TA_CENTER,
        spaceAfter=2 * mm,
    )
    sub = ParagraphStyle(
        'SubBodega',
        parent=base['Normal'],
        fontSize=8.5,
        textColor=GRIS_TEXTO,
        alignment=TA_CENTER,
    )
    return base, titulo, sub


def _documento(buffer, bodega):
    return SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=bodega,
        author=AUTOR,
    )


def generar_pdf_bodega(bodega, items):
    """PDF de una bodega: título + tabla COD_SAP / STOCK. Devuelve bytes."""
    base, estilo_titulo, estilo_sub = _estilos()

    datos = [['COD_SAP', 'STOCK']] + [[i['COD_SAP'], str(i['STOCK'])] for i in items]
    tabla = Table(datos, colWidths=[95 * mm, 35 * mm], repeatRows=1, hAlign='CENTER')
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), AZUL_HEADER),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9.5),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.4, GRIS_BORDE),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, AZUL_FILA]),
    ]))

    total = sum(i['STOCK'] for i in items)
    marca = datetime.now().strftime('%d-%m-%Y %H:%M')

    buffer = io.BytesIO()
    _documento(buffer, bodega).build([
        Paragraph(bodega, estilo_titulo),
        Paragraph(
            f'{len(items)} repuestos con stock · total {total} unidades · generado {marca}',
            estilo_sub,
        ),
        Spacer(1, 6 * mm),
        tabla,
    ])
    return buffer.getvalue()


def generar_pdf_bodega_vacia(bodega):
    """PDF de aviso para bodegas sin repuestos con stock. Devuelve bytes."""
    base, estilo_titulo, estilo_sub = _estilos()
    marca = datetime.now().strftime('%d-%m-%Y %H:%M')

    buffer = io.BytesIO()
    _documento(buffer, bodega).build([
        Paragraph(bodega, estilo_titulo),
        Paragraph(f'Generado {marca}', estilo_sub),
        Spacer(1, 6 * mm),
        Paragraph('Sin repuestos con stock mayor a 0.', base['Normal']),
    ])
    return buffer.getvalue()
