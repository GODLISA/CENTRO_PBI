"""
Tests de la API del módulo Tareas: visibilidad, permisos, ciclos, rollup,
versión y enmascarado de dependencias privadas. Usan force_login (sin
credenciales reales) y el cliente de test (exento de CSRF).
"""
import datetime
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import services
from .models import (
    Dependencia, Objetivo, PreferenciaUsuario, Subtarea, Tarea,
    ESTADO_COMPLETADO, ESTADO_PENDIENTE,
)
from django.utils.dateparse import parse_date  # noqa: F401  (usado en los tests de validación)

User = get_user_model()


def _json(resp):
    return json.loads(resp.content)


class TareasAPITests(TestCase):
    def setUp(self):
        self.dueno = User.objects.create_user('dueno', password='x')
        self.otro = User.objects.create_user('otro', password='x')
        self.resp = User.objects.create_user('resp', password='x')

    def post(self, name, args=None, body=None):
        url = reverse(name, args=args or [])
        return self.client.post(url, data=json.dumps(body or {}), content_type='application/json')

    # ---- Visibilidad ----
    def test_privado_oculto_a_no_miembro(self):
        priv = Objetivo.objects.create(titulo='Privado', dueno=self.dueno, es_privada=True)
        Tarea.objects.create(objetivo=priv, titulo='T', responsable=self.dueno)

        self.client.force_login(self.otro)
        data = _json(self.client.get(reverse('tareas_api_tablero')))['data']
        titulos = [o['title'] for o in data['objetivos']]
        self.assertNotIn('Privado', titulos)

        self.client.force_login(self.dueno)
        data = _json(self.client.get(reverse('tareas_api_tablero')))['data']
        titulos = [o['title'] for o in data['objetivos']]
        self.assertIn('Privado', titulos)

    def test_responsable_ve_su_objetivo_privado(self):
        priv = Objetivo.objects.create(titulo='Privado', dueno=self.dueno, es_privada=True)
        Tarea.objects.create(objetivo=priv, titulo='T', responsable=self.resp)
        self.client.force_login(self.resp)
        data = _json(self.client.get(reverse('tareas_api_tablero')))['data']
        self.assertIn('Privado', [o['title'] for o in data['objetivos']])

    # ---- Permisos ----
    def test_no_dueno_no_elimina(self):
        obj = Objetivo.objects.create(titulo='Pub', dueno=self.dueno)
        self.client.force_login(self.otro)
        resp = self.post('tareas_objetivo_eliminar', args=[obj.id])
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(Objetivo.objects.filter(pk=obj.id).exists())

    def test_no_responsable_no_completa(self):
        obj = Objetivo.objects.create(titulo='Pub', dueno=self.dueno)
        t = Tarea.objects.create(objetivo=obj, titulo='T', responsable=self.resp)
        self.client.force_login(self.otro)
        resp = self.post('tareas_tarea_actualizar', args=[t.id], body={'estado': ESTADO_COMPLETADO})
        self.assertEqual(resp.status_code, 403)
        t.refresh_from_db()
        self.assertEqual(t.estado, ESTADO_PENDIENTE)

    def test_responsable_si_completa(self):
        obj = Objetivo.objects.create(titulo='Pub', dueno=self.dueno)
        t = Tarea.objects.create(objetivo=obj, titulo='T', responsable=self.resp)
        self.client.force_login(self.resp)
        resp = self.post('tareas_tarea_actualizar', args=[t.id], body={'estado': ESTADO_COMPLETADO})
        self.assertEqual(resp.status_code, 200)
        t.refresh_from_db()
        self.assertEqual(t.estado, ESTADO_COMPLETADO)

    # ---- Rollup ----
    def test_rollup_subtareas(self):
        obj = Objetivo.objects.create(titulo='Pub', dueno=self.dueno)
        t = Tarea.objects.create(objetivo=obj, titulo='T', responsable=self.dueno)
        s1 = Subtarea.objects.create(tarea=t, titulo='s1', responsable=self.dueno)
        s2 = Subtarea.objects.create(tarea=t, titulo='s2', responsable=self.dueno)
        self.client.force_login(self.dueno)
        self.post('tareas_subtarea_actualizar', args=[s1.id], body={'estado': ESTADO_COMPLETADO})
        t.refresh_from_db()
        self.assertNotEqual(t.estado, ESTADO_COMPLETADO)  # aún falta s2
        self.post('tareas_subtarea_actualizar', args=[s2.id], body={'estado': ESTADO_COMPLETADO})
        t.refresh_from_db()
        self.assertEqual(t.estado, ESTADO_COMPLETADO)  # rollup

    # ---- Ciclos ----
    def test_ciclo_rechazado(self):
        b1 = Objetivo.objects.create(titulo='B1', dueno=self.dueno)
        b2 = Objetivo.objects.create(titulo='B2', dueno=self.dueno)
        ta = Tarea.objects.create(objetivo=b1, titulo='ta', responsable=self.dueno)
        tb = Tarea.objects.create(objetivo=b2, titulo='tb', responsable=self.dueno)
        self.client.force_login(self.dueno)
        r1 = self.post('tareas_dependencia_crear', args=[ta.id],
                       body={'targetType': 'bubble', 'targetId': services.oid(b2.id)})
        self.assertEqual(r1.status_code, 200)
        r2 = self.post('tareas_dependencia_crear', args=[tb.id],
                       body={'targetType': 'bubble', 'targetId': services.oid(b1.id)})
        self.assertEqual(r2.status_code, 400)
        self.assertFalse(_json(r2)['success'])

    # ---- Versión ----
    def test_version_incrementa(self):
        self.client.force_login(self.dueno)
        v0 = _json(self.client.get(reverse('tareas_api_version')))['data']['version']
        self.post('tareas_objetivo_crear', body={'titulo': 'Nuevo'})
        v1 = _json(self.client.get(reverse('tareas_api_version')))['data']['version']
        self.assertEqual(v1, v0 + 1)

    # ---- Enmascarado de dependencia privada ----
    def test_dep_privada_enmascarada(self):
        # Objetivo público cuya tarea depende de una tarea en objetivo privado ajeno
        priv = Objetivo.objects.create(titulo='Privado', dueno=self.dueno, es_privada=True)
        t_priv = Tarea.objects.create(objetivo=priv, titulo='Secreta', responsable=self.dueno)
        pub = Objetivo.objects.create(titulo='Pub', dueno=self.otro)
        t_pub = Tarea.objects.create(objetivo=pub, titulo='Visible', responsable=self.otro)
        Dependencia.objects.create(tarea_origen=t_pub, tarea_destino=t_priv, bloqueante=False)

        self.client.force_login(self.otro)
        data = _json(self.client.get(reverse('tareas_api_tablero')))['data']
        self.assertNotIn('Privado', [o['title'] for o in data['objetivos']])
        pub_ser = next(o for o in data['objetivos'] if o['title'] == 'Pub')
        dep = pub_ser['tasks'][0]['dependsOn'][0]
        self.assertTrue(dep['privado'])
        self.assertIsNone(dep['nombre'])
        self.assertIsNone(dep['targetBubbleId'])
        self.assertIn('pct', dep)  # el % sí se expone (por diseño)


