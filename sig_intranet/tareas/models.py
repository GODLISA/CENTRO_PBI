"""
Modelos del módulo Tareas: tablero de objetivos (burbujas) con tareas,
subtareas, dependencias y privacidad.

Jerarquía: Objetivo (burbuja) > Tarea > Subtarea.
El estado 'bloqueado' NO se almacena: es derivado (hay una dependencia
bloqueante sin cumplir). Ver tareas/services.py.
"""
import django
from django.conf import settings
from django.db import models
from django.db.models import Q

# CheckConstraint: el argumento se llama 'check' hasta Django 5.0 y 'condition'
# desde 5.1 (en 6.0 'check' ya no existe). El servidor corre 4.2.
_CHECK_KW = 'condition' if django.VERSION >= (5, 1) else 'check'


# ----- Choices (estilo clásico, como presupuestos/models.py) -----
ESTADO_PENDIENTE = 'pendiente'
ESTADO_EN_CURSO = 'en_curso'
ESTADO_COMPLETADO = 'completado'
ESTADOS = [
    (ESTADO_PENDIENTE, 'Pendiente'),
    (ESTADO_EN_CURSO, 'En curso'),
    (ESTADO_COMPLETADO, 'Completado'),
]

PRIORIDAD_ALTA = 'alta'
PRIORIDAD_MEDIA = 'media'
PRIORIDAD_BAJA = 'baja'
PRIORIDADES = [
    (PRIORIDAD_ALTA, 'Alta'),
    (PRIORIDAD_MEDIA, 'Media'),
    (PRIORIDAD_BAJA, 'Baja'),
]

RECURRENCIA_NO = ''
RECURRENCIA_DIARIA = 'diaria'
RECURRENCIA_SEMANAL = 'semanal'
RECURRENCIA_MENSUAL = 'mensual'
RECURRENCIAS = [
    (RECURRENCIA_NO, 'No recurrente'),
    (RECURRENCIA_DIARIA, 'Diaria'),
    (RECURRENCIA_SEMANAL, 'Semanal'),
    (RECURRENCIA_MENSUAL, 'Mensual'),
]

PERMISO_VER = 'ver'
PERMISO_EDITAR = 'editar'
PERMISOS = [
    (PERMISO_VER, 'Solo visualizar'),
    (PERMISO_EDITAR, 'Editar'),
]


class Objetivo(models.Model):
    """Burbuja: un objetivo general que agrupa tareas."""
    titulo = models.CharField(max_length=200)
    dueno = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='objetivos', verbose_name='Dueño')
    es_privada = models.BooleanField(default=False)
    # Posición manual global en el lienzo (todos ven el mismo layout)
    pos_x = models.FloatField(null=True, blank=True)
    pos_y = models.FloatField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Objetivo'
        verbose_name_plural = 'Objetivos'
        ordering = ['creado_en']

    def __str__(self):
        return self.titulo


class ObjetivoMiembro(models.Model):
    """Usuario invitado a un objetivo (ver o editar). El dueño y los
    responsables de tareas también son miembros, pero implícitos."""
    objetivo = models.ForeignKey(
        Objetivo, on_delete=models.CASCADE, related_name='miembros')
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='objetivos_invitado')
    permiso = models.CharField(max_length=10, choices=PERMISOS, default=PERMISO_VER)

    class Meta:
        verbose_name = 'Miembro de objetivo'
        verbose_name_plural = 'Miembros de objetivo'
        constraints = [
            models.UniqueConstraint(
                fields=['objetivo', 'usuario'], name='miembro_unico_por_objetivo'),
        ]

    def __str__(self):
        return f'{self.usuario} en {self.objetivo} ({self.permiso})'


