import os
from pathlib import Path


def env(name, default=''):
    return os.getenv(name, default)


def env_bool(name, default=False):
    return str(os.getenv(name, str(default))).strip().lower() in ('1', 'true', 'yes', 'on')


def env_int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = env('DJANGO_SECRET_KEY', 'unsafe-dev-key')
DEBUG = env_bool('DJANGO_DEBUG', False)
ALLOWED_HOSTS = [x.strip() for x in env('DJANGO_ALLOWED_HOSTS', 'localhost').split(',') if x.strip()]
INSTALLED_APPS = [
    'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions',
    'django.contrib.messages', 'django.contrib.staticfiles',
    'rest_framework', 'accounts', 'devices', 'remote_sessions', 'access', 'security',
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware', 'django.contrib.messages.middleware.MessageMiddleware',
]
ROOT_URLCONF = 'core.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [], 'APP_DIRS': True,
              'OPTIONS': {'context_processors': ['django.template.context_processors.request',
                                                 'django.contrib.auth.context_processors.auth',
                                                 'django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION = 'core.wsgi.application'

if env('DB_ENGINE', 'postgresql') == 'sqlite':  # unit tests / local development only
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': env('SQLITE_PATH', str(BASE_DIR / 'db.sqlite3'))}}
else:
    DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql', 'NAME': env('POSTGRES_DB', 'techguardinas_remote'),
                             'USER': env('POSTGRES_USER', 'techguardinas_remote'), 'PASSWORD': env('POSTGRES_PASSWORD', ''),
                             'HOST': env('POSTGRES_HOST', 'localhost'), 'PORT': env('POSTGRES_PORT', '5432')}}

if env('REDIS_URL'):
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.redis.RedisCache', 'LOCATION': env('REDIS_URL')}}
else:
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}

AUTH_PASSWORD_VALIDATORS = [{'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 12}}]
LANGUAGE_CODE = 'en-us'; TIME_ZONE = env('TIME_ZONE', 'Asia/Kolkata'); USE_I18N = True; USE_TZ = True
STATIC_URL = 'static/'; STATIC_ROOT = BASE_DIR / 'staticfiles'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'accounts.PortalUser'
AUTHENTICATION_BACKENDS = ['accounts.auth_backend.LocalPortalBackend', 'accounts.auth_backend.PortalADBackend']

PORTAL_ALLOW_SELF_REGISTRATION = False
PORTAL_REQUIRE_ADMIN_APPROVAL = True
PORTAL_MFA_ISSUER = env('PORTAL_MFA_ISSUER', 'TechGuardinas Remote')
# Public (internal-DNS) URL of this portal, used in session invitation links.
PORTAL_PUBLIC_URL = env('PORTAL_PUBLIC_URL', 'https://remote.techguardinas.local')

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ['rest_framework.authentication.SessionAuthentication'],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
}
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = env_bool('SESSION_COOKIE_SECURE', not DEBUG)
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Strict'
CSRF_COOKIE_SAMESITE = 'Strict'
SESSION_COOKIE_AGE = env_int('PORTAL_SESSION_HOURS', 10) * 3600
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'no-referrer'
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
CSRF_TRUSTED_ORIGINS = [x.strip() for x in env('CSRF_TRUSTED_ORIGINS', '').split(',') if x.strip()]

# ---------------------------------------------------------------------------
# MeshCentral remote-control engine
# ---------------------------------------------------------------------------
# Browser-facing URL of MeshCentral (internal DNS, internal CA certificate).
MESH_PUBLIC_URL = env('MESH_PUBLIC_URL', env('MESH_BASE_URL', 'https://mesh.remote.techguardinas.local'))
# URL the backend uses for server-to-server calls (agent downloads). Defaults to MESH_PUBLIC_URL.
MESH_INTERNAL_URL = env('MESH_INTERNAL_URL', '')
# Control websocket. Defaults to wss://<MESH_PUBLIC_URL host>/control.ashx
MESH_CONTROL_URL = env('MESH_CONTROL_URL', '')
MESH_TLS_VERIFY = env_bool('MESH_TLS_VERIFY', True)
MESH_CA_BUNDLE = env('MESH_CA_BUNDLE', '')
MESH_LOGIN_KEY_FILE = env('MESH_LOGIN_KEY_FILE', '/run/secrets/mesh_login_key')
MESH_SERVICE_USER = env('MESH_SERVICE_USER', 'tg-portal-svc')
MESH_DOMAIN = env('MESH_DOMAIN', '')
MESH_ACTION_TIMEOUT = env_int('MESH_ACTION_TIMEOUT', 30)
MESH_LOGIN_TOKEN_MINUTES = env_int('MESH_LOGIN_TOKEN_MINUTES', 1)
# MeshCentral UI elements hidden inside the portal console: 1 header, 4 footer, 16 left bar, 32 back button.
MESH_CONSOLE_HIDE = env_int('MESH_CONSOLE_HIDE', 1 | 4 | 16 | 32)
MESH_SESSION_RECORDING = env_bool('MESH_SESSION_RECORDING', False)
# Consent flags (MeshCentral): 1/2/4 notify desktop/terminal/files, 8/16/32 prompt, 64 connection toolbar.
MESH_CONSENT_ATTENDED = env_int('MESH_CONSENT_ATTENDED', 1 | 2 | 4 | 8 | 16 | 32 | 64)
MESH_CONSENT_UNATTENDED = env_int('MESH_CONSENT_UNATTENDED', 1 | 2 | 4 | 64)

# ---------------------------------------------------------------------------
# Remote-support policy
# ---------------------------------------------------------------------------
ATTENDED_CODE_TTL_MINUTES = env_int('ATTENDED_CODE_TTL_MINUTES', 10)
SESSION_MAX_MINUTES = env_int('SESSION_MAX_MINUTES', 120)
# Attended sessions end when the remote user's agent has been offline this long.
ATTENDED_OFFLINE_GRACE_SECONDS = env_int('ATTENDED_OFFLINE_GRACE_SECONDS', 45)
# Capabilities a technician gets in attended sessions (remote user still approves each one).
ATTENDED_CAPABILITIES = [x.strip() for x in env('ATTENDED_CAPABILITIES', 'desktop,chat,files,terminal').split(',') if x.strip()]
UNATTENDED_REQUIRE_MFA = env_bool('UNATTENDED_REQUIRE_MFA', True)
ATTENDED_REQUIRE_MFA = env_bool('ATTENDED_REQUIRE_MFA', False)
JOIN_MAX_ATTEMPTS = env_int('JOIN_MAX_ATTEMPTS', 10)
LOGIN_MAX_ATTEMPTS = env_int('LOGIN_MAX_ATTEMPTS', 8)

LOGGING = {
    'version': 1, 'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'loggers': {'techguardinas': {'handlers': ['console'], 'level': env('LOG_LEVEL', 'INFO')},
                'django.request': {'handlers': ['console'], 'level': 'ERROR', 'propagate': False}},
}
