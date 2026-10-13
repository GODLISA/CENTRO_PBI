from django.apps import AppConfig
from django.db.backends.signals import connection_created


def _sqlite_pragmas(sender, connection, **kwargs):
    """Activa WAL y un busy_timeout en SQLite para soportar la concurrencia
    del polling bajo waitress (servidor WSGI multihilo)."""
    if connection.vendor == 'sqlite':
        cursor = connection.cursor()
        cursor.execute('PRAGMA journal_mode=WAL;')
        cursor.execute('PRAGMA busy_timeout=20000;')
        cursor.execute('PRAGMA synchronous=NORMAL;')


class TareasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tareas'
    verbose_name = 'Tareas'

    def ready(self):
        connection_created.connect(_sqlite_pragmas, dispatch_uid='tareas_sqlite_pragmas')