class RecurrenciaTests(TestCase):
    """Tarea recurrente: al completarla vuelve a pendiente con el siguiente
    vencimiento (ver services.reabrir_si_recurrente)."""

    def setUp(self):
        self.dueno = User.objects.create_user('dueno_rec', password='x')
        self.objetivo = Objetivo.objects.create(titulo='Mantención', dueno=self.dueno)

    def test_siguiente_vencimiento(self):
        d = datetime.date(2026, 1, 31)
        self.assertEqual(services.siguiente_vencimiento(d, 'diaria'), datetime.date(2026, 2, 1))
        self.assertEqual(services.siguiente_vencimiento(d, 'semanal'), datetime.date(2026, 2, 7))
        # 31-ene no existe en febrero: se recorta al último día del mes
        self.assertEqual(services.siguiente_vencimiento(d, 'mensual'), datetime.date(2026, 2, 28))
        self.assertIsNone(services.siguiente_vencimiento(d, ''))

    def test_completar_recurrente_la_reabre(self):
        vence = timezone.localdate() + datetime.timedelta(days=3)
        t = Tarea.objects.create(
            objetivo=self.objetivo, titulo='Revisar bombas', responsable=self.dueno,
            vence=vence, recurrencia='semanal')
        self.client.force_login(self.dueno)
        self.client.post(
            reverse('tareas_tarea_actualizar', args=[t.id]),
            data=json.dumps({'estado': ESTADO_COMPLETADO}),
            content_type='application/json')
        t.refresh_from_db()
        self.assertEqual(t.estado, ESTADO_PENDIENTE)
        self.assertEqual(t.vence, vence + datetime.timedelta(days=7))

    def test_completar_no_recurrente_queda_completada(self):
        t = Tarea.objects.create(
            objetivo=self.objetivo, titulo='Tarea normal', responsable=self.dueno)
        self.client.force_login(self.dueno)
        self.client.post(
            reverse('tareas_tarea_actualizar', args=[t.id]),
            data=json.dumps({'estado': ESTADO_COMPLETADO}),
            content_type='application/json')
        t.refresh_from_db()
        self.assertEqual(t.estado, ESTADO_COMPLETADO)

    def test_subtareas_vuelven_a_pendiente(self):
        t = Tarea.objects.create(
            objetivo=self.objetivo, titulo='Ronda diaria', responsable=self.dueno,
            recurrencia='diaria')
        s1 = Subtarea.objects.create(tarea=t, titulo='Piso 1', responsable=self.dueno)
        s2 = Subtarea.objects.create(tarea=t, titulo='Piso 2', responsable=self.dueno)
        self.client.force_login(self.dueno)
        for s in (s1, s2):
            self.client.post(
                reverse('tareas_subtarea_actualizar', args=[s.id]),
                data=json.dumps({'estado': ESTADO_COMPLETADO}),
                content_type='application/json')
        t.refresh_from_db()
        s1.refresh_from_db()
        s2.refresh_from_db()
        self.assertEqual(t.estado, ESTADO_PENDIENTE)
        self.assertEqual(s1.estado, ESTADO_PENDIENTE)
        self.assertEqual(s2.estado, ESTADO_PENDIENTE)
        self.assertEqual(t.vence, timezone.localdate() + datetime.timedelta(days=1))


