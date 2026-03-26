"""Test script para verificar el flujo completo del botón Actualizar Paneles."""
import os, sys, json, re
import urllib.request, urllib.error, urllib.parse, http.cookiejar

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sig_intranet.settings')

BASE = 'http://localhost:8000'

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# 1. GET /login/ → CSRF token
print('1. GET /login/ ...')
resp = opener.open(f'{BASE}/login/')
html = resp.read().decode()
m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html)
if not m:
    print('   ERROR: No se encontró csrfmiddlewaretoken en login page')
    sys.exit(1)
csrf1 = m.group(1)
print(f'   OK  csrf={csrf1[:20]}...')

# 2. POST /login/ (jvega)
print('2. POST /login/ (jvega) ...')
login_data = urllib.parse.urlencode({
    'username': 'jvega',
    'password': 'admin123',
    'csrfmiddlewaretoken': csrf1,
}).encode()
req = urllib.request.Request(
    f'{BASE}/login/', data=login_data,
    headers={'Referer': f'{BASE}/login/'},
)
try:
    resp = opener.open(req)
    print(f'   OK  status={resp.status}  url={resp.url}')
except urllib.error.HTTPError as e:
    print(f'   FAIL  status={e.code}')
    print(f'   (Verifica que la contraseña de jvega sea correcta)')
    sys.exit(1)

# 3. GET / → verificar botón y data-attrs
print('3. GET / (página principal) ...')
resp = opener.open(f'{BASE}/')
main_html = resp.read().decode()
print(f'   btn-actualizar en HTML:   {"SI" if "btn-actualizar" in main_html else "NO ← El usuario NO es staff o el template no lo renderiza"}')
print(f'   data-actualizar-url:      {"SI" if "data-actualizar-url" in main_html else "NO"}')
print(f'   data-csrf-token:          {"SI" if "data-csrf-token" in main_html else "NO"}')

m2 = re.search(r'data-actualizar-url="([^"]*)"', main_html)
if m2:
    print(f'   URL del atributo:         {m2.group(1)}')

# Extraer csrf del data-attr
m3 = re.search(r'data-csrf-token="([^"]*)"', main_html)
csrf2 = m3.group(1) if m3 else csrf1

# Verificar que app.js carga
m4 = re.search(r'src="([^"]*app\.js[^"]*)"', main_html)
if m4:
    js_url = m4.group(1)
    print(f'   app.js src:               {js_url}')
    try:
        js_resp = opener.open(f'{BASE}{js_url}')
        js_body = js_resp.read().decode()
        print(f'   app.js carga OK:          {len(js_body)} bytes')
    except Exception as ex:
        print(f'   app.js FALLA al cargar:   {ex}')

# 4. POST /api/actualizar-paneles/
print('4. POST /api/actualizar-paneles/ ...')
req2 = urllib.request.Request(
    f'{BASE}/api/actualizar-paneles/',
    data=b'{}',
    headers={
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf2,
        'Referer': f'{BASE}/',
    },
    method='POST',
)
try:
    resp2 = opener.open(req2)
    body = resp2.read().decode()
    print(f'   OK  status={resp2.status}')
    print(f'   Body: {body}')
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f'   FAIL  status={e.code}')
    print(f'   Body: {body[:500]}')

print('\n=== FIN DEL TEST ===')
