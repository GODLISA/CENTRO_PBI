"""
Lógica de negocio del módulo Tareas (autoritativa en el servidor):
reglas de peso/completado/bloqueo, visibilidad y permisos, serialización
del tablero para el front y detección de ciclos de dependencias.
"""
import calendar
import datetime

from django.contrib.auth import get_user_model
from django.db.models import F, Q
from django.utils import timezone

from .models import (
    CambioTablero, Dependencia, Objetivo, Subtarea, Tarea,
    ESTADO_COMPLETADO, ESTADO_EN_CURSO, ESTADO_PENDIENTE, PERMISO_EDITAR,
    RECURRENCIA_DIARIA, RECURRENCIA_SEMANAL, RECURRENCIA_MENSUAL,
)

User = get_user_model()


# ----- IDs con prefijo (el front los usa como ids opacos) -----
def uid(pk):
    return 'u%s' % pk if pk is not None else None


def oid(pk):
    return 'o%s' % pk


def tid(pk):
    return 't%s' % pk


def sid(pk):
    return 's%s' % pk


def parse_pk(valor):
    """De 'o12'/'t5'/'s3'/'u7' (o un número) al entero pk."""
    if valor is None:
        return None
    s = str(valor)
    if s and s[0] in 'outs':
        s = s[1:]
    return int(s)


# ----- Versión / polling -----
def version_actual():
    row, _ = CambioTablero.objects.get_or_create(pk=1)
    return row.version


def bump_version():
    CambioTablero.objects.get_or_create(pk=1)
    CambioTablero.objects.filter(pk=1).update(version=F('version') + 1)
    return version_actual()


# ----- Reglas de negocio -----
def peso_objetivo(obj):
    total = 0.0
    for t in obj.tareas.all():
        total += 1 + len(list(t.subtareas.all())) * 0.1
    return total


def tarea_completada(tarea):
    subs = list(tarea.subtareas.all())
    if subs:
        return all(s.estado == ESTADO_COMPLETADO for s in subs)
    return tarea.estado == ESTADO_COMPLETADO


def peso_completado(obj):
    total = 0.0
    for t in obj.tareas.all():
        for s in t.subtareas.all():
            if s.estado == ESTADO_COMPLETADO:
                total += 0.1
        if tarea_completada(t):
            total += 1
    return total


def pct_objetivo(obj):
    peso = peso_objetivo(obj)
    if peso <= 0:
        return 0
    return round(peso_completado(obj) / peso * 100)


def objetivo_completado(obj):
    tareas = list(obj.tareas.all())
    return len(tareas) > 0 and all(tarea_completada(t) for t in tareas)


def dep_cumplida(dep):
    if dep.objetivo_destino_id:
        tareas = list(dep.objetivo_destino.tareas.all())
        return len(tareas) > 0 and all(tarea_cumplida_para_dependencia(t) for t in tareas)
    if dep.tarea_destino_id:
        return tarea_cumplida_para_dependencia(dep.tarea_destino)
    if dep.subtarea_destino_id:
        sub = dep.subtarea_destino
        # Si la tarea padre es recurrente, sus subtareas se reabren con ella:
        # el ciclo vigente del padre es lo que decide.
        if sub.tarea.recurrencia:
            return ciclo_recurrente_vigente(sub.tarea)
        return sub.estado == ESTADO_COMPLETADO
    return True


def tarea_bloqueada(tarea):
    return any(d.bloqueante and not dep_cumplida(d) for d in tarea.dependencias.all())


def estado_efectivo_tarea(tarea):
    if tarea_bloqueada(tarea):
        return 'bloqueado'
    if tarea_completada(tarea):
        return ESTADO_COMPLETADO
    subs = list(tarea.subtareas.all())
    if subs and any(s.estado == ESTADO_COMPLETADO for s in subs):
        return ESTADO_EN_CURSO
    return tarea.estado


def recalcular_estado_tarea(tarea):
    """Ajusta el estado de la tarea según sus subtareas (rollup hacia arriba).
    Devuelve True si la tarea quedó completada por este recálculo. NO reabre
    recurrentes: eso lo decide la vista, solo cuando el usuario completa una
    subtarea (si no, borrar una subtarea reabriría el ciclo y perdería avance)."""
    subs = list(tarea.subtareas.all())
    if not subs:
        return False
    if all(s.estado == ESTADO_COMPLETADO for s in subs):
        tarea.estado = ESTADO_COMPLETADO
    elif tarea.estado == ESTADO_COMPLETADO:
        tarea.estado = ESTADO_EN_CURSO
    tarea.save(update_fields=['estado'])
    return tarea.estado == ESTADO_COMPLETADO