class UsuariosOrdenTests(TestCase):
    """Los usuarios del tablero salen en orden alfabético por nombre visible."""

    def test_orden_alfabetico(self):
        User.objects.create_user('zulema', password='x', first_name='Ana', last_name='Zu')
        User.objects.create_user('ana', password='x', first_name='Carlos', last_name='Be')
        yo = User.objects.create_user('beto', password='x')
        nombres = [u['nombre'] for u in services.serializar_tablero(yo)['usuarios']]
        self.assertEqual(nombres, sorted(nombres, key=str.casefold))
        self.assertEqual(nombres[0], 'Ana Zu')


class RecurrenciaDependenciasTests(TestCase):
    """Una dependencia bloqueante hacia una recurrente se cumple mientras el
    ciclo esté vigente; si no, la recurrente bloquearía para siempre."""

    def setUp(self):
        self.dueno = User.objects.create_user('dueno_dep', password='x')
        self.objetivo = Objetivo.objects.create(titulo='Planta', dueno=self.dueno)
        self.recurrente = Tarea.objects.create(
            objetivo=self.objetivo, titulo='Ronda diaria', responsable=self.dueno,
            recurrencia='diaria')
        self.dependiente = Tarea.objects.create(
            objetivo=self.objetivo, titulo='Informe', responsable=self.dueno)
        Dependencia.objects.create(
            tarea_origen=self.dependiente, tarea_destino=self.recurrente, bloqueante=True)
        self.client.force_login(self.dueno)

    def _completar(self, tarea):
        return self.client.post(
            reverse('tareas_tarea_actualizar', args=[tarea.id]),
            data=json.dumps({'estado': ESTADO_COMPLETADO}),
            content_type='application/json')

    def test_bloquea_antes_de_completar(self):
        self.assertTrue(services.tarea_bloqueada(self.dependiente))

    def test_desbloquea_tras_completar_la_recurrente(self):
        resp = self._completar(self.recurrente)
        self.assertTrue(_json(resp)['data']['reabierta'])
        self.recurrente.refresh_from_db()
        self.assertEqual(self.recurrente.estado, ESTADO_PENDIENTE)
        self.assertEqual(self.recurrente.ultima_completada, timezone.localdate())
        self.dependiente.refresh_from_db()
        self.assertFalse(services.tarea_bloqueada(self.dependiente))
        self.assertEqual(_json(self._completar(self.dependiente)).get('success'), True)

    def test_ciclo_vencido_vuelve_a_bloquear(self):
        self.recurrente.ultima_completada = timezone.localdate() - datetime.timedelta(days=2)
        self.recurrente.save(update_fields=['ultima_completada'])
        self.assertFalse(services.ciclo_recurrente_vigente(self.recurrente))
        self.assertTrue(services.tarea_bloqueada(self.dependiente))


class RollupSinReaperturaTests(TestCase):
    """Borrar o agregar subtareas recalcula el estado, pero NO reabre el ciclo:
    si lo hiciera, se perdería el avance ya registrado."""

    def setUp(self):
        self.dueno = User.objects.create_user('dueno_roll', password='x')
        self.objetivo = Objetivo.objects.create(titulo='Bodega', dueno=self.dueno)
        self.tarea = Tarea.objects.create(
            objetivo=self.objetivo, titulo='Inventario', responsable=self.dueno,
            recurrencia='diaria')
        self.s1 = Subtarea.objects.create(tarea=self.tarea, titulo='Pasillo 1', responsable=self.dueno)
        self.s2 = Subtarea.objects.create(tarea=self.tarea, titulo='Pasillo 2', responsable=self.dueno)
        self.client.force_login(self.dueno)

    def test_borrar_hermana_no_resetea_la_completada(self):
        self.client.post(
            reverse('tareas_subtarea_actualizar', args=[self.s1.id]),
            data=json.dumps({'estado': ESTADO_COMPLETADO}),
            content_type='application/json')
        self.client.post(reverse('tareas_subtarea_eliminar', args=[self.s2.id]))
        self.s1.refresh_from_db()
        self.assertEqual(self.s1.estado, ESTADO_COMPLETADO)


