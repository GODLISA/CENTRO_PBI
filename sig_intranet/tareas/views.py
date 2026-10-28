"""
Vistas del módulo Tareas: la página del tablero y la API JSON.

La API sigue el envelope del resto del proyecto: {success, message, data}.
Toda regla de privacidad/permisos se valida AQUÍ (servidor), no se confía
en el front. Escrituras: @require_POST + CSRF (header X-CSRFToken) + atomic.
"""
import json

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_GET, require_POST

from . import services
from .models import (
    Dependencia, Objetivo, ObjetivoMiembro, Subtarea, Tarea,
    ESTADOS, PRIORIDADES, RECURRENCIAS, PERMISO_VER, PERMISO_EDITAR, ESTADO_COMPLETADO,
)

User = get_user_model()

_ESTADOS_VALIDOS = {c[0] for c in ESTADOS}
_PRIOS_VALIDAS = {c[0] for c in PRIORIDADES}
_RECURRENCIAS_VALIDAS = {c[0] for c in RECURRENCIAS}


# ----- Helpers de respuesta -----
def _ok(data=None):
    return JsonResponse({'success': True, 'data': data if data is not None else {}})


def _err(message, status=400):
    return JsonResponse({'success': False, 'message': message}, status=status)


def _body(request):
    try:
        return json.loads(request.body or b'{}')
    except (ValueError, TypeError):
        return {}


def _usuario(valor):
    """Usuario activo a partir de un id tipo 'u5' o número; None si no aplica."""
    if not valor:
        return None
    try:
        pk = services.parse_pk(valor)
    except (ValueError, TypeError):
        return None
    return User.objects.filter(pk=pk, is_active=True).first()


def _get(modelo, valor):
    try:
        return modelo.objects.filter(pk=services.parse_pk(valor)).first()
    except (ValueError, TypeError):
        return None


def _vence(valor):
    """Fecha de vencimiento validada. Devuelve (fecha_o_None, error_o_None)."""
    if not valor:
        return None, None
    fecha = parse_date(valor) if isinstance(valor, str) else valor
    if fecha is None:
        return None, 'Fecha de vencimiento inválida (formato AAAA-MM-DD).'
    return fecha, None


def _bump_ok(data=None):
    data = data or {}
    data['version'] = services.bump_version()
    return _ok(data)


# ============================================================
# Página
# ============================================================
@login_required
def tablero_view(request):
    """Página del tablero. El JS carga los datos desde la API."""
    return render(request, 'tareas/tablero.html')


# ============================================================
# API - lectura
# ============================================================
@login_required
@require_GET
def api_tablero(request):
    return _ok(services.serializar_tablero(request.user))


@login_required
@require_GET
def api_version(request):
    return _ok({'version': services.version_actual()})


# ============================================================
# API - Objetivos
# ============================================================
@login_required
@require_POST
def api_objetivo_crear(request):
    d = _body(request)
    titulo = (d.get('titulo') or '').strip()
    if not titulo:
        return _err('El título es obligatorio.')
    with transaction.atomic():
        obj = Objetivo.objects.create(
            titulo=titulo, dueno=request.user, es_privada=bool(d.get('es_privada')))
    return _bump_ok({'id': services.oid(obj.id)})


@login_required
@require_POST
def api_objetivo_actualizar(request, pk):
    obj = _get(Objetivo, pk)
    if not obj:
        return _err('Objetivo no encontrado.', 404)
    d = _body(request)
    with transaction.atomic():
        if 'titulo' in d:
            if not services.puede_editar(obj, request.user):
                return _err('Sin permiso de edición.', 403)
            titulo = (d.get('titulo') or '').strip()
            if not titulo:
                return _err('El título es obligatorio.')
            obj.titulo = titulo
        if 'es_privada' in d:
            if obj.dueno_id != request.user.id:
                return _err('Solo el dueño cambia la privacidad.', 403)
            obj.es_privada = bool(d.get('es_privada'))
        obj.save()
    return _bump_ok()


