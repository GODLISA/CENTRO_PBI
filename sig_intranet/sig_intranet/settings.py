"""
Django settings para SIG Intranet.
Configurado para entorno productivo en red interna.
"""

from pathlib import Path
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# ============================================
# CARGA DE VARIABLES DESDE ARCHIVO .env
# ============================================
# Lee el archivo .env y carga las variables de entorno
_env_path = BASE_DIR / '.env'
if _env_path.exists():
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _key, _val = _line.split('=', 1)
                os.environ.setdefault(_key.strip(), _val.strip())

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError('No se encontró SECRET_KEY. Definirla en el archivo .env')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

# Configurar con las IPs/dominios permitidos en tu intranet
ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    '172.16.0.13',
    # Agregar la IP del servidor, ejemplo:
    # '192.168.1.100',
    # O un rango completo con comodín:
    # '.midominio.local',
]

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'panel',  # Nuestra app
    'presupuestos',  # Módulo de presupuestos
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'sig_intranet.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'sig_intranet.wsgi.application'

# Database - SQLite por defecto
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'es-es'
TIME_ZONE = 'America/Lima'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ============================================
# CONFIGURACIÓN DE AUTENTICACIÓN
# ============================================

# URL a donde redirigir si el usuario no está autenticado
LOGIN_URL = '/login/'

# URL a donde redirigir después de login exitoso
LOGIN_REDIRECT_URL = '/'

# URL a donde redirigir después de logout
LOGOUT_REDIRECT_URL = '/login/'

# ============================================
# CONFIGURACIÓN DE SEGURIDAD PARA INTRANET
# ============================================

# Desactivar HTTPS obligatorio (solo para intranet sin SSL)
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Duración de la sesión (2 semanas por defecto)
SESSION_COOKIE_AGE = 1209600

# Cerrar sesión al cerrar el navegador (opcional, descomentar si se desea)
# SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# ============================================
# API EXTERNA - Actualización de paneles
# ============================================
API_BASE_URL = os.environ.get('API_BASE_URL', '')
API_BASE_TOKEN = os.environ.get('API_BASE_TOKEN', '')
