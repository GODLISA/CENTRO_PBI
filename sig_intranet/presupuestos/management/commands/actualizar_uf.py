"""
Obtiene el valor UF del día desde mindicador.cl y lo registra como
ValorParametro vigente desde hoy. Pensado para ejecutarse a diario
(Programador de tareas de Windows o cron):

    python manage.py actualizar_uf

Si el servidor no tiene salida a internet, el valor puede cargarse
manualmente en el admin (Presupuestos → Valores de parámetros).
"""
import json
import urllib.error
import urllib.request
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from presupuestos.models import Parametro, ValorParametro

API_URL = 'https://mindicador.cl/api/uf'


class Command(BaseCommand):
    help = 'Actualiza el valor UF del día desde mindicador.cl'

    def handle(self, *args, **options):
        try:
            parametro = Parametro.objects.get(codigo=Parametro.COD_UF)
        except Parametro.DoesNotExist:
            raise CommandError('No existe el parámetro UF. Ejecute las migraciones primero.')

        try:
            with urllib.request.urlopen(API_URL, timeout=20) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            valor = Decimal(str(data['serie'][0]['valor']))
        except (urllib.error.URLError, KeyError, IndexError, ValueError) as e:
            raise CommandError(
                f'No se pudo obtener la UF desde {API_URL}: {e}. '
                'Puede cargar el valor manualmente en el admin.'
            )

        hoy = timezone.localdate()
        registro, creado = ValorParametro.objects.update_or_create(
            parametro=parametro,
            zona=None,
            vigente_desde=hoy,
            defaults={'valor': valor, 'observacion': 'Actualización automática (mindicador.cl)'},
        )
        accion = 'creado' if creado else 'actualizado'
        self.stdout.write(self.style.SUCCESS(
            f'Valor UF {accion}: ${valor} (vigente desde {hoy})'
        ))