@login_required
@require_POST
def api_objetivo_posicion(request, pk):
    """Posición manual global. La puede mover cualquiera que vea el objetivo."""
    obj = _get(Objetivo, pk)
    if not obj:
        return _err('Objetivo no encontrado.', 404)
    if not services.puede_ver(obj, request.user):
        return _err('Sin acceso.', 403)
    d = _body(request)
    try:
        obj.pos_x = float(d.get('x'))
        obj.pos_y = float(d.get('y'))
    except (TypeError, ValueError):
        return _err('Coordenadas inválidas.')
    obj.save(update_fields=['pos_x', 'pos_y', 'actualizado_en'])
    # La posición no altera la "versión" del tablero para no forzar refetch a todos.
    return _ok()


@login_required
@require_POST
def api_objetivo_eliminar(request, pk):
    obj = _get(Objetivo, pk)
    if not obj:
        return _err('Objetivo no encontrado.', 404)
    if not services.puede_eliminar(obj, request.user):
        return _err('Solo el dueño puede eliminar.', 403)
    with transaction.atomic():
        obj.delete()
    return _bump_ok()


@login_required
@require_POST
def api_objetivo_completar(request, pk):
    obj = _get(Objetivo, pk)
    if not obj:
        return _err('Objetivo no encontrado.', 404)
    if obj.dueno_id != request.user.id:
        return _err('Solo el dueño puede marcar el objetivo completo.', 403)
    bloqueadas, reabiertas = 0, 0
    with transaction.atomic():
        for t in obj.tareas.all():
            # Misma regla que api_tarea_actualizar: una tarea bloqueada no se completa
            if services.tarea_bloqueada(t):
                bloqueadas += 1
                continue
            t.subtareas.update(estado=ESTADO_COMPLETADO)
            t.estado = ESTADO_COMPLETADO
            t.save(update_fields=['estado'])
            if services.reabrir_si_recurrente(t):
                reabiertas += 1
    return _bump_ok({'reabierta': reabiertas > 0, 'bloqueadas': bloqueadas})


@login_required
@require_POST
def api_objetivo_miembro(request, pk):
    obj = _get(Objetivo, pk)
    if not obj:
        return _err('Objetivo no encontrado.', 404)
    if not services.puede_editar(obj, request.user):
        return _err('Sin permiso de edición.', 403)
    d = _body(request)
    accion = d.get('accion')
    usuario = _usuario(d.get('usuario'))
    if not usuario:
        return _err('Usuario inválido.')
    if usuario.id == obj.dueno_id:
        return _err('El dueño ya es miembro.')
    with transaction.atomic():
        if accion == 'quitar':
            ObjetivoMiembro.objects.filter(objetivo=obj, usuario=usuario).delete()
        else:
            permiso = PERMISO_EDITAR if d.get('permiso') == PERMISO_EDITAR else PERMISO_VER
            ObjetivoMiembro.objects.update_or_create(
                objetivo=obj, usuario=usuario, defaults={'permiso': permiso})
    return _bump_ok()


@login_required
@require_POST
def api_objetivo_reordenar_tareas(request, pk):
    obj = _get(Objetivo, pk)
    if not obj:
        return _err('Objetivo no encontrado.', 404)
    if not services.puede_editar(obj, request.user):
        return _err('Sin permiso de edición.', 403)
    ids = _body(request).get('orden') or []
    with transaction.atomic():
        for i, tarea_id in enumerate(ids):
            Tarea.objects.filter(pk=services.parse_pk(tarea_id), objetivo=obj).update(orden=i)
    return _bump_ok()


# ============================================================
# API - Tareas
# ============================================================
@login_required
@require_POST
def api_tarea_crear(request, pk):
    obj = _get(Objetivo, pk)
    if not obj:
        return _err('Objetivo no encontrado.', 404)
    if not services.puede_editar(obj, request.user):
        return _err('Sin permiso de edición.', 403)
    d = _body(request)
    titulo = (d.get('titulo') or '').strip()
    if not titulo:
        return _err('El título es obligatorio.')
    prioridad = d.get('prioridad') if d.get('prioridad') in _PRIOS_VALIDAS else 'media'
    recurrencia = d.get('recurrencia') if d.get('recurrencia') in _RECURRENCIAS_VALIDAS else ''
    vence, error = _vence(d.get('vence'))
    if error:
        return _err(error)
    siguiente_orden = obj.tareas.count()
    with transaction.atomic():
        t = Tarea.objects.create(
            objetivo=obj, titulo=titulo, responsable=_usuario(d.get('responsable')),
            prioridad=prioridad, vence=vence,
            recurrencia=recurrencia, orden=siguiente_orden)
    return _bump_ok({'id': services.tid(t.id)})


