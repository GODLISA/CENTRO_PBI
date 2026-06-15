"""
Modelos del módulo de Presupuestos.

Diseño orientado a mantenibilidad:
- Las matrices de cobro (ItemMatriz) se editan desde el admin, por área.
- Las variables que cambian en el tiempo o por zona (valor UF, valor km, IVA)
  se modelan como Parametro + ValorParametro con fecha de vigencia: nunca se
  sobreescriben, se agrega un valor nuevo y el histórico queda intacto.
- Cada Presupuesto guarda un snapshot de los precios y parámetros usados al
  momento de emitirlo, de modo que editar las matrices a futuro NO altera
  presupuestos ya generados.
"""
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


# ============================================
# Matrices base (editables en admin)
# ============================================

class AreaServicio(models.Model):
    """Área de servicio/negocio. Cada área tiene su propia matriz de cobros."""
    nombre = models.CharField(max_length=120, unique=True)
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Área de servicio'
        verbose_name_plural = 'Áreas de servicio'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Zona(models.Model):
    """Zona geográfica. Permite que parámetros (ej: valor km) varíen por zona."""
    nombre = models.CharField(max_length=120, unique=True)
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Zona'
        verbose_name_plural = 'Zonas'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Comuna(models.Model):
    """
    Comuna asociada a una zona, con la distancia de traslado (ida + regreso)
    usada para calcular el costo de traslado (km x valor km de la zona).
    """
    zona = models.ForeignKey(Zona, on_delete=models.CASCADE, related_name='comunas')
    nombre = models.CharField(max_length=120)
    region = models.CharField(max_length=120, blank=True)
    km_ida_regreso = models.DecimalField(
        max_digits=8, decimal_places=1, default=0,
        help_text='Kilómetros de traslado (ida + regreso). 0 si no se cobra traslado.'
    )
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Comuna'
        verbose_name_plural = 'Comunas'
        ordering = ['zona', 'nombre']
        constraints = [
            models.UniqueConstraint(fields=['zona', 'nombre'], name='comuna_unica_por_zona'),
        ]

    def __str__(self):
        return f'{self.nombre} ({self.zona})'


class ItemMatriz(models.Model):
    """
    Ítem de la matriz de cobro de un área: concepto cobrable con su precio
    unitario. El precio puede estar expresado en CLP o en UF.
    """
    MONEDA_CLP = 'CLP'
    MONEDA_UF = 'UF'
    MONEDAS = [
        (MONEDA_CLP, 'Peso chileno (CLP)'),
        (MONEDA_UF, 'UF'),
    ]

    area = models.ForeignKey(
        AreaServicio, on_delete=models.CASCADE, related_name='items'
    )
    codigo = models.CharField(
        max_length=30, blank=True,
        help_text='Código interno opcional (ej: MED-001)'
    )
    concepto = models.CharField(max_length=255)
    unidad = models.CharField(
        max_length=40, default='unidad',
        help_text='Unidad de medida: unidad, m², hora, día, muestra, etc.'
    )
    moneda = models.CharField(max_length=3, choices=MONEDAS, default=MONEDA_CLP)
    precio_unitario = models.DecimalField(
        max_digits=14, decimal_places=4,
        help_text='Precio unitario en la moneda indicada (si es UF admite decimales)'
    )
    orden = models.PositiveIntegerField(default=0, help_text='Orden de despliegue')
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Ítem de matriz de cobro'
        verbose_name_plural = 'Matriz de cobros (ítems)'
        ordering = ['area', 'orden', 'concepto']

    def __str__(self):
        return f'[{self.area}] {self.concepto}'


# ============================================
# Parámetros variables (por fecha y/o zona)
# ============================================

