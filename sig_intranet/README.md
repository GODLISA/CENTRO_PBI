# Panel SIG - Intranet

Aplicación Django mínima para mostrar un iframe de Power BI protegido con autenticación.

## Estructura del Proyecto

```
sig_intranet/
├── manage.py
├── requirements.txt
├── db.sqlite3 (se crea automáticamente)
├── sig_intranet/
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── panel/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── urls.py
│   └── views.py
└── templates/
    └── panel/
        ├── login.html
        └── panel.html
```

## Instalación y Configuración

### 1. Crear entorno virtual (recomendado)

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 2. Instalar Django

```bash
pip install -r requirements.txt
```

### 3. Configurar ALLOWED_HOSTS

Editar `sig_intranet/settings.py` y agregar la IP del servidor:

```python
ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    '192.168.1.100',  # IP de tu servidor
    # O para permitir toda la subred:
    # '.tudominio.local',
]
```

### 4. Cambiar SECRET_KEY (importante para producción)

En `settings.py`, cambiar la SECRET_KEY por una única. Puedes generar una con:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 5. Aplicar migraciones

```bash
python manage.py migrate
```

### 6. Crear superusuario (administrador)

```bash
python manage.py createsuperuser
```

Sigue las instrucciones para crear usuario, email y contraseña.

### 7. Recolectar archivos estáticos (para producción)

```bash
python manage.py collectstatic
```

## Ejecución

### Desarrollo (solo localhost)

```bash
python manage.py runserver
```

Acceder a: http://127.0.0.1:8000

### Producción en Intranet (accesible desde otros equipos)

```bash
python manage.py runserver 0.0.0.0:8000
```

Acceder desde cualquier equipo de la red: http://[IP_DEL_SERVIDOR]:8000

**Ejemplo:** Si el servidor tiene IP 192.168.1.100:
- http://192.168.1.100:8000

### Opción con Gunicorn (Linux - más robusto)

```bash
pip install gunicorn
gunicorn sig_intranet.wsgi:application --bind 0.0.0.0:8000
```

### Opción con Waitress (Windows - más robusto)

```bash
pip install waitress
waitress-serve --listen=0.0.0.0:8000 sig_intranet.wsgi:application
```

## Gestión de Usuarios

### Crear usuarios adicionales

1. Acceder al admin: http://[IP]:8000/admin/
2. Iniciar sesión con el superusuario
3. Ir a "Usuarios" → "Agregar usuario"
4. Completar usuario y contraseña
5. Guardar

### Crear usuario por línea de comandos

```bash
python manage.py createsuperuser
```

O para usuario normal:

```bash
python manage.py shell
```

```python
from django.contrib.auth.models import User
User.objects.create_user('usuario', 'email@ejemplo.com', 'contraseña')
```

## Flujo de la Aplicación

1. Usuario accede a la URL raíz `/`
2. Si no está autenticado → Redirige a `/login/`
3. Ingresa credenciales
4. Si son correctas → Redirige a `/` (panel con iframe)
5. Puede cerrar sesión con el botón "Cerrar Sesión"

## URLs Disponibles

| URL | Descripción |
|-----|-------------|
| `/` | Panel principal (protegido) |
| `/login/` | Página de inicio de sesión |
| `/logout/` | Cerrar sesión |
| `/admin/` | Panel de administración Django |

## Notas de Seguridad

- La aplicación está configurada para **intranet sin HTTPS**
- `DEBUG = False` para producción
- CSRF activado por defecto
- Sesiones manejadas por Django
- No exponer a internet sin configurar HTTPS

## Solución de Problemas

### Error "ALLOWED_HOSTS"
Agregar la IP del servidor a `ALLOWED_HOSTS` en `settings.py`.

### No se pueden ver estilos del admin
Ejecutar `python manage.py collectstatic`.

### Puerto 8000 ocupado
Usar otro puerto: `python manage.py runserver 0.0.0.0:8080`
