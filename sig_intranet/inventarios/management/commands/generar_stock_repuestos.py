"""
Equivalente por consola del módulo web de stock de repuestos.

Uso:
    python manage.py generar_stock_repuestos
    python manage.py generar_stock_repuestos --salida C:\\ruta\\destino
    python manage.py generar_stock_repuestos --incluir-vacias --zip
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from inventarios import services
from inventarios.services import InventarioError


class Command(BaseCommand):
    help = 'Genera un PDF de stock por cada bodega desde la tabla StockRepuestos.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--salida',
            help='Carpeta de salida (por defecto OUTPUT_DIR del .env).',
        )
        parser.add_argument(
            '--incluir-vacias',
            action='store_true',
            help='Genera también un PDF con aviso para bodegas sin stock > 0.',
        )
        parser.add_argument(
            '--zip',
            action='store_true',
            help='Además de los PDF, deja un .zip con todos ellos.',
        )

    def handle(self, *args, **opciones):
        destino = Path(opciones['salida']) if opciones['salida'] else settings.INVENTARIOS_OUTPUT_DIR

        self.stdout.write('Conectando a SQL Server...')
        try:
            filas = services.obtener_filas()
            self.stdout.write(f'Filas leídas: {len(filas)}')
            grupos = services.agrupar_por_bodega(
                filas, incluir_vacias=opciones['incluir_vacias']
            )

            if not grupos:
                self.stdout.write(self.style.WARNING(
                    'No hay repuestos con stock mayor a 0. No se generaron PDF.'
                ))
                return

            rutas = services.generar_pdfs_en_disco(grupos, destino=destino)
            for ruta, (bodega, items) in zip(rutas, grupos.items()):
                detalle = f'{len(items)} repuestos' if items else 'sin stock'
                self.stdout.write(f'  OK {ruta.name} ({detalle})')

            if opciones['zip']:
                nombre, contenido = services.generar_zip(grupos, guardar_en_disco=False)
                archivo_zip = destino / nombre
                archivo_zip.write_bytes(contenido)
                self.stdout.write(f'  ZIP {archivo_zip.name}')

        except InventarioError as e:
            raise CommandError(str(e))

        self.stdout.write(self.style.SUCCESS(
            f'Listo: {len(grupos)} PDF en {destino}'
        ))
