from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tareas', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='tarea',
            name='recurrencia',
            field=models.CharField(
                blank=True,
                choices=[
                    ('', 'No recurrente'),
                    ('diaria', 'Diaria'),
                    ('semanal', 'Semanal'),
                    ('mensual', 'Mensual'),
                ],
                default='',
                max_length=8,
            ),
        ),
    ]
