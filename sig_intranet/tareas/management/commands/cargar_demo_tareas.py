"""
Carga datos de ejemplo en el módulo Tareas (opcional).

Uso típico para UAT local:
    python manage.py cargar_demo_tareas --owner jvega --con-usuarios

- --owner <username>: dueño de los objetivos de ejemplo (por defecto, el
  primer superusuario).
- --con-usuarios: crea usuarios de ejemplo (mperez, lgonzalez, acortes, rsoto)
  con una contraseña de PRUEBA para poder validar privacidad/multiusuario en
  local. NO usar en producción.
- --password <clave>: contraseña para esos usuarios de prueba (default Demo.2026).
- --reset: elimina los objetivos de ejemplo previos (por título) antes de cargar.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tareas.models import (
    Dependencia, Objetivo, ObjetivoMiembro, Subtarea, Tarea,
    ESTADO_PENDIENTE, ESTADO_EN_CURSO, ESTADO_COMPLETADO, PERMISO_VER,
)

User = get_user_model()

USUARIOS_DEMO = ['mperez', 'lgonzalez', 'acortes', 'rsoto']

# (titulo objetivo, dueño, privada, [viewers (username, perm)], [tareas])
# tarea: (titulo, responsable, estado, prioridad, vence, [subtareas])
# subtarea: (titulo, responsable, estado)
TITULOS_DEMO = [
    'Lanzamiento ERP', 'Infraestructura Servidores',
    'Campaña Marketing Q4', 'Objetivos del área TI',
]


class Command(BaseCommand):
    help = 'Carga objetivos/tareas de ejemplo en el módulo Tareas (opcional, para UAT).'

    def add_arguments(self, parser):
        parser.add_argument('--owner', type=str, default=None)
        parser.add_argument('--con-usuarios', action='store_true')
        parser.add_argument('--password', type=str, default='Demo.2026')
        parser.add_argument('--reset', action='store_true')

    def handle(self, *args, **opts):
        owner = self._resolver_owner(opts.get('owner'))
        users = self._resolver_usuarios(owner, opts['con_usuarios'], opts['password'])

        if opts['reset']:
            n, _ = Objetivo.objects.filter(titulo__in=TITULOS_DEMO).delete()
            self.stdout.write(self.style.WARNING('Objetivos de ejemplo previos eliminados.'))

        with transaction.atomic():
            self._cargar(users)

        self.stdout.write(self.style.SUCCESS('Datos de ejemplo cargados.'))
        if opts['con_usuarios']:
            self.stdout.write(self.style.WARNING(
                'Usuarios de prueba creados con contraseña "%s" (SOLO pruebas locales).'
                % opts['password']))

    def _resolver_owner(self, username):
        if username:
            u = User.objects.filter(username=username).first()
            if not u:
                raise CommandError('No existe el usuario --owner "%s".' % username)
            return u
        u = User.objects.filter(is_superuser=True).order_by('id').first()
        if not u:
            raise CommandError('No hay superusuario. Pasa --owner <username> o crea uno.')
        return u

    def _resolver_usuarios(self, owner, con_usuarios, password):
        """Devuelve un dict {clave_demo: User}. Sin --con-usuarios, todo cae en owner."""
        mapa = {'jvega': owner}
        for uname in USUARIOS_DEMO:
            if con_usuarios:
                u, creado = User.objects.get_or_create(
                    username=uname, defaults={'email': '%s@pelp.cl' % uname})
                if creado:
                    u.set_password(password)
                    u.save()
                mapa[uname] = u
            else:
                mapa[uname] = owner
        return mapa

    def _cargar(self, u):
        # B1 - Lanzamiento ERP (público)
        b1 = Objetivo.objects.create(titulo='Lanzamiento ERP', dueno=u['jvega'], es_privada=False)
        ObjetivoMiembro.objects.get_or_create(objetivo=b1, usuario=u['rsoto'], defaults={'permiso': PERMISO_VER})
        t1 = Tarea.objects.create(objetivo=b1, titulo='Migrar datos maestros', responsable=u['mperez'],
                                  estado=ESTADO_COMPLETADO, prioridad='alta', vence='2026-10-20', orden=0)
        Subtarea.objects.create(tarea=t1, titulo='Clientes', responsable=u['mperez'], estado=ESTADO_COMPLETADO, orden=0)
        Subtarea.objects.create(tarea=t1, titulo='Proveedores', responsable=u['mperez'], estado=ESTADO_COMPLETADO, orden=1)
        Subtarea.objects.create(tarea=t1, titulo='Artículos', responsable=u['lgonzalez'], estado=ESTADO_COMPLETADO, orden=2)
        t2 = Tarea.objects.create(objetivo=b1, titulo='Capacitar usuarios', responsable=u['lgonzalez'],
                                  estado=ESTADO_EN_CURSO, prioridad='media', vence='2026-10-28', orden=1)
        Subtarea.objects.create(tarea=t2, titulo='Preparar material', responsable=u['lgonzalez'], estado=ESTADO_COMPLETADO, orden=0)
        Subtarea.objects.create(tarea=t2, titulo='Dictar sesiones', responsable=u['lgonzalez'], estado=ESTADO_PENDIENTE, orden=1)
        t3 = Tarea.objects.create(objetivo=b1, titulo='Salida a producción', responsable=u['jvega'],
                                  estado=ESTADO_PENDIENTE, prioridad='alta', vence='2026-11-05', orden=2)

        # B2 - Infraestructura Servidores (público)
        b2 = Objetivo.objects.create(titulo='Infraestructura Servidores', dueno=u['mperez'], es_privada=False)
        Tarea.objects.create(objetivo=b2, titulo='Comprar servidores', responsable=u['mperez'],
                             estado=ESTADO_COMPLETADO, prioridad='media', vence='2026-10-10', orden=0)
        t5 = Tarea.objects.create(objetivo=b2, titulo='Configurar red', responsable=u['acortes'],
                                  estado=ESTADO_EN_CURSO, prioridad='alta', vence='2026-10-30', orden=1)
        Subtarea.objects.create(tarea=t5, titulo='Segmentar VLANs', responsable=u['acortes'], estado=ESTADO_COMPLETADO, orden=0)
        Subtarea.objects.create(tarea=t5, titulo='Reglas de firewall', responsable=u['acortes'], estado=ESTADO_EN_CURSO, orden=1)

        # B3 - Campaña Marketing Q4 (público)
        b3 = Objetivo.objects.create(titulo='Campaña Marketing Q4', dueno=u['lgonzalez'], es_privada=False)
        t6 = Tarea.objects.create(objetivo=b3, titulo='Diseño gráfico', responsable=u['lgonzalez'],
                                  estado=ESTADO_COMPLETADO, prioridad='media', vence='2026-10-15', orden=0)
        Subtarea.objects.create(tarea=t6, titulo='Piezas para redes', responsable=u['lgonzalez'], estado=ESTADO_COMPLETADO, orden=0)
        Subtarea.objects.create(tarea=t6, titulo='Banner web', responsable=u['lgonzalez'], estado=ESTADO_COMPLETADO, orden=1)
        Tarea.objects.create(objetivo=b3, titulo='Pauta en redes', responsable=u['rsoto'],
                             estado=ESTADO_EN_CURSO, prioridad='media', vence='2026-11-01', orden=1)
        t8 = Tarea.objects.create(objetivo=b3, titulo='Landing page', responsable=u['jvega'],
                                  estado=ESTADO_PENDIENTE, prioridad='alta', vence='2026-11-03', orden=2)

        # B4 - Objetivos del área TI (PRIVADO)
        b4 = Objetivo.objects.create(titulo='Objetivos del área TI', dueno=u['jvega'], es_privada=True)
        ObjetivoMiembro.objects.get_or_create(objetivo=b4, usuario=u['acortes'], defaults={'permiso': PERMISO_VER})
        t9 = Tarea.objects.create(objetivo=b4, titulo='Certificación Cloud', responsable=u['jvega'],
                                  estado=ESTADO_EN_CURSO, prioridad='media', vence='2026-12-01', orden=0)
        Tarea.objects.create(objetivo=b4, titulo='Documentar procesos internos', responsable=u['jvega'],
                             estado=ESTADO_PENDIENTE, prioridad='baja', vence='2026-12-15', orden=1)

        # Dependencias: T3->B2 (bloqueante); T8->T5 y T8->T9 (no bloquean)
        Dependencia.objects.create(tarea_origen=t3, objetivo_destino=b2, bloqueante=True)
        Dependencia.objects.create(tarea_origen=t8, tarea_destino=t5, bloqueante=False)
        Dependencia.objects.create(tarea_origen=t8, tarea_destino=t9, bloqueante=False)
