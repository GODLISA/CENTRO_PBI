from django.contrib import admin

from .models import (
    CambioTablero, Dependencia, Objetivo, ObjetivoMiembro, PreferenciaUsuario,
    Subtarea, Tarea,
)


class TareaInline(admin.TabularInline):
    model = Tarea
    extra = 0
    show_change_link = True


class MiembroInline(admin.TabularInline):
    model = ObjetivoMiembro
    extra = 0


class SubtareaInline(admin.TabularInline):
    model = Subtarea
    extra = 0


@admin.register(Objetivo)
class ObjetivoAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'dueno', 'es_privada', 'creado_en')
    list_filter = ('es_privada',)
    search_fields = ('titulo',)
    inlines = [TareaInline, MiembroInline]


@admin.register(Tarea)
class TareaAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'objetivo', 'responsable', 'estado', 'prioridad', 'orden')
    list_filter = ('estado', 'prioridad')
    search_fields = ('titulo',)
    inlines = [SubtareaInline]


@admin.register(Dependencia)
class DependenciaAdmin(admin.ModelAdmin):
    list_display = ('tarea_origen', 'destino_label', 'bloqueante')


@admin.register(PreferenciaUsuario)
class PreferenciaUsuarioAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'color')


admin.site.register(CambioTablero)
