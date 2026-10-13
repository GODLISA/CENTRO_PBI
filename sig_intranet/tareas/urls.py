from django.urls import path

from . import views

urlpatterns = [
    path('', views.tablero_view, name='tareas_tablero'),

    # Lectura
    path('api/tablero/', views.api_tablero, name='tareas_api_tablero'),
    path('api/version/', views.api_version, name='tareas_api_version'),

    # Objetivos
    path('api/objetivo/crear/', views.api_objetivo_crear, name='tareas_objetivo_crear'),
    path('api/objetivo/<int:pk>/actualizar/', views.api_objetivo_actualizar, name='tareas_objetivo_actualizar'),
    path('api/objetivo/<int:pk>/posicion/', views.api_objetivo_posicion, name='tareas_objetivo_posicion'),
    path('api/objetivo/<int:pk>/eliminar/', views.api_objetivo_eliminar, name='tareas_objetivo_eliminar'),
    path('api/objetivo/<int:pk>/completar/', views.api_objetivo_completar, name='tareas_objetivo_completar'),
    path('api/objetivo/<int:pk>/miembro/', views.api_objetivo_miembro, name='tareas_objetivo_miembro'),
    path('api/objetivo/<int:pk>/reordenar-tareas/', views.api_objetivo_reordenar_tareas, name='tareas_objetivo_reordenar'),
    path('api/objetivo/<int:pk>/tarea/crear/', views.api_tarea_crear, name='tareas_tarea_crear'),

    # Tareas
    path('api/tarea/<int:pk>/actualizar/', views.api_tarea_actualizar, name='tareas_tarea_actualizar'),
    path('api/tarea/<int:pk>/eliminar/', views.api_tarea_eliminar, name='tareas_tarea_eliminar'),
    path('api/tarea/<int:pk>/reordenar-subtareas/', views.api_tarea_reordenar_subtareas, name='tareas_tarea_reordenar'),
    path('api/tarea/<int:pk>/subtarea/crear/', views.api_subtarea_crear, name='tareas_subtarea_crear'),
    path('api/tarea/<int:pk>/dependencia/crear/', views.api_dependencia_crear, name='tareas_dependencia_crear'),

    # Subtareas
    path('api/subtarea/<int:pk>/actualizar/', views.api_subtarea_actualizar, name='tareas_subtarea_actualizar'),
    path('api/subtarea/<int:pk>/eliminar/', views.api_subtarea_eliminar, name='tareas_subtarea_eliminar'),

    # Dependencias
    path('api/dependencia/<int:pk>/eliminar/', views.api_dependencia_eliminar, name='tareas_dependencia_eliminar'),
]