class ObjetivoCompletarTests(TestCase):
    """api_objetivo_completar respeta los bloqueos y reabre las recurrentes."""

    def setUp(self):
        self.dueno = User.objects.create_user('dueno_obj', password='x')
        self.objetivo = Objetivo.objects.create(titulo='Cierre mes', dueno=self.dueno)
        self.otro = Objetivo.objects.create(titulo='Previo', dueno=self.dueno)
        self.previa = Tarea.objects.create(objetivo=self.otro, titulo='Previa', responsable=self.dueno)
        self.bloqueada = Tarea.objects.create(
            objetivo=self.objetivo, titulo='Bloqueada', responsable=self.dueno)
        Dependencia.objects.create(
            tarea_origen=self.bloqueada, tarea_destino=self.previa, bloqueante=True)
        self.recurrente = Tarea.objects.create(
            objetivo=self.objetivo, titulo='Semanal', responsable=self.dueno, recurrencia='semanal')
        self.client.force_login(self.dueno)

    def test_salta_bloqueadas_y_reabre_recurrentes(self):
        resp = self.client.post(reverse('tareas_objetivo_completar', args=[self.objetivo.id]))
        data = _json(resp)['data']
        self.assertEqual(data['bloqueadas'], 1)
        self.assertTrue(data['reabierta'])
        self.bloqueada.refresh_from_db()
        self.recurrente.refresh_from_db()
        self.assertEqual(self.bloqueada.estado, ESTADO_PENDIENTE)
        self.assertEqual(self.recurrente.estado, ESTADO_PENDIENTE)
        self.assertEqual(self.recurrente.ultima_completada, timezone.localdate())


class ValidacionEntradaTests(TestCase):
    """La API responde 400 con el envelope, no 500, ante entradas inválidas."""

    def setUp(self):
        self.dueno = User.objects.create_user('dueno_val', password='x')
        self.objetivo = Objetivo.objects.create(titulo='Val', dueno=self.dueno)
        self.client.force_login(self.dueno)

    def test_vence_invalido(self):
        resp = self.client.post(
            reverse('tareas_tarea_crear', args=[self.objetivo.id]),
            data=json.dumps({'titulo': 'X', 'vence': 'no-es-fecha'}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(_json(resp)['success'])

    def test_recurrencia_invalida(self):
        t = Tarea.objects.create(objetivo=self.objetivo, titulo='T', recurrencia='semanal')
        resp = self.client.post(
            reverse('tareas_tarea_actualizar', args=[t.id]),
            data=json.dumps({'titulo': 'T', 'recurrencia': 'anual'}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        t.refresh_from_db()
        self.assertEqual(t.recurrencia, 'semanal')


class ColorUsuarioTests(TestCase):
    """Color propio: se guarda, se valida y viaja en el tablero."""

    def setUp(self):
        self.user = User.objects.create_user('coloreado', password='x')
        self.client.force_login(self.user)

    def post(self, body):
        return self.client.post(
            reverse('tareas_mi_color'),
            data=json.dumps(body), content_type='application/json')

    def test_guarda_y_normaliza(self):
        resp = self.post({'color': '#AABBCC'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            PreferenciaUsuario.objects.get(usuario=self.user).color, '#aabbcc')

    def test_rechaza_formato_invalido(self):
        self.assertEqual(self.post({'color': 'rojo'}).status_code, 400)
        self.assertEqual(self.post({'color': '#12345'}).status_code, 400)
        self.assertFalse(PreferenciaUsuario.objects.exists())

    def test_vacio_borra_el_color(self):
        self.post({'color': '#112233'})
        self.post({'color': ''})
        self.assertEqual(
            PreferenciaUsuario.objects.get(usuario=self.user).color, '')

    def test_viaja_en_el_tablero(self):
        self.post({'color': '#102030'})
        datos = services.serializar_tablero(self.user)
        mio = [u for u in datos['usuarios'] if u['id'] == services.uid(self.user.id)][0]
        self.assertEqual(mio['color'], '#102030')

    def test_sin_preferencia_devuelve_vacio(self):
        datos = services.serializar_tablero(self.user)
        self.assertEqual(datos['usuarios'][0]['color'], '')
