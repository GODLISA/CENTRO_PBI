from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tareas', '0002_tarea_recurrencia'),
    ]

    operations = [
        migrations.AddField(
            model_name='tarea',
            name='ultima_completada',
            field=models.DateField(blank=True, null=True),
        ),
    ]
