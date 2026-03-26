from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from .models import Panel, PerfilUsuario


# ============================================
# Admin para Panel
# ============================================
@admin.register(Panel)
class PanelAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'activo', 'created_at')
    list_filter = ('activo',)
    search_fields = ('nombre',)
    list_editable = ('activo',)


# ============================================
# PerfilUsuario inline dentro del User admin
# ============================================
class PerfilUsuarioInline(admin.StackedInline):
    model = PerfilUsuario
    can_delete = False
    verbose_name = 'Perfil - Paneles asignados'
    verbose_name_plural = 'Perfil - Paneles asignados'
    filter_horizontal = ('paneles',)  # Widget cómodo para ManyToMany


# Extender el UserAdmin existente para incluir el inline
class CustomUserAdmin(UserAdmin):
    inlines = (PerfilUsuarioInline,)


# Re-registrar User con el admin personalizado
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)

# Personalizar títulos del admin
admin.site.site_header = 'SIG Intranet - Administración'
admin.site.site_title = 'SIG Admin'
admin.site.index_title = 'Gestión de Paneles y Usuarios'
