"""
Obtiene los valores UF y dólar del día desde mindicador.cl y los registra
como ValorParametro vigentes desde hoy. Pensado para ejecutarse a diario
(Programador de tareas de Windows o cron):

    python manage.py actualizar_uf

Si el servidor no tiene salida a internet, los valores pueden cargarse
manualmente en el admin (Presupuestos → Valores de parámetros).
"""
import json
import urllib.error
import urllib.request
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from presupuestos.models import Parametro, ValorParametro

API = 'https://mindicador.cl/api/{indicador}'
INDICADORES = {Parametro.COD_UF: 'uf', Parametro.COD_USD: 'dolar'}


class Command(BaseCommand):
    help = 'Actualiza los valores UF y dólar del día desde mindicador.cl'

    def handle(self, *args, **options):
        hoy = timezone.localdate()
        actualizados = []
        errores = []

        for codigo, indicador in INDICADORES.items():
            try:
                parametro = Parametro.objects.get(codigo=codigo)
            except Parametro.DoesNotExist:
                errores.append(f'{codigo}: parámetro inexistente (ejecute migraciones)')
                continue
            try:
                with urllib.request.urlopen(API.format(indicador=indicador), timeout=20) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                valor = Decimal(str(data['serie'][0]['valor']))
            except (urllib.error.URLError, OSError, KeyError, IndexError, ValueError) as e:
                # OSError cubre cortes de conexión (RemoteDisconnected, timeouts, etc.)
                errores.append(f'{codigo}: {e}')
                continue

            ValorParametro.objects.update_or_create(
                parametro=parametro, zona=None, vigente_desde=hoy,
                defaults={'valor': valor, 'observacion': 'Actualización automática (mindicador.cl)'},
            )
            actualizados.append(f'{codigo}=${valor}')

        if actualizados:
            self.stdout.write(self.style.SUCCESS(
                f'Actualizado ({hoy}): ' + ', '.join(actualizados)
            ))
        for err in errores:
            self.stdout.write(self.style.WARNING(err))
        if not actualizados:
            raise CommandError(
                'No se pudo actualizar ningún indicador. Cargue los valores manualmente en el admin.'
            )
