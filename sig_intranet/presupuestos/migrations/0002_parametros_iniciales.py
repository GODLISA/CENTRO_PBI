"""
Datos semilla: crea los parámetros que usa el motor de cálculo (UF, VALOR_KM,
IVA) y un valor inicial para el IVA (19%). Los valores de UF y VALOR_KM deben
cargarse en el admin o con el comando `actualizar_uf` (solo UF).
"""
from django.db import migrations


def crear_parametros(apps, schema_editor):
    Parametro = apps.get_model('presupuestos', 'Parametro')
    ValorParametro = apps.get_model('presupuestos', 'ValorParametro')

    uf, _ = Parametro.objects.get_or_create(
        codigo='UF',
        defaults={'nombre': 'Valor UF', 'unidad': 'CLP', 'ambito': 'global'},
    )
    Parametro.objects.get_or_create(
        codigo='VALOR_KM',
        defaults={'nombre': 'Valor traslado por km', 'unidad': 'CLP/km', 'ambito': 'zona'},
    )
    iva, _ = Parametro.objects.get_or_create(
        codigo='IVA',
        defaults={'nombre': 'IVA', 'unidad': '%', 'ambito': 'global'},
    )
    if not ValorParametro.objects.filter(parametro=iva).exists():
        ValorParametro.objects.create(
            parametro=iva,
            valor=19,
            vigente_desde='2000-01-01',
            observacion='Valor inicial',
        )


def eliminar_parametros(apps, schema_editor):
    Parametro = apps.get_model('presupuestos', 'Parametro')
    Parametro.objects.filter(codigo__in=['UF', 'VALOR_KM', 'IVA']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('presupuestos', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(crear_parametros, eliminar_parametros),
    ]