# ----- Recurrencia -----
def siguiente_vencimiento(desde, recurrencia):
    """Fecha del próximo ciclo. En mensual, el día se recorta al último del mes
    (31-ene + 1 mes = 28/29-feb)."""
    if recurrencia == RECURRENCIA_DIARIA:
        return desde + datetime.timedelta(days=1)
    if recurrencia == RECURRENCIA_SEMANAL:
        return desde + datetime.timedelta(days=7)
    if recurrencia == RECURRENCIA_MENSUAL:
        anio = desde.year + (1 if desde.month == 12 else 0)
        mes = 1 if desde.month == 12 else desde.month + 1
        dia = min(desde.day, calendar.monthrange(anio, mes)[1])
        return datetime.date(anio, mes, dia)
    return None


def reabrir_si_recurrente(tarea):
    """Tras completar una tarea recurrente: vuelve a pendiente (y sus subtareas
    también) con el siguiente vencimiento. Devuelve True si se reabrió.

    La base del próximo vencimiento es la fecha de vencimiento anterior, salvo
    que ya haya pasado: en ese caso se cuenta desde hoy, para no arrastrar
    ciclos vencidos."""
    if not tarea.recurrencia:
        return False
    hoy = timezone.localdate()
    base = tarea.vence if (tarea.vence and tarea.vence >= hoy) else hoy
    tarea.ultima_completada = hoy
    tarea.vence = siguiente_vencimiento(base, tarea.recurrencia)
    tarea.estado = ESTADO_PENDIENTE
    tarea.save(update_fields=['estado', 'vence', 'ultima_completada'])
    tarea.subtareas.update(estado=ESTADO_PENDIENTE)
    return True


def ciclo_recurrente_vigente(tarea):
    """¿La tarea recurrente ya se cumplió en el ciclo actual? Vale hasta que
    toque el siguiente vencimiento (diaria: hoy; semanal: 7 días; etc.)."""
    if not tarea.recurrencia or not tarea.ultima_completada:
        return False
    proxima = siguiente_vencimiento(tarea.ultima_completada, tarea.recurrencia)
    return bool(proxima and proxima > timezone.localdate())


def tarea_cumplida_para_dependencia(tarea):
    """Completado visto por una dependencia: una recurrente cuenta como
    cumplida mientras su ciclo esté vigente, aunque ya haya vuelto a pendiente."""
    if tarea.recurrencia:
        return ciclo_recurrente_vigente(tarea)
    return tarea_completada(tarea)


# ----- Visibilidad y permisos -----
def objetivos_visibles(user):
    return Objetivo.objects.filter(
        Q(es_privada=False) | Q(dueno=user) | Q(miembros__usuario=user) |
        Q(tareas__responsable=user) | Q(tareas__subtareas__responsable=user)
    ).distinct()


def es_miembro(obj, user):
    if obj.dueno_id == user.id:
        return True
    if obj.miembros.filter(usuario=user).exists():
        return True
    if obj.tareas.filter(responsable=user).exists():
        return True
    return Subtarea.objects.filter(tarea__objetivo=obj, responsable=user).exists()


def puede_ver(obj, user):
    return (not obj.es_privada) or es_miembro(obj, user)


def puede_editar(obj, user):
    if obj.dueno_id == user.id:
        return True
    return obj.miembros.filter(usuario=user, permiso=PERMISO_EDITAR).exists()


def puede_completar(obj, user, responsable_id):
    return user.id == responsable_id or user.id == obj.dueno_id


def puede_eliminar(obj, user):
    return obj.dueno_id == user.id


# ----- Detección de ciclos (a nivel de objetivo) -----
def _objetivo_destino_id(dep):
    if dep.objetivo_destino_id:
        return dep.objetivo_destino_id
    if dep.tarea_destino_id:
        return dep.tarea_destino.objetivo_id
    if dep.subtarea_destino_id:
        return dep.subtarea_destino.tarea.objetivo_id
    return None


