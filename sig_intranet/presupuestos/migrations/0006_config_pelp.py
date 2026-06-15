"""
Rellena la Configuración de empresa con los datos de PELP INTERNACIONAL S.A.
si todavía tiene el valor placeholder ('Mi Empresa' o vacío). No sobreescribe
una configuración ya personalizada en el admin.
"""
from django.db import migrations

PELP = {
    'nombre': 'PELP INTERNACIONAL S.A.',
    'rut': '96.501.840-9',
    'giro': 'IMPORTACIÓN Y EXPORTACIÓN DE TODA CLASE DE BIENES MUEBLES',
    'direccion': 'EL ROSAL 4560 – HUECHURABA, SANTIAGO – CHILE',
    'telefono': 'MESA CENTRAL: (2) 2870 – 4300 · SERVICIO TÉCNICO: (2) 2870 – 4350',
}


def aplicar(apps, schema_editor):
    Config = apps.get_model('presupuestos', 'ConfiguracionEmpresa')
    obj = Config.objects.first()
    if obj and obj.nombre in ('', 'Mi Empresa'):
        for campo, valor in PELP.items():
            setattr(obj, campo, valor)
        obj.save()


def revertir(apps, schema_editor):
    pass  # no se revierte: dejaría la config sin datos


class Migration(migrations.Migration):

    dependencies = [
        ('presupuestos', '0005_parametro_usd'),
    ]

    operations = [
        migrations.RunPython(aplicar, revertir),
    ]
