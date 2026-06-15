"""
Carga la matriz de cobros inicial (extraída del Excel
"MATRIZ DE CALCULO - Cobros a PI.xlsx") desde data/matriz_inicial.json:

- Zonas (Centro, Norte, Sur) con sus comunas y km de traslado (ida + regreso).
- Áreas de servicio con sus ítems de cobro (UF o CLP).
- Valor del parámetro VALOR_KM ($300/km, igual para todas las zonas).

Es idempotente: puede ejecutarse varias veces; actualiza precios/km de los
registros existentes y crea los que falten. No borra registros agregados a
mano en el admin.

    python manage.py cargar_matriz
"""
import json
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from presupuestos.models import (
    AreaServicio, Comuna, ItemMatriz, Parametro, ValorParametro, Zona,
)

RUTA_DATOS = Path(__file__).resolve().parent.parent.parent / 'data' / 'matriz_inicial.json'

# Valor de traslado por km según la matriz Excel (mismo para todas las zonas)
VALOR_KM = Decimal('300')


class Command(BaseCommand):
    help = 'Carga zonas, comunas, áreas e ítems de la matriz de cobros inicial'

    @transaction.atomic
    def handle(self, *args, **options):
        with open(RUTA_DATOS, encoding='utf-8') as f:
            datos = json.load(f)

        # --- Zonas y comunas ---
        comunas_creadas = comunas_actualizadas = 0
        for dz in datos['zonas']:
            zona, _ = Zona.objects.update_or_create(
                nombre=dz['nombre'], defaults={'descripcion': dz['descripcion']},
            )
            for dc in dz['comunas']:
                _, creada = Comuna.objects.update_or_create(
                    zona=zona, nombre=dc['nombre'],
                    defaults={
                        'region': dc['region'],
                        'km_ida_regreso': Decimal(str(dc['km_ida_regreso'])),
                    },
                )
                if creada:
                    comunas_creadas += 1
                else:
                    comunas_actualizadas += 1

        # --- Áreas e ítems ---
        items_creados = items_actualizados = 0
        for da in datos['areas']:
            area, _ = AreaServicio.objects.update_or_create(
                nombre=da['nombre'], defaults={'descripcion': da['descripcion']},
            )
            for orden, di in enumerate(da['items']):
                _, creado = ItemMatriz.objects.update_or_create(
                    area=area, concepto=di['concepto'],
                    defaults={
                        'unidad': di['unidad'],
                        'moneda': di['moneda'],
                        'precio_unitario': Decimal(str(di['precio'])),
                        'orden': orden,
                    },
                )
                if creado:
                    items_creados += 1
                else:
                    items_actualizados += 1

        # --- Valor km global ($300/km según la matriz) ---
        param_km = Parametro.objects.get(codigo=Parametro.COD_VALOR_KM)
        vigente = param_km.valor_vigente()
        if vigente is None or vigente.valor != VALOR_KM:
            ValorParametro.objects.update_or_create(
                parametro=param_km, zona=None,
                vigente_desde=timezone.localdate(),
                defaults={
                    'valor': VALOR_KM,
                    'observacion': 'Matriz Excel: $300/km (ida + regreso), todas las zonas',
                },
            )
            self.stdout.write(f'VALOR_KM fijado en ${VALOR_KM}/km')

        self.stdout.write(self.style.SUCCESS(
            f'Zonas: {len(datos["zonas"])} | '
            f'Comunas: {comunas_creadas} creadas, {comunas_actualizadas} actualizadas | '
            f'Ítems: {items_creados} creados, {items_actualizados} actualizados'
        ))
        if not ValorParametro.objects.filter(parametro__codigo=Parametro.COD_UF).exists():
            self.stdout.write(self.style.WARNING(
                'Falta el valor UF: ejecute "python manage.py actualizar_uf" '
                'o cárguelo en el admin.'
            ))