class Tarea(models.Model):
    """Tarea de un objetivo. Peso 1 para el tamaño de la burbuja."""
    objetivo = models.ForeignKey(
        Objetivo, on_delete=models.CASCADE, related_name='tareas')
    titulo = models.CharField(max_length=200)
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='tareas_asignadas')
    estado = models.CharField(max_length=12, choices=ESTADOS, default=ESTADO_PENDIENTE)
    prioridad = models.CharField(max_length=6, choices=PRIORIDADES, default=PRIORIDAD_MEDIA)
    vence = models.DateField(null=True, blank=True)
    # Al completar una tarea recurrente se reabre con el siguiente vencimiento
    # (ver services.reabrir_si_recurrente). Vacío = tarea normal.
    recurrencia = models.CharField(
        max_length=8, choices=RECURRENCIAS, blank=True, default=RECURRENCIA_NO)
    # Fecha del último ciclo cumplido de una tarea recurrente. Sin esto, una
    # dependencia bloqueante hacia una recurrente nunca se cumpliría: la tarea
    # vuelve a 'pendiente' apenas se completa.
    ultima_completada = models.DateField(null=True, blank=True)
    orden = models.IntegerField(default=0)

    class Meta:
        verbose_name = 'Tarea'
        verbose_name_plural = 'Tareas'
        ordering = ['orden', 'id']

    def __str__(self):
        return self.titulo


class Subtarea(models.Model):
    """Subtarea de una tarea. Peso 0,1 para el tamaño de la burbuja."""
    tarea = models.ForeignKey(
        Tarea, on_delete=models.CASCADE, related_name='subtareas')
    titulo = models.CharField(max_length=200)
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='subtareas_asignadas')
    estado = models.CharField(max_length=12, choices=ESTADOS, default=ESTADO_PENDIENTE)
    orden = models.IntegerField(default=0)

    class Meta:
        verbose_name = 'Subtarea'
        verbose_name_plural = 'Subtareas'
        ordering = ['orden', 'id']

    def __str__(self):
        return self.titulo


class Dependencia(models.Model):
    """Dependencia de una tarea hacia otro objetivo, tarea o subtarea.
    Solo uno de los tres destinos está seteado. Bloquea solo si es bloqueante."""
    tarea_origen = models.ForeignKey(
        Tarea, on_delete=models.CASCADE, related_name='dependencias')
    objetivo_destino = models.ForeignKey(
        Objetivo, on_delete=models.CASCADE, null=True, blank=True, related_name='+')
    tarea_destino = models.ForeignKey(
        Tarea, on_delete=models.CASCADE, null=True, blank=True, related_name='+')
    subtarea_destino = models.ForeignKey(
        Subtarea, on_delete=models.CASCADE, null=True, blank=True, related_name='+')
    bloqueante = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Dependencia'
        verbose_name_plural = 'Dependencias'
        constraints = [
            models.CheckConstraint(
                name='dependencia_un_solo_destino',
                **{_CHECK_KW: (
                    (Q(objetivo_destino__isnull=False) & Q(tarea_destino__isnull=True) & Q(subtarea_destino__isnull=True)) |
                    (Q(objetivo_destino__isnull=True) & Q(tarea_destino__isnull=False) & Q(subtarea_destino__isnull=True)) |
                    (Q(objetivo_destino__isnull=True) & Q(tarea_destino__isnull=True) & Q(subtarea_destino__isnull=False))
                )},
            ),
        ]

    def __str__(self):
        return f'{self.tarea_origen} depende de {self.destino_label()}'

    def destino_label(self):
        if self.objetivo_destino_id:
            return f'objetivo:{self.objetivo_destino_id}'
        if self.tarea_destino_id:
            return f'tarea:{self.tarea_destino_id}'
        return f'subtarea:{self.subtarea_destino_id}'


class CambioTablero(models.Model):
    """Contador global de versión del tablero. Fila única (pk=1).
    Se incrementa en cada escritura; el front hace polling de este valor."""
    version = models.IntegerField(default=0)

    class Meta:
        verbose_name = 'Versión del tablero'
        verbose_name_plural = 'Versión del tablero'

    def __str__(self):
        return f'versión {self.version}'
