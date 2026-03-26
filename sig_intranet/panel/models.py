from django.db import models
from django.contrib.auth.models import User


class Panel(models.Model):
    """
    Representa un panel/dashboard de Power BI.
    Se gestiona desde el admin de Django.
    """
    nombre = models.CharField(max_length=200, help_text='Nombre descriptivo del panel')
    url_iframe = models.TextField(help_text='URL completa del iframe de Power BI')
    activo = models.BooleanField(default=True, help_text='Panel visible para usuarios asignados')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Panel'
        verbose_name_plural = 'Paneles'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class PerfilUsuario(models.Model):
    """
    Extiende el User de Django con una relación ManyToMany a Panel.
    Se crea automáticamente al crear un User (ver signals.py).
    """
    usuario = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='perfil'
    )
    paneles = models.ManyToManyField(
        Panel,
        blank=True,
        related_name='usuarios',
        help_text='Paneles que este usuario puede ver'
    )

    class Meta:
        verbose_name = 'Perfil de Usuario'
        verbose_name_plural = 'Perfiles de Usuarios'

    def __str__(self):
        return f'Perfil de {self.usuario.username}'
