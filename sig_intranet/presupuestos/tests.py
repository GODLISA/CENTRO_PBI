from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from . import services
from .models import (
    AreaServicio, Comuna, ItemMatriz, Parametro, Presupuesto, ValorParametro, Zona,
)
from .pdf import generar_pdf_presupuesto


def cargar_valor(codigo, valor, vigente_desde, zona=None):
    parametro = Parametro.objects.get(codigo=codigo)
    return ValorParametro.objects.create(
        parametro=parametro, valor=Decimal(str(valor)),
        vigente_desde=vigente_desde, zona=zona,
    )


class BaseDatos(TestCase):
    """Datos comunes: área con matriz, zonas y parámetros vigentes."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('tester', password='x')
        cls.area = AreaServicio.objects.create(nombre='Higiene Ocupacional')
        cls.zona_norte = Zona.objects.create(nombre='Norte')
        cls.zona_sur = Zona.objects.create(nombre='Sur')

        cls.item_clp = ItemMatriz.objects.create(
            area=cls.area, concepto='Medición de ruido', unidad='punto',
            moneda='CLP', precio_unitario=Decimal('50000'),
        )
        cls.item_uf = ItemMatriz.objects.create(
            area=cls.area, concepto='Informe técnico', unidad='informe',
            moneda='UF', precio_unitario=Decimal('2.5'),
        )

        cargar_valor('UF', '38000', date(2026, 1, 1))
        cargar_valor('USD', '900', date(2026, 1, 1))
        cargar_valor('VALOR_KM', '800', date(2026, 1, 1))                     # global
        cargar_valor('VALOR_KM', '1000', date(2026, 1, 1), zona=cls.zona_sur)  # zona sur

    def crear_presupuesto(self, **kwargs):
        defaults = dict(
            cliente_nombre='Cliente Prueba', area=self.area,
            creado_por=self.user, fecha_emision=date(2026, 6, 12),
        )
        defaults.update(kwargs)
        return Presupuesto.objects.create(**defaults)


class ParametrosTests(BaseDatos):
    def test_valor_vigente_por_fecha_toma_el_ultimo(self):
        cargar_valor('UF', '39000', date(2026, 6, 1))
        valor, _ = services.valor_parametro('UF', fecha=date(2026, 6, 12))
        self.assertEqual(valor, Decimal('39000'))

    def test_valor_historico_se_mantiene(self):
        cargar_valor('UF', '39000', date(2026, 6, 1))
        valor, _ = services.valor_parametro('UF', fecha=date(2026, 3, 1))
        self.assertEqual(valor, Decimal('38000'))

    def test_valor_por_zona_con_fallback_global(self):
        valor_sur, _ = services.valor_parametro('VALOR_KM', zona=self.zona_sur)
        valor_norte, _ = services.valor_parametro('VALOR_KM', zona=self.zona_norte)
        self.assertEqual(valor_sur, Decimal('1000'))   # valor específico de la zona
        self.assertEqual(valor_norte, Decimal('800'))  # cae al global

    def test_error_claro_si_no_hay_valor(self):
        ValorParametro.objects.filter(parametro__codigo='UF').delete()
        with self.assertRaises(ValidationError):
            services.valor_parametro('UF')


class CalculoPresupuestoTests(BaseDatos):
    def test_calculo_completo_con_uf_y_traslado(self):
        presupuesto = self.crear_presupuesto(
            zona=self.zona_sur, distancia_km=Decimal('50'),
        )
        services.calcular_presupuesto(presupuesto, [
            {'item_id': self.item_clp.pk, 'cantidad': '2'},   # 2 x 50.000 = 100.000
            {'item_id': self.item_uf.pk, 'cantidad': '1'},    # 2.5 UF x 38.000 = 95.000
        ])
        presupuesto.refresh_from_db()

        # traslado: 50 km x 1.000 (zona sur) = 50.000
        self.assertEqual(presupuesto.costo_traslado, Decimal('50000'))
        self.assertEqual(presupuesto.subtotal, Decimal('245000'))
        self.assertEqual(presupuesto.monto_iva, Decimal('46550'))   # 19%
        self.assertEqual(presupuesto.total, Decimal('291550'))
        # snapshots
        self.assertEqual(presupuesto.valor_uf, Decimal('38000'))
        self.assertEqual(presupuesto.valor_km, Decimal('1000'))
        self.assertEqual(presupuesto.detalles.count(), 2)

    def test_snapshot_no_cambia_si_se_edita_la_matriz(self):
        presupuesto = self.crear_presupuesto()
        services.calcular_presupuesto(
            presupuesto, [{'item_id': self.item_clp.pk, 'cantidad': '1'}]
        )
        total_original = presupuesto.total

        # Editar la matriz a futuro no debe alterar el presupuesto emitido
        self.item_clp.precio_unitario = Decimal('99999')
        self.item_clp.save()
        presupuesto.refresh_from_db()
        self.assertEqual(presupuesto.total, total_original)
        detalle = presupuesto.detalles.first()
        self.assertEqual(detalle.precio_unitario, Decimal('50000'))

    def test_linea_manual(self):
        presupuesto = self.crear_presupuesto()
        services.calcular_presupuesto(presupuesto, [{
            'item_id': None, 'concepto': 'Servicio especial',
            'cantidad': '3', 'precio_unitario': '10000', 'moneda': 'CLP',
        }])
        presupuesto.refresh_from_db()
        self.assertEqual(presupuesto.subtotal, Decimal('30000'))

    def test_item_de_otra_area_es_rechazado(self):
        otra_area = AreaServicio.objects.create(nombre='Otra')
        presupuesto = self.crear_presupuesto(area=otra_area)
        with self.assertRaises(ValidationError):
            services.calcular_presupuesto(
                presupuesto, [{'item_id': self.item_clp.pk, 'cantidad': '1'}]
            )

    def test_sin_lineas_es_rechazado(self):
        presupuesto = self.crear_presupuesto()
        with self.assertRaises(ValidationError):
            services.calcular_presupuesto(presupuesto, [])

    def test_correlativo_anual(self):
        p1 = self.crear_presupuesto()
        p2 = self.crear_presupuesto()
        anio = date.today().year
        self.assertEqual(p1.numero, f'P-{anio}-0001')
        self.assertEqual(p2.numero, f'P-{anio}-0002')


class CargarMatrizTests(TestCase):
    """Verifica la carga de la matriz extraída del Excel."""

    def test_carga_idempotente(self):
        call_command('cargar_matriz', verbosity=0)
        zonas = Zona.objects.count()
        comunas = Comuna.objects.count()
        items = ItemMatriz.objects.count()

        self.assertEqual(zonas, 3)
        self.assertGreater(comunas, 100)
        self.assertGreater(items, 200)

        # Valores conocidos de la matriz
        rancagua = Comuna.objects.get(nombre='Rancagua')
        self.assertEqual(rancagua.km_ida_regreso, Decimal('174'))
        self.assertEqual(rancagua.zona.nombre, 'Sur')

        valor_km, _ = services.valor_parametro('VALOR_KM')
        self.assertEqual(valor_km, Decimal('300'))

        # Segunda ejecución no duplica
        call_command('cargar_matriz', verbosity=0)
        self.assertEqual(Comuna.objects.count(), comunas)
        self.assertEqual(ItemMatriz.objects.count(), items)


class PdfTests(BaseDatos):
    def test_genera_pdf_valido(self):
        presupuesto = self.crear_presupuesto(zona=self.zona_sur, distancia_km=Decimal('10'))
        services.calcular_presupuesto(
            presupuesto, [{'item_id': self.item_uf.pk, 'cantidad': '1'}]
        )
        contenido = generar_pdf_presupuesto(presupuesto)
        self.assertTrue(contenido.startswith(b'%PDF'))
        self.assertGreater(len(contenido), 1000)

    def test_snapshot_usd_referencial(self):
        presupuesto = self.crear_presupuesto()
        services.calcular_presupuesto(
            presupuesto, [{'item_id': self.item_clp.pk, 'cantidad': '1'}]
        )
        presupuesto.refresh_from_db()
        self.assertEqual(presupuesto.valor_usd, Decimal('900'))

    def test_pdf_funciona_sin_usd(self):
        # Si el dólar no está cargado, el cálculo y el PDF no fallan
        ValorParametro.objects.filter(parametro__codigo='USD').delete()
        presupuesto = self.crear_presupuesto()
        services.calcular_presupuesto(
            presupuesto, [{'item_id': self.item_clp.pk, 'cantidad': '1'}]
        )
        presupuesto.refresh_from_db()
        self.assertIsNone(presupuesto.valor_usd)
        self.assertTrue(generar_pdf_presupuesto(presupuesto).startswith(b'%PDF'))


class VistasTests(BaseDatos):
    def setUp(self):
        self.client.login(username='tester', password='x')

    def test_flujo_crear_presupuesto_via_post(self):
        respuesta = self.client.post(reverse('presupuesto_nuevo'), {
            'cliente_nombre': 'ACME Ltda.',
            'area': self.area.pk,
            'zona': self.zona_sur.pk,
            'distancia_km': '20',
            'validez_dias': '30',
            'lineas_json': f'[{{"item_id": {self.item_clp.pk}, "cantidad": "1"}}]',
        })
        self.assertEqual(respuesta.status_code, 302)
        presupuesto = Presupuesto.objects.get(cliente_nombre='ACME Ltda.')
        self.assertEqual(presupuesto.costo_traslado, Decimal('20000'))  # 20 km x 1000

    def test_api_items_area(self):
        respuesta = self.client.get(
            reverse('presupuestos_api_items', args=[self.area.pk])
        )
        data = respuesta.json()
        self.assertEqual(len(data['items']), 2)
        self.assertEqual(data['parametros']['UF'], '38000.0000')
        self.assertEqual(data['valores_km'][str(self.zona_sur.pk)], '1000.0000')

    def test_pdf_view(self):
        presupuesto = self.crear_presupuesto()
        services.calcular_presupuesto(
            presupuesto, [{'item_id': self.item_clp.pk, 'cantidad': '1'}]
        )
        respuesta = self.client.get(reverse('presupuesto_pdf', args=[presupuesto.pk]))
        self.assertEqual(respuesta['Content-Type'], 'application/pdf')

    def test_paginas_renderizan(self):
        presupuesto = self.crear_presupuesto()
        services.calcular_presupuesto(
            presupuesto, [{'item_id': self.item_clp.pk, 'cantidad': '1'}]
        )
        for url in (
            reverse('presupuestos_lista'),
            reverse('presupuesto_nuevo'),
            reverse('presupuesto_detalle', args=[presupuesto.pk]),
        ):
            respuesta = self.client.get(url)
            self.assertEqual(respuesta.status_code, 200, url)

    def test_api_comunas_zona(self):
        comuna = Comuna.objects.create(
            zona=self.zona_sur, nombre='Rancagua', region="O'Higgins",
            km_ida_regreso=Decimal('174'),
        )
        respuesta = self.client.get(
            reverse('presupuestos_api_comunas', args=[self.zona_sur.pk])
        )
        data = respuesta.json()
        self.assertEqual(data['comunas'][0]['nombre'], 'Rancagua')
        self.assertEqual(data['comunas'][0]['km'], '174.0')

        # La comuna se guarda en el presupuesto creado vía POST
        respuesta = self.client.post(reverse('presupuesto_nuevo'), {
            'cliente_nombre': 'Cliente Comuna',
            'area': self.area.pk,
            'zona': self.zona_sur.pk,
            'comuna': comuna.pk,
            'distancia_km': '174',
            'validez_dias': '30',
            'lineas_json': f'[{{"item_id": {self.item_clp.pk}, "cantidad": "1"}}]',
        })
        self.assertEqual(respuesta.status_code, 302)
        presupuesto = Presupuesto.objects.get(cliente_nombre='Cliente Comuna')
        self.assertEqual(presupuesto.comuna, comuna)
        self.assertEqual(presupuesto.costo_traslado, Decimal('174000'))  # 174 x 1000

    def test_requiere_login(self):
        self.client.logout()
        respuesta = self.client.get(reverse('presupuestos_lista'))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn('/login/', respuesta.url)
