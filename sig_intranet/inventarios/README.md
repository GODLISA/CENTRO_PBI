# Módulo Inventarios — Stock de repuestos por bodega

Menú independiente (`/inventarios/`) que lee la tabla **StockRepuestos** de SQL Server,
agrupa por `BODEGA` considerando solo `STOCK > 0` y genera un PDF por bodega con las
columnas `COD_SAP`, `DESCRIPCIÓN` y `STOCK`.

Es la versión web del script `stock_repuestos_pdf.py`: misma consulta, mismo formato de
PDF, pero integrado a la intranet y con **descarga de todos los PDF en un único .zip**.

## Configuración (.env)

Las credenciales se leen del `.env` del proyecto (`sig_intranet/.env`), que ya se parsea
en `settings.py`. Ver `sig_intranet/.env.example`:

```
SQL_SERVER=192.168.0.10
SQL_PORT=1433
SQL_DATABASE=NombreBaseDatos
SQL_USER=usuario_lectura
SQL_PASSWORD=cambiar_esta_clave
SQL_DRIVER=
SQL_COL_DESCRIPCION=
SQL_TRUST_CERT=yes
SQL_ENCRYPT=no
SQL_TIMEOUT=30
OUTPUT_DIR=PDF_StockRepuestos
```

- `SQL_DRIVER` vacío → el módulo detecta el driver ODBC más nuevo instalado.
- `SQL_COL_DESCRIPCION` vacío → se autodetecta la columna de descripción entre
  `DESCRIPCION`, `DESCRIPCIÓN`, `DESC_SAP`, `DESCRIPCION_SAP`, `DESCRIPCION_ARTICULO`,
  `NOMBRE_ARTICULO`, `MATERIAL_DESC`, `TEXTO_BREVE`, `DETALLE`, `GLOSA`, `ARTICULO`,
  `NOMBRE` y `DESC`. Si la tabla usa otro nombre, indíquelo aquí. Si no hay ninguna,
  el PDF sale con el formato original de dos columnas.
- `OUTPUT_DIR` relativo se resuelve desde `sig_intranet/`.
- El `.env` se parsea línea a línea: **sin comillas** y **sin comentarios al final de la línea**.

## Requisitos

```bash
pip install pyodbc reportlab
```

Además, el servidor necesita el *ODBC Driver for SQL Server* de Microsoft instalado
(gratuito). Si falta, la pantalla muestra el error correspondiente sin caerse.

## URLs

| URL | Descripción |
|-----|-------------|
| `/inventarios/` | Resumen por bodega + botón de descarga del ZIP |
| `/inventarios/stock-repuestos/zip/` | (POST) Genera los PDF y descarga el `.zip` |
| `/inventarios/stock-repuestos/pdf/?bodega=NOMBRE` | PDF de una sola bodega |

Todas las vistas requieren sesión iniciada (`@login_required`).

## Uso

1. Entrar a **📦 Inventarios** desde el panel principal.
2. La pantalla consulta SQL Server y muestra bodegas, repuestos y unidades.
3. Opcional: marcar *Incluir bodegas sin stock* → genera un PDF con aviso para esas bodegas.
4. Botón **⬇️ Descargar todos los PDF (.zip)**: genera un PDF por bodega, deja una copia
   en `OUTPUT_DIR` y descarga el comprimido `StockRepuestos_AAAA-MM-DD_HHMM.zip`.

## Uso por consola

```bash
python manage.py generar_stock_repuestos
python manage.py generar_stock_repuestos --salida C:\ruta\destino
python manage.py generar_stock_repuestos --incluir-vacias --zip
```

## Estructura

- `services.py` — conexión ODBC, consulta, agrupación por bodega, PDF en disco y ZIP.
- `pdf.py` — armado del PDF con ReportLab (devuelve bytes).
- `views.py` — pantalla, descarga del ZIP y PDF individual.
- `management/commands/generar_stock_repuestos.py` — equivalente por consola.
- `templates/inventarios/` — `base.html` (menú del módulo) y `stock_repuestos.html`.

Los errores de configuración, conexión o consulta se levantan como `InventarioError`
y se muestran en pantalla; no hay modelos ni migraciones (los datos viven en SQL Server).
