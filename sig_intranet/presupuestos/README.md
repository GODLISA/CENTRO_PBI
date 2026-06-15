# Módulo de Presupuestos

Herramienta para generar presupuestos mediante matrices de cálculo por área de
servicio, con descarga en PDF. Forma parte de la intranet SIG (`/presupuestos/`).

## Conceptos

| Concepto | Dónde se edita | Descripción |
|---|---|---|
| **Área de servicio** | Admin → Presupuestos → Áreas de servicio | Cada área tiene su propia matriz de cobros. |
| **Matriz de cobros (ítems)** | Admin → Áreas de servicio (inline) o Matriz de cobros | Conceptos cobrables con unidad, moneda (CLP o UF) y precio unitario. Editables en cualquier momento. |
| **Zona** | Admin → Zonas | Zonas geográficas (Centro, Norte, Sur); permiten valores por km distintos. |
| **Comuna** | Admin → Comunas (o inline en Zonas) | Comunas con km de traslado **ida + regreso**; autocompletan la distancia en el formulario. |
| **Parámetros** | Admin → Parámetros / Valores de parámetros | Variables que cambian por fecha y/o zona: `UF`, `VALOR_KM`, `IVA`. |
| **Configuración empresa/PDF** | Admin → Configuración de empresa / PDF | Datos PELP, textos de observaciones, condiciones y pie del PDF. |

## Formato del PDF

El PDF replica estrictamente el presupuesto PELP de referencia
("PRESUPUESTO N°1888"): membrete PELP, caja **R.U.T. / PRESUPUESTO / N°**,
referencia **(USD)** y **(UF)** del día, datos del cliente en grilla, barra
verde de **ALCANCES / OBSERVACIONES** con el título del trabajo, tabla de
detalle con encabezado gris (DETALLE · Valor Un.(\*) · Cantidad ·
Subtotal(\*)), totales **TOTAL NETO / IVA 19% / TOTAL A PAGAR** en verde
claro, nota "(\*) VALORES NO INCLUYEN IVA" y el pie de condiciones. Colores y
fuente tomados del Excel original (verde accent3 `#9BBB59`, header gris
`#D9D9D9`, Arial Narrow / Helvetica 10 pt). El membrete está en
`static/presupuestos/img/pelp_membrete.png`; los textos (reenvío,
aprobación, validez, condiciones) se editan en la Configuración de empresa.

El dólar **(USD)** es referencial: lo carga `actualizar_uf` junto con la UF
(mindicador.cl `/dolar`). Si falta, el PDF muestra "-" sin interrumpir el
cálculo.

## Cómo funciona el versionado de valores

Los valores de parámetros **no se editan: se agregan**. Cada registro tiene una
fecha `vigente_desde`; el motor toma el valor más reciente cuya fecha sea menor
o igual a la fecha de emisión del presupuesto.

- **Valor UF (cambia por día):** agregar un valor nuevo cada día, o automatizar
  con el comando:

  ```
  python manage.py actualizar_uf
  ```

  (obtiene la UF del día desde mindicador.cl; programarlo a diario con el
  Programador de tareas de Windows). Si el servidor no tiene internet, cargar
  el valor a mano en el admin.

- **Valor traslado por km (cambia por zona):** el parámetro `VALOR_KM` es de
  ámbito "por zona". Se puede cargar un valor global (campo zona vacío) y
  valores específicos por zona; el motor usa el de la zona y si no existe cae
  al global.

- **IVA:** viene precargado en 19%. Si cambia la ley, agregar un valor nuevo
  con la fecha desde la que rige.

## Snapshots (integridad histórica)

Al guardar un presupuesto se copian a éste el precio de cada ítem, el valor UF,
el valor km y el % IVA usados. **Editar las matrices o parámetros a futuro no
altera presupuestos ya emitidos.**

## Datos iniciales desde la matriz Excel

La matriz real ("MATRIZ DE CALCULO - Cobros a PI.xlsx") está convertida a
`data/matriz_inicial.json` y se carga/actualiza con:

```
python manage.py cargar_matriz
```

Carga: zonas Centro/Norte/Sur con sus comunas y km (ida + regreso), las 3
áreas (Instalación Eq. Gastronómicos, Instalación Eq. de Taller, Mantención
Preventiva Eq. Gastronómicos) con ~210 ítems, y el VALOR_KM de $300/km. Es
idempotente: re-ejecutarla actualiza precios sin duplicar ni borrar lo
agregado a mano. Si llega una versión nueva del Excel, regenerar el JSON con
`data/extraer_matriz_excel.py "ruta\al\excel.xlsx"` y volver a ejecutar el
comando.

Convención de los precios en UF: los ítems en UF se multiplican por la UF
del día y al final se agrega el 19% de IVA (los precios de las matrices son
netos, como indica el propio Excel: "valores no incluyen IVA").

## Flujo de uso

1. `Presupuestos → + Nuevo`: datos del cliente, área, zona y comuna (la
   comuna autocompleta los km ida + regreso; se pueden ajustar a mano).
2. Al elegir el área se carga su matriz; se agregan ítems con cantidades
   (también se pueden agregar líneas manuales). El total se estima en vivo.
3. Guardar → el backend calcula con los parámetros vigentes y asigna un número
   correlativo anual (`P-2026-0001`).
4. Desde el detalle: **Descargar PDF** y cambiar estado (borrador → emitido →
   aceptado/rechazado).

## Despliegue

```powershell
pip install -r requirements.txt        # agrega reportlab
python manage.py migrate               # crea tablas + parámetros semilla
python manage.py collectstatic --noinput  # publica css/js del módulo (DEBUG=False)
```

Luego, en el admin: crear áreas con sus ítems, zonas, y cargar valores de
`UF` y `VALOR_KM`.

## Tests

```powershell
python manage.py test presupuestos
```
