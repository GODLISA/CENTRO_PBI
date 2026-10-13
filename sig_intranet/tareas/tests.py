"""
Tests de la API del módulo Tareas: visibilidad, permisos, ciclos, rollup,
versión y enmascarado de dependencias privadas. Usan force_login (sin
credenciales reales) y el cliente de test (exento de CSRF).
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from . import services
from .models import (
    Dependencia, Objetivo, Subtarea, Tarea,
    ESTADO_COMPLETADO, ESTADO_PENDIENTE,
)

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