@login_required
@require_POST
def api_tarea_actualizar(request, pk):
    t = _get(Tarea, pk)
    if not t:
        return _err('Tarea no encontrada.', 404)
    obj = t.objetivo
    d = _body(request)
    solo_estado = set(d.keys()) <= {'estado'}

    with transaction.atomic():
        if solo_estado and 'estado' in d:
            # Completar / descompletar: responsable o dueño
            if not services.puede_completar(obj, request.user, t.responsable_id):
                return _err('Solo el responsable o el dueño pueden completarla.', 403)
            if list(t.subtareas.all()):
                return _err('Esta tarea se completa al terminar sus subtareas.')
            if services.tarea_bloqueada(t):
                return _err('Tarea bloqueada por una dependencia pendiente.')
            nuevo = d.get('estado')
            if nuevo not in _ESTADOS_VALIDOS:
                return _err('Estado inválido.')
            t.estado = nuevo
            t.save(update_fields=['estado'])
            if nuevo == ESTADO_COMPLETADO and services.reabrir_si_recurrente(t):
                return _bump_ok({'reabierta': True})
        else:
            # Edición estructural: requiere permiso de edición
            if not services.puede_editar(obj, request.user):
                return _err('Sin permiso de edición.', 403)
            if 'titulo' in d:
                titulo = (d.get('titulo') or '').strip()
                if not titulo:
                    return _err('El título es obligatorio.')
                t.titulo = titulo
            if 'prioridad' in d:
                if d['prioridad'] not in _PRIOS_VALIDAS:
                    return _err('Prioridad inválida.')
                t.prioridad = d['prioridad']
            if 'vence' in d:
                vence, error = _vence(d.get('vence'))
                if error:
                    return _err(error)
                t.vence = vence
            if 'responsable' in d:
                t.responsable = _usuario(d.get('responsable'))
            if 'recurrencia' in d:
                if d['recurrencia'] not in _RECURRENCIAS_VALIDAS:
                    return _err('Recurrencia inválida.')
                t.recurrencia = d['recurrencia']
            if 'estado' in d and d['estado'] in _ESTADOS_VALIDOS and not list(t.subtareas.all()):
                t.estado = d['estado']
            t.save()
    return _bump_ok()


@login_required
@require_POST
def api_tarea_eliminar(request, pk):
    t = _get(Tarea, pk)
    if not t:
        return _err('Tarea no encontrada.', 404)
    if not services.puede_eliminar(t.objetivo, request.user):
        return _err('Solo el dueño puede eliminar.', 403)
    with transaction.atomic():
        t.delete()
    return _bump_ok()


@login_required
@require_POST
def api_tarea_reordenar_subtareas(request, pk):
    t = _get(Tarea, pk)
    if not t:
        return _err('Tarea no encontrada.', 404)
    if not services.puede_editar(t.objetivo, request.user):
        return _err('Sin permiso de edición.', 403)
    ids = _body(request).get('orden') or []
    with transaction.atomic():
        for i, sub_id in enumerate(ids):
            Subtarea.objects.filter(pk=services.parse_pk(sub_id), tarea=t).update(orden=i)
    return _bump_ok()


# ============================================================
# API - Subtareas
# ============================================================
@login_required
@require_POST
def api_subtarea_crear(request, pk):
    t = _get(Tarea, pk)
    if not t:
        return _err('Tarea no encontrada.', 404)
    if not services.puede_editar(t.objetivo, request.user):
        return _err('Sin permiso de edición.', 403)
    d = _body(request)
    titulo = (d.get('titulo') or '').strip()
    if not titulo:
        return _err('El título es obligatorio.')
    siguiente = t.subtareas.count()
    with transaction.atomic():
        s = Subtarea.objects.create(
            tarea=t, titulo=titulo, responsable=_usuario(d.get('responsable')), orden=siguiente)
        services.recalcular_estado_tarea(t)
    return _bump_ok({'id': services.sid(s.id)})


