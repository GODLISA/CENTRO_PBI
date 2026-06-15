from django.contrib import admin
from django.utils.html import format_html

from .models import (
    AreaServicio,
    Comuna,
    ConfiguracionEmpresa,
    DetallePresupuesto,
    ItemMatriz,
    Parametro,
    Presupuesto,
    ValorParametro,
    Zona,
)


# ============================================
# Matrices de cobro (editables)
# ============================================

class ItemMatrizInline(admin.TabularInline):
    model = ItemMatriz
    extra = 1
    fields = ('codigo', 'concepto', 'unidad', 'moneda', 'precio_unitario', 'orden', 'activo')


@admin.register(AreaServicio)
class AreaServicioAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'activo', 'cantidad_items')
    list_filter = ('activo',)
    search_fields = ('nombre',)
    inlines = (ItemMatrizInline,)

    @admin.display(description='Ítems en matriz')
    def cantidad_items(self, obj):
        return obj.items.filter(activo=True).count()


@admin.register(ItemMatriz)
class ItemMatrizAdmin(admin.ModelAdmin):
    list_display = ('concepto', 'area', 'codigo', 'unidad', 'moneda', 'precio_unitario', 'activo')
    list_filter = ('area', 'moneda', 'activo')
    search_fields = ('concepto', 'codigo')
    list_editable = ('precio_unitario', 'activo')


class ComunaInline(admin.TabularInline):
    model = Comuna
    extra = 1
    fields = ('nombre', 'region', 'km_ida_regreso', 'activo')


@admin.register(Zona)
class ZonaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'activo', 'cantidad_comunas')
    list_filter = ('activo',)
    search_fields = ('nombre',)
    inlines = (ComunaInline,)

    @admin.display(description='Comunas')
    def cantidad_comunas(self, obj):
        return obj.comunas.filter(activo=True).count()


@admin.register(Comuna)
class ComunaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'region', 'zona', 'km_ida_regreso', 'activo')
    list_filter = ('zona', 'region', 'activo')
    search_fields = ('nombre', 'region')
    list_editable = ('km_ida_regreso', 'activo')


# ============================================
# Parámetros variables (UF, valor km, IVA)
# ============================================

class ValorParametroInline(admin.TabularInline):
    model = ValorParametro
    extra = 1
    fields = ('zona', 'valor', 'vigente_desde', 'observacion')
    ordering = ('-vigente_desde',)


@admin.register(Parametro)
class ParametroAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'codigo', 'unidad', 'ambito', 'valor_actual')
    inlines = (ValorParametroInline,)

    @admin.display(description='Valor vigente (global)')
    def valor_actual(self, obj):
        registro = obj.valor_vigente()
        return registro.valor if registro else '— sin valor —'


@admin.register(ValorParametro)
class ValorParametroAdmin(admin.ModelAdmin):
    list_display = ('parametro', 'zona', 'valor', 'vigente_desde', 'observacion')
    list_filter = ('parametro', 'zona')
    date_hierarchy = 'vigente_desde'


# ============================================
# Configuración del PDF / empresa
# ============================================

@admin.register(ConfiguracionEmpresa)
class ConfiguracionEmpresaAdmin(admin.ModelAdmin):
    readonly_fields = ('vista_previa_logo',)
    fieldsets = (
        ('Datos de la empresa', {
            'fields': ('nombre', 'rut', 'giro', 'direccion', 'telefono', 'email'),
        }),
        ('Logo / membrete del PDF', {
            'fields': ('logo', 'vista_previa_logo', 'logo_alto_mm', 'mostrar_logo'),
            'description': 'Sube aquí el logo de la empresa. Si lo dejas vacío, '
                           'se usa el membrete PELP por defecto. Ajusta "Alto del '
                           'logo" si se ve grande o chico.',
        }),
        ('Textos del PDF', {
            'fields': ('texto_reenvio', 'nota_aprobacion', 'validez_texto',
                       'condiciones', 'pie_pagina'),
        }),
    )

    @admin.display(description='Vista previa')
    def vista_previa_logo(self, obj):
        if obj and obj.logo:
            return format_html(
                '<img src="{}" style="max-height:120px;max-width:400px;'
                'border:1px solid #ddd;padding:4px;" />', obj.logo.url
            )
        return 'Sin logo subido (se usa el membrete PELP por defecto).'

    def has_add_permission(self, request):
        # Singleton: solo permitir crear si aún no existe
        return not ConfiguracionEmpresa.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


# ============================================
# Presupuestos (consulta; se crean desde la intranet)
# ============================================

class DetallePresupuestoInline(admin.TabularInline):
    model = DetallePresupuesto
    extra = 0
    can_delete = False
    readonly_fields = (
        'concepto', 'unidad', 'cantidad', 'moneda',
        'precio_unitario', 'precio_unitario_clp', 'total_clp',
    )
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Presupuesto)
class PresupuestoAdmin(admin.ModelAdmin):
    list_display = (
        'numero', 'cliente_nombre', 'area', 'zona',
        'fecha_emision', 'total', 'estado', 'creado_por',
    )
    list_filter = ('estado', 'area', 'zona', 'fecha_emision')
    search_fields = ('numero', 'cliente_nombre', 'cliente_rut')
    date_hierarchy = 'fecha_emision'
    inlines = (DetallePresupuestoInline,)
    readonly_fields = (
        'numero', 'valor_uf', 'valor_km', 'porcentaje_iva', 'costo_traslado',
        'subtotal', 'monto_iva', 'total', 'creado_por', 'created_at', 'updated_at',
    )
