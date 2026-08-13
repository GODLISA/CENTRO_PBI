"""
Lectura del stock de repuestos por bodega desde SQL Server.

Adaptación del script `stock_repuestos_pdf.py` al proyecto SIG Intranet:
la configuración de conexión ya no se lee con python-dotenv, sino desde
`settings` (que a su vez parsea el .env del proyecto), y los PDF se pueden
generar en memoria para descargarlos comprimidos desde la intranet.

Fuente de datos: `select * from StockRepuestos;` — se agrupa por BODEGA y
solo se consideran las filas con STOCK > 0.
"""
import io
import re
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from django.conf import settings

from .pdf import generar_pdf_bodega, generar_pdf_bodega_vacia

QUERY = 'select * from StockRepuestos;'
COLUMNAS_REQUERIDAS = ('BODEGA', 'COD_SAP', 'STOCK')

# Drivers ODBC de SQL Server, del más nuevo al más antiguo
DRIVERS_PREFERIDOS = (
    'ODBC Driver 18 for SQL Server',
    'ODBC Driver 17 for SQL Server',
    'ODBC Driver 13.1 for SQL Server',
    'ODBC Driver 13 for SQL Server',
    'ODBC Driver 11 for SQL Server',
    'SQL Server Native Client 11.0',
    'SQL Server',
)


class InventarioError(Exception):
    """Error controlado del módulo: configuración, conexión o consulta."""


# ---------------------------------------------------------------- conexión ---
def _pyodbc():
    """Importa pyodbc de forma diferida para no romper el resto del sitio."""
    try:
        import pyodbc
    except ImportError as e:
        raise InventarioError(
            'Falta la librería pyodbc en el servidor. '
            'Instalar con: pip install pyodbc'
        ) from e
    return pyodbc


def detectar_driver():
    """Elige el driver ODBC de SQL Server más reciente instalado."""
    pyodbc = _pyodbc()
    disponibles = [d for d in pyodbc.drivers() if 'SQL Server' in d]
    if not disponibles:
        raise InventarioError(
            'No hay ningún driver ODBC de SQL Server instalado en el servidor. '
            'Instalar "ODBC Driver 18 for SQL Server" o definir SQL_DRIVER en el .env.'
        )
    for preferido in DRIVERS_PREFERIDOS:
        if preferido in disponibles:
            return preferido
    return disponibles[0]


def construir_cadena_conexion():
    """Arma la cadena ODBC con los valores de settings (leídos del .env)."""
    requeridos = {
        'SQL_SERVER': settings.SQL_SERVER,
        'SQL_DATABASE': settings.SQL_DATABASE,
        'SQL_USER': settings.SQL_USER,
        'SQL_PASSWORD': settings.SQL_PASSWORD,
    }
    faltantes = [nombre for nombre, valor in requeridos.items() if not valor]
    if faltantes:
        raise InventarioError(
            'Faltan variables en el .env: ' + ', '.join(faltantes)
        )

    driver = (settings.SQL_DRIVER or '').strip() or detectar_driver()

    servidor = settings.SQL_SERVER.strip()
    puerto = (settings.SQL_PORT or '').strip()
    if puerto and '\\' not in servidor and ',' not in servidor:
        servidor = f'{servidor},{puerto}'

    partes = [
        f'DRIVER={{{driver}}}',
        f'SERVER={servidor}',
        f'DATABASE={settings.SQL_DATABASE.strip()}',
        f'UID={settings.SQL_USER.strip()}',
        f'PWD={settings.SQL_PASSWORD}',
    ]

    encrypt = (settings.SQL_ENCRYPT or '').strip()
    if encrypt:
        partes.append(f'Encrypt={encrypt}')
    if (settings.SQL_TRUST_CERT or 'yes').strip().lower() in ('yes', 'true', '1'):
        partes.append('TrustServerCertificate=yes')

    return ';'.join(partes) + ';'


def obtener_filas():
    """Ejecuta la consulta y devuelve las filas como lista de diccionarios."""
    pyodbc = _pyodbc()
    cadena = construir_cadena_conexion()
    try:
        with pyodbc.connect(cadena, timeout=settings.SQL_TIMEOUT) as conexion:
            cursor = conexion.cursor()
            cursor.execute(QUERY)
            columnas = [c[0] for c in cursor.description]
            filas = [dict(zip(columnas, fila)) for fila in cursor.fetchall()]
    except pyodbc.Error as e:
        raise InventarioError(f'Falla de conexión o consulta a SQL Server: {e}') from e

    if filas:
        faltantes = set(COLUMNAS_REQUERIDAS) - set(filas[0].keys())
        if faltantes:
            raise InventarioError(
                'La consulta no devuelve las columnas: '
                + ', '.join(sorted(faltantes))
            )
    return filas


