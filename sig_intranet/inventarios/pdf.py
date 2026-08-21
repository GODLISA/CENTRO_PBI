"""
Generación del PDF de stock por bodega con ReportLab.

Mismo formato del script original `stock_repuestos_pdf.py` (título con el
nombre de la bodega, subtítulo con totales y tabla de artículos), pero
agregando la descripción del artículo junto al código, y devolviendo bytes en
memoria para servirlos por HTTP o comprimirlos.

La columna DESCRIPCIÓN solo se dibuja si los ítems traen descripción; si la
tabla StockRepuestos no tiene una columna reconocible, el PDF mantiene el
formato original de dos columnas (COD_SAP / STOCK).
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

# Ancho útil de la hoja A4 con los márgenes de 20 mm: 170 mm
ANCHOS_CON_DESC = [32 * mm, 113 * mm, 25 * mm]
ANCHOS_SIN_DESC = [95 * mm, 35 * mm]


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
    # Las descripciones son largas: se usa Paragraph para que corten en varias
    # líneas dentro de la celda en vez de desbordar la columna.
    celda = ParagraphStyle(
        'CeldaDescripcion',
        parent=base['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=10,
    )
    return base, titulo, sub, celda


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


def _tabla_articulos(items, estilo_celda):
    """Table de ReportLab con o sin la columna DESCRIPCIÓN según los datos."""
    con_descripcion = any((i.get('DESCRIPCION') or '').strip() for i in items)

    if con_descripcion:
        datos = [['COD_SAP', 'DESCRIPCIÓN', 'STOCK']]
        for i in items:
            datos.append([
                i['COD_SAP'],
                Paragraph((i.get('DESCRIPCION') or '').strip() or '-', estilo_celda),
                str(i['STOCK']),
            ])
        anchos = ANCHOS_CON_DESC
        col_stock = 2
    else:
        datos = [['COD_SAP', 'STOCK']]
        datos += [[i['COD_SAP'], str(i['STOCK'])] for i in items]
        anchos = ANCHOS_SIN_DESC
        col_stock = 1

    tabla = Table(datos, colWidths=anchos, repeatRows=1, hAlign='CENTER')
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), AZUL_HEADER),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9.5),
        ('ALIGN', (col_stock, 0), (col_stock, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.4, GRIS_BORDE),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, AZUL_FILA]),
    ]))
    return tabla


def generar_pdf_bodega(bodega, items):
    """PDF de una bodega: título + tabla de artículos. Devuelve bytes."""
    base, estilo_titulo, estilo_sub, estilo_celda = _estilos()

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
        _tabla_articulos(items, estilo_celda),
    ])
    return buffer.getvalue()


def generar_pdf_bodega_vacia(bodega):
    """PDF de aviso para bodegas sin repuestos con stock. Devuelve bytes."""
    base, estilo_titulo, estilo_sub, _ = _estilos()
    marca = datetime.now().strftime('%d-%m-%Y %H:%M')

    buffer = io.BytesIO()
    _documento(buffer, bodega).build([
        Paragraph(bodega, estilo_titulo),
        Paragraph(f'Generado {marca}', estilo_sub),
        Spacer(1, 6 * mm),
        Paragraph('Sin repuestos con stock mayor a 0.', base['Normal']),
    ])
    return buffer.getvalue()