@login_required
@require_POST
def api_subtarea_actualizar(request, pk):
    s = _get(Subtarea, pk)
    if not s:
        return _err('Subtarea no encontrada.', 404)
    obj = s.tarea.objetivo
    d = _body(request)
    solo_estado = set(d.keys()) <= {'estado'}
    with transaction.atomic():
        if solo_estado and 'estado' in d:
            if not services.puede_completar(obj, request.user, s.responsable_id):
                return _err('Solo el responsable o el dueño pueden completarla.', 403)
            if d['estado'] not in _ESTADOS_VALIDOS:
                return _err('Estado inválido.')
            s.estado = d['estado']
            s.save(update_fields=['estado'])
            if services.recalcular_estado_tarea(s.tarea) and services.reabrir_si_recurrente(s.tarea):
                return _bump_ok({'reabierta': True})
        else:
            if not services.puede_editar(obj, request.user):
                return _err('Sin permiso de edición.', 403)
            if 'titulo' in d:
                titulo = (d.get('titulo') or '').strip()
                if not titulo:
                    return _err('El título es obligatorio.')
                s.titulo = titulo
            if 'responsable' in d:
                s.responsable = _usuario(d.get('responsable'))
            s.save()
    return _bump_ok()


@login_required
@require_POST
def api_subtarea_eliminar(request, pk):
    s = _get(Subtarea, pk)
    if not s:
        return _err('Subtarea no encontrada.', 404)
    if not services.puede_eliminar(s.tarea.objetivo, request.user):
        return _err('Solo el dueño puede eliminar.', 403)
    tarea = s.tarea
    with transaction.atomic():
        s.delete()
        services.recalcular_estado_tarea(tarea)
    return _bump_ok()


# ============================================================
# API - Dependencias
# ============================================================
@login_required
@require_POST
def api_dependencia_crear(request, pk):
    t = _get(Tarea, pk)
    if not t:
        return _err('Tarea no encontrada.', 404)
    if not services.puede_editar(t.objetivo, request.user):
        return _err('Sin permiso de edición.', 403)
    d = _body(request)
    tipo = d.get('targetType')
    destino_id = services.parse_pk(d.get('targetId')) if d.get('targetId') else None
    bloqueante = bool(d.get('blocking'))
    if not destino_id or tipo not in ('bubble', 'task', 'subtask'):
        return _err('Destino inválido.')

    campos = {'objetivo_destino': None, 'tarea_destino': None, 'subtarea_destino': None}
    objetivo_destino_id = None
    if tipo == 'bubble':
        dest = Objetivo.objects.filter(pk=destino_id).first()
        if not dest:
            return _err('Objetivo destino no encontrado.', 404)
        campos['objetivo_destino'] = dest
        objetivo_destino_id = dest.id
    elif tipo == 'task':
        dest = Tarea.objects.filter(pk=destino_id).first()
        if not dest:
            return _err('Tarea destino no encontrada.', 404)
        if dest.id == t.id:
            return _err('Una tarea no puede depender de sí misma.')
        campos['tarea_destino'] = dest
        objetivo_destino_id = dest.objetivo_id
    else:
        dest = Subtarea.objects.filter(pk=destino_id).first()
        if not dest:
            return _err('Subtarea destino no encontrada.', 404)
        campos['subtarea_destino'] = dest
        objetivo_destino_id = dest.tarea.objetivo_id

    if services.crearia_ciclo(t.objetivo_id, objetivo_destino_id):
        return _err('Esa dependencia crearía un ciclo (A→B→A). No permitido.')

    with transaction.atomic():
        Dependencia.objects.create(tarea_origen=t, bloqueante=bloqueante, **campos)
    return _bump_ok()


@login_required
@require_POST
def api_dependencia_eliminar(request, pk):
    dep = _get(Dependencia, pk)
    if not dep:
        return _err('Dependencia no encontrada.', 404)
    if not services.puede_editar(dep.tarea_origen.objetivo, request.user):
        return _err('Sin permiso de edición.', 403)
    with transaction.atomic():
        dep.delete()
    return _bump_ok()