class Parametro(models.Model):
    """
    Definición de una variable de cobro cuyo valor cambia en el tiempo
    (ej: UF) o según zona (ej: valor de traslado por km).
    """
    AMBITO_GLOBAL = 'global'
    AMBITO_ZONA = 'zona'
    AMBITOS = [
        (AMBITO_GLOBAL, 'Global (igual para todas las zonas)'),
        (AMBITO_ZONA, 'Por zona'),
    ]

    # Códigos usados por el motor de cálculo
    COD_UF = 'UF'
    COD_USD = 'USD'
    COD_VALOR_KM = 'VALOR_KM'
    COD_IVA = 'IVA'

    codigo = models.CharField(
        max_length=30, unique=True,
        help_text='Código usado por el sistema (no cambiar los predefinidos: UF, VALOR_KM, IVA)'
    )
    nombre = models.CharField(max_length=120)
    unidad = models.CharField(
        max_length=40, blank=True,
        help_text='Ej: CLP, CLP/km, %'
    )
    ambito = models.CharField(max_length=10, choices=AMBITOS, default=AMBITO_GLOBAL)

    class Meta:
        verbose_name = 'Parámetro'
        verbose_name_plural = 'Parámetros'
        ordering = ['codigo']

    def __str__(self):
        return f'{self.nombre} ({self.codigo})'

    def valor_vigente(self, fecha=None, zona=None):
        """
        Retorna el ValorParametro vigente a la fecha dada (hoy por defecto).
        Para parámetros por zona, busca primero el valor de la zona y si no
        existe cae al valor global (zona=None).
        """
        if fecha is None:
            fecha = timezone.localdate()

        qs = self.valores.filter(vigente_desde__lte=fecha)
        if self.ambito == self.AMBITO_ZONA and zona is not None:
            por_zona = qs.filter(zona=zona).order_by('-vigente_desde').first()
            if por_zona:
                return por_zona
        return qs.filter(zona__isnull=True).order_by('-vigente_desde').first()


class ValorParametro(models.Model):
    """
    Valor de un parámetro con fecha de inicio de vigencia y zona opcional.
    Para actualizar un valor NO se edita el registro anterior: se crea uno
    nuevo con la fecha desde la cual rige (mantiene histórico).
    """
    parametro = models.ForeignKey(
        Parametro, on_delete=models.CASCADE, related_name='valores'
    )
    zona = models.ForeignKey(
        Zona, on_delete=models.CASCADE, null=True, blank=True,
        related_name='valores_parametro',
        help_text='Dejar vacío para valor global. Solo aplica a parámetros por zona.'
    )
    valor = models.DecimalField(max_digits=14, decimal_places=4)
    vigente_desde = models.DateField(default=timezone.localdate)
    observacion = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = 'Valor de parámetro'
        verbose_name_plural = 'Valores de parámetros'
        ordering = ['parametro', '-vigente_desde']
        constraints = [
            models.UniqueConstraint(
                fields=['parametro', 'zona', 'vigente_desde'],
                name='unico_valor_por_fecha_zona',
            ),
        ]

    def __str__(self):
        zona = f' / {self.zona}' if self.zona else ''
        return f'{self.parametro.codigo}{zona} = {self.valor} (desde {self.vigente_desde})'

    def clean(self):
        if self.zona and self.parametro_id and self.parametro.ambito != Parametro.AMBITO_ZONA:
            raise ValidationError(
                'Este parámetro es global: no se le pueden asignar valores por zona.'
            )


# ============================================
# Configuración del PDF / empresa (singleton)
# ============================================

