"""
WSGI config for sig_intranet project.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sig_intranet.settings')

application = get_wsgi_application()
