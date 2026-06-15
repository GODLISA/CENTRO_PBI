"""Agrega el parámetro USD (dólar) usado como referencia en el PDF."""
from django.db import migrations


def crear_usd(apps, schema_editor):
    Parametro = apps.get_model('presupuestos', 'Parametro')
    Parametro.objects.get_or_create(
        codigo='USD',
        defaults={'nombre': 'Valor dólar', 'unidad': 'CLP', 'ambito': 'global'},
    )


def eliminar_usd(apps, schema_editor):
    apps.get_model('presupuestos', 'Parametro').objects.filter(codigo='USD').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('presupuestos', '0004_configuracionempresa_mostrar_logo_and_more'),
    ]

    operations = [
        migrations.RunPython(crear_usd, eliminar_usd),
    ]