class ConfiguracionEmpresa(models.Model):
    """
    Datos de la empresa y textos del PDF. Singleton: existe un solo registro,
    editable en admin (la "matriz" de presentación del presupuesto).
    """
    nombre = models.CharField(max_length=200, default='PELP INTERNACIONAL S.A.')
    rut = models.CharField(max_length=20, blank=True, default='96.501.840-9')
    giro = models.CharField(
        max_length=200, blank=True,
        default='IMPORTACIÓN Y EXPORTACIÓN DE TODA CLASE DE BIENES MUEBLES'
    )
    direccion = models.CharField(max_length=255, blank=True, default='EL ROSAL 4560 – HUECHURABA, SANTIAGO – CHILE')
    telefono = models.CharField(
        max_length=120, blank=True,
        default='MESA CENTRAL: (2) 2870 – 4300 · SERVICIO TÉCNICO: (2) 2870 – 4350'
    )
    email = models.EmailField(blank=True)
    logo = models.ImageField(
        upload_to='presupuestos/logo/', blank=True, null=True,
        help_text='Logo/membrete que aparece en el encabezado del PDF. '
                  'Recomendado: PNG horizontal. Si se deja vacío se usa el '
                  'membrete PELP por defecto.'
    )
    logo_alto_mm = models.PositiveSmallIntegerField(
        default=22,
        help_text='Altura del logo en el PDF, en milímetros (el ancho se ajusta '
                  'solo). Sube o baja este número si el logo se ve grande o chico. '
                  'Referencia: 22 mm ≈ tamaño de un logo de esquina.'
    )
    mostrar_logo = models.BooleanField(
        default=True, help_text='Mostrar el membrete/logo en el encabezado del PDF'
    )
    texto_reenvio = models.TextField(
        blank=True,
        default=(
            'Para dar ejecución al presente trabajo, se debe reenviar esta cotización '
            'firmada y timbrada autorizando expresamente por correo electrónico\n'
            ' a:  Pmellado@pelp.cl; Daphne.tello@pelp.cl; Catalina.riquelme@pelp.cl'
        ),
        help_text='Texto bajo el detalle de observaciones (reenvío/autorización)'
    )
    nota_aprobacion = models.CharField(
        max_length=255, blank=True,
        default='*Servicio Sujeto a Aprobación del Área de Cobranzas de PELP Int.'
    )
    validez_texto = models.CharField(
        max_length=120, blank=True, default='Validez el presupuesto 30 días'
    )
    condiciones = models.TextField(
        blank=True,
        default=(
            '* El presente presupuesto está sujeto a variación según las condiciones que se encuentren en terreno\n'
            '* Repuestos sujetos a stock\n'
            '* Garantía 30 días por repuesto cambiado, no incluye traslado de técnico o viatico.\n'
            '* Defectos por fallas eléctricas causadas por condiciones externas al equipo no están cubiertas por garantías.'
        ),
        help_text='Condiciones al pie del PDF (una por línea)'
    )
    pie_pagina = models.CharField(
        max_length=255, blank=True,
        help_text='Texto del pie de página del PDF'
    )

    class Meta:
        verbose_name = 'Configuración de empresa / PDF'
        verbose_name_plural = 'Configuración de empresa / PDF'

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        self.pk = 1  # fuerza singleton
        super().save(*args, **kwargs)

    @classmethod
    def obtener(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


# ============================================
# Presupuesto y su detalle
# ============================================

class Presupuesto(models.Model):
    ESTADO_BORRADOR = 'borrador'
    ESTADO_EMITIDO = 'emitido'
    ESTADO_ACEPTADO = 'aceptado'
    ESTADO_RECHAZADO = 'rechazado'
    ESTADOS = [
        (ESTADO_BORRADOR, 'Borrador'),
        (ESTADO_EMITIDO, 'Emitido'),
        (ESTADO_ACEPTADO, 'Aceptado'),
        (ESTADO_RECHAZADO, 'Rechazado'),
    ]

    numero = models.CharField(max_length=20, unique=True, editable=False)
    estado = models.CharField(max_length=10, choices=ESTADOS, default=ESTADO_BORRADOR)

    # Datos del cliente
    cliente_nombre = models.CharField(max_length=200)
    cliente_rut = models.CharField(max_length=20, blank=True)
    cliente_contacto = models.CharField(max_length=120, blank=True)
    cliente_email = models.EmailField(blank=True)
    cliente_direccion = models.CharField(max_length=255, blank=True)

    # Clasificación
    area = models.ForeignKey(AreaServicio, on_delete=models.PROTECT, related_name='presupuestos')
    zona = models.ForeignKey(
        Zona, on_delete=models.PROTECT, related_name='presupuestos',
        null=True, blank=True
    )
    comuna = models.ForeignKey(
        Comuna, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='presupuestos',
        help_text='Comuna de destino (autocompleta los km de traslado)'
    )
    distancia_km = models.DecimalField(
        max_digits=8, decimal_places=1, default=0,
        help_text='Kilómetros de traslado (ida + regreso). 0 si no aplica.'
    )

    # Snapshots de parámetros al momento del cálculo
    valor_uf = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
        help_text='Valor UF usado en el cálculo (snapshot)'
    )
    valor_usd = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
        help_text='Valor USD a la fecha de emisión (snapshot, referencial)'
    )
    valor_km = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
        help_text='Valor CLP/km usado en el cálculo (snapshot)'
    )
    porcentaje_iva = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('19'))

    # Totales (CLP)
    costo_traslado = models.DecimalField(max_digits=14, decimal_places=0, default=0)
    subtotal = models.DecimalField(max_digits=14, decimal_places=0, default=0)
    monto_iva = models.DecimalField(max_digits=14, decimal_places=0, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=0, default=0)

    validez_dias = models.PositiveIntegerField(default=30)
    titulo_trabajo = models.CharField(
        max_length=200, blank=True,
        help_text='Título del trabajo en la barra verde de observaciones (ej: "VISITA TECNICA MERRYCHEF E1S"). Si se deja vacío usa el nombre del área.'
    )
    notas = models.TextField(blank=True, help_text='Observaciones adicionales para el cliente')

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='presupuestos_creados'
    )
    fecha_emision = models.DateField(default=timezone.localdate)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Presupuesto'
        verbose_name_plural = 'Presupuestos'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.numero} - {self.cliente_nombre}'

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = self._generar_numero()
        super().save(*args, **kwargs)

    def _generar_numero(self):
        """Correlativo anual: P-2026-0001, P-2026-0002, ..."""
        anio = timezone.localdate().year
        prefijo = f'P-{anio}-'
        ultimo = (
            Presupuesto.objects
            .filter(numero__startswith=prefijo)
            .order_by('-numero')
            .values_list('numero', flat=True)
            .first()
        )
        correlativo = int(ultimo.split('-')[-1]) + 1 if ultimo else 1
        return f'{prefijo}{correlativo:04d}'