def crearia_ciclo(objetivo_origen_id, objetivo_destino_id):
    """¿Agregar una dependencia origen->destino (a nivel de objetivo) crea un ciclo?"""
    if not objetivo_destino_id or objetivo_origen_id == objetivo_destino_id:
        return False
    adj = {}
    deps = Dependencia.objects.select_related(
        'tarea_origen', 'tarea_destino__objetivo', 'subtarea_destino__tarea')
    for d in deps:
        src = d.tarea_origen.objetivo_id
        dst = _objetivo_destino_id(d)
        if dst and dst != src:
            adj.setdefault(src, set()).add(dst)
    adj.setdefault(objetivo_origen_id, set()).add(objetivo_destino_id)
    stack = [objetivo_destino_id]
    seen = set()
    while stack:
        cur = stack.pop()
        if cur == objetivo_origen_id:
            return True
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(adj.get(cur, ()))
    return False


# ----- Serialización del tablero para el front -----
def _serializar_dep(dep, visible_ids):
    if dep.objetivo_destino_id:
        ttype, tgt_obj = 'bubble', dep.objetivo_destino
        tbid = dep.objetivo_destino_id
        nombre = tgt_obj.titulo
        pct = pct_objetivo(tgt_obj)
    elif dep.tarea_destino_id:
        ttype = 'task'
        t = dep.tarea_destino
        tbid = t.objetivo_id
        nombre = t.titulo
        pct = 100 if tarea_completada(t) else 0
    else:
        ttype = 'subtask'
        s = dep.subtarea_destino
        tbid = s.tarea.objetivo_id
        nombre = s.titulo
        pct = 100 if s.estado == ESTADO_COMPLETADO else 0
    visible = tbid in visible_ids
    return {
        'depId': dep.id,
        'targetType': ttype,
        'blocking': dep.bloqueante,
        'targetBubbleId': oid(tbid) if visible else None,
        'privado': not visible,
        'pct': pct,
        'cumplida': dep_cumplida(dep),
        'nombre': nombre if visible else None,
    }


def _serializar_subtarea(s):
    return {
        'id': sid(s.id),
        'title': s.titulo,
        'assignee': uid(s.responsable_id) if s.responsable_id else None,
        'state': s.estado,
    }


def _serializar_tarea(t, visible_ids):
    return {
        'id': tid(t.id),
        'title': t.titulo,
        'assignee': uid(t.responsable_id) if t.responsable_id else None,
        'state': t.estado,
        'prio': t.prioridad,
        'due': t.vence.isoformat() if t.vence else '',
        'recur': t.recurrencia,
        'subtasks': [_serializar_subtarea(s) for s in t.subtareas.all()],
        'dependsOn': [_serializar_dep(d, visible_ids) for d in t.dependencias.all()],
    }


def _serializar_objetivo(o, visible_ids):
    return {
        'id': oid(o.id),
        'title': o.titulo,
        'ownerId': uid(o.dueno_id),
        'private': o.es_privada,
        'pos': ({'x': o.pos_x, 'y': o.pos_y} if o.pos_x is not None and o.pos_y is not None else None),
        'viewers': [{'uid': uid(m.usuario_id), 'perm': m.permiso} for m in o.miembros.all()],
        'tasks': [_serializar_tarea(t, visible_ids) for t in o.tareas.all()],
    }


def serializar_tablero(user):
    visibles = list(
        objetivos_visibles(user).prefetch_related(
            'miembros', 'tareas__subtareas', 'tareas__dependencias',
            'tareas__dependencias__objetivo_destino',
            'tareas__dependencias__tarea_destino__objetivo',
            'tareas__dependencias__subtarea_destino__tarea',
        )
    )
    visible_ids = set(o.id for o in visibles)
    objetivos = [_serializar_objetivo(o, visible_ids) for o in visibles]
    # Orden alfabético por el nombre que se muestra, no por username
    usuarios = sorted(
        ({'id': uid(u.id), 'nombre': u.get_full_name() or u.username}
         for u in User.objects.filter(is_active=True)),
        key=lambda x: x['nombre'].casefold(),
    )
    return {
        'usuarios': usuarios,
        'objetivos': objetivos,
        'version': version_actual(),
        'yo': uid(user.id),
    }