# ------------------------------------------------------------------ utils ---
def a_entero(valor):
    """Convierte el stock a entero; devuelve 0 si no es numérico."""
    if valor is None:
        return 0
    try:
        return int(float(str(valor).replace(',', '.')))
    except (TypeError, ValueError):
        return 0


def nombre_archivo_seguro(texto):
    """Limpia el nombre de la bodega para usarlo como nombre de archivo."""
    limpio = re.sub(r'[<>:"/\\|?*]+', '_', str(texto)).strip(' .')
    limpio = re.sub(r'\s+', ' ', limpio)
    return limpio[:120] or 'SIN_BODEGA'


def agrupar_por_bodega(filas, incluir_vacias=False):
    """
    Agrupa las filas por BODEGA considerando solo STOCK > 0.
    Con `incluir_vacias` se agregan las bodegas sin stock con una lista vacía.
    """
    grupos = defaultdict(list)
    for fila in filas:
        stock = a_entero(fila.get('STOCK'))
        if stock <= 0:
            continue
        bodega = (fila.get('BODEGA') or 'SIN BODEGA').strip()
        grupos[bodega].append({
            'COD_SAP': (fila.get('COD_SAP') or '').strip(),
            'STOCK': stock,
        })
    for bodega in grupos:
        grupos[bodega].sort(key=lambda r: r['COD_SAP'])

    if incluir_vacias:
        todas = {(f.get('BODEGA') or 'SIN BODEGA').strip() for f in filas}
        for bodega in todas - set(grupos):
            grupos[bodega] = []

    return dict(sorted(grupos.items()))


def obtener_stock_por_bodega(incluir_vacias=False):
    """Atajo: consulta SQL Server y devuelve el stock ya agrupado por bodega."""
    return agrupar_por_bodega(obtener_filas(), incluir_vacias=incluir_vacias)


def resumen_bodegas(grupos):
    """Resumen para la tabla de la vista: bodega, cantidad de ítems y unidades."""
    return [
        {
            'bodega': bodega,
            'repuestos': len(items),
            'unidades': sum(i['STOCK'] for i in items),
        }
        for bodega, items in grupos.items()
    ]


# -------------------------------------------------------------- generación ---
def pdf_de_bodega(bodega, items):
    """Bytes del PDF de una bodega (con aviso si no tiene stock)."""
    if items:
        return generar_pdf_bodega(bodega, items)
    return generar_pdf_bodega_vacia(bodega)


def generar_pdfs_en_disco(grupos, destino=None):
    """
    Escribe un PDF por bodega en `destino` (por defecto OUTPUT_DIR del .env)
    y devuelve la lista de rutas generadas.
    """
    carpeta = Path(destino) if destino else settings.INVENTARIOS_OUTPUT_DIR
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise InventarioError(f'No se pudo crear la carpeta de salida {carpeta}: {e}') from e

    rutas = []
    for bodega, items in grupos.items():
        archivo = carpeta / f'{nombre_archivo_seguro(bodega)}.pdf'
        try:
            archivo.write_bytes(pdf_de_bodega(bodega, items))
        except OSError as e:
            raise InventarioError(f'No se pudo escribir {archivo}: {e}') from e
        rutas.append(archivo)
    return rutas


def generar_zip(grupos, guardar_en_disco=True, destino=None):
    """
    Devuelve (nombre_zip, bytes) con un PDF por bodega dentro del comprimido.

    Con `guardar_en_disco` también deja los PDF sueltos en OUTPUT_DIR, para
    mantener el comportamiento del script original.
    """
    if guardar_en_disco:
        generar_pdfs_en_disco(grupos, destino=destino)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for bodega, items in grupos.items():
            zf.writestr(
                f'{nombre_archivo_seguro(bodega)}.pdf',
                pdf_de_bodega(bodega, items),
            )

    marca = datetime.now().strftime('%Y-%m-%d_%H%M')
    return f'StockRepuestos_{marca}.zip', buffer.getvalue()