class DetallePresupuesto(models.Model):
    """
    Línea del presupuesto. Guarda snapshot del concepto, moneda y precio del
    ítem de la matriz al momento de generar el presupuesto.
    """
    presupuesto = models.ForeignKey(
        Presupuesto, on_delete=models.CASCADE, related_name='detalles'
    )
    item = models.ForeignKey(
        ItemMatriz, on_delete=models.SET_NULL, null=True, blank=True,
        help_text='Ítem de la matriz de origen (referencial)'
    )
    concepto = models.CharField(max_length=255)
    unidad = models.CharField(max_length=40, default='unidad')
    cantidad = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    moneda = models.CharField(max_length=3, choices=ItemMatriz.MONEDAS, default=ItemMatriz.MONEDA_CLP)
    precio_unitario = models.DecimalField(
        max_digits=14, decimal_places=4,
        help_text='Precio unitario en la moneda original (snapshot)'
    )
    precio_unitario_clp = models.DecimalField(
        max_digits=14, decimal_places=0, default=0,
        help_text='Precio unitario convertido a CLP'
    )
    total_clp = models.DecimalField(max_digits=14, decimal_places=0, default=0)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Detalle de presupuesto'
        verbose_name_plural = 'Detalles de presupuesto'
        ordering = ['presupuesto', 'orden', 'id']

    def __str__(self):
        return f'{self.presupuesto.numero}: {self.concepto}'
