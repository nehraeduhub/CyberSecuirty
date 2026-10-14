import os
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'unsafe-dev-key')
DEBUG = os.getenv('DJANGO_DEBUG','False').lower() == 'true'
ALLOWED_HOSTS = [x.strip() for x in os.getenv('DJANGO_ALLOWED_HOSTS','localhost').split(',') if x.strip()]
INSTALLED_APPS = [
 'django.contrib.admin','django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles',
 'rest_framework','corsheaders','accounts','devices','remote_sessions','access','security',
]
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware','corsheaders.middleware.CorsMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware','django.contrib.messages.middleware.MessageMiddleware']
ROOT_URLCONF='core.urls'
TEMPLATES=[{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION='core.wsgi.application'
DATABASES={'default':{'ENGINE':'django.db.backends.postgresql','NAME':os.getenv('POSTGRES_DB','bsf_remote'),'USER':os.getenv('POSTGRES_USER','bsf_remote'),'PASSWORD':os.getenv('POSTGRES_PASSWORD',''),'HOST':os.getenv('POSTGRES_HOST','localhost'),'PORT':os.getenv('POSTGRES_PORT','5432')}}
AUTH_PASSWORD_VALIDATORS=[]
LANGUAGE_CODE='en-us'; TIME_ZONE='Asia/Kolkata'; USE_I18N=True; USE_TZ=True
STATIC_URL='static/'; STATIC_ROOT=BASE_DIR/'staticfiles'
DEFAULT_AUTO_FIELD='django.db.models.BigAutoField'
AUTH_USER_MODEL='accounts.PortalUser'
AUTHENTICATION_BACKENDS=['accounts.auth_backend.LocalPortalBackend','accounts.auth_backend.PortalADBackend']

# django-auth-ldap: existing portal users only; authentication never creates portal accounts.
AUTH_LDAP_SERVER_URI=os.getenv('LDAP_SERVER_URI','ldaps://dc.example.local:636')
AUTH_LDAP_BIND_DN=os.getenv('LDAP_BIND_DN','')
AUTH_LDAP_BIND_PASSWORD=os.getenv('LDAP_BIND_PASSWORD','')
AUTH_LDAP_USER_SEARCH_BASE=os.getenv('LDAP_USER_BASE_DN','')
if AUTH_LDAP_USER_SEARCH_BASE:
    import ldap
    from django_auth_ldap.config import LDAPSearch
    AUTH_LDAP_USER_SEARCH=LDAPSearch(AUTH_LDAP_USER_SEARCH_BASE, ldap.SCOPE_SUBTREE, '(sAMAccountName=%(user)s)')
AUTH_LDAP_REQUIRE_GROUP=os.getenv('LDAP_REQUIRE_GROUP','') or None
AUTH_LDAP_NO_NEW_USERS=True
AUTH_LDAP_ALWAYS_UPDATE_USER=True
AUTH_LDAP_CACHE_TIMEOUT=300
AUTH_LDAP_START_TLS=os.getenv('LDAP_START_TLS','False').lower()=='true'
AUTH_LDAP_USER_ATTR_MAP={'first_name':'givenName','last_name':'sn','email':'mail'}

PORTAL_ALLOW_SELF_REGISTRATION=False
PORTAL_REQUIRE_ADMIN_APPROVAL=True
PORTAL_AUTH_MODE='LOCAL_FIRST'
MESH_BASE_URL=os.getenv('MESH_BASE_URL','https://remote-gateway.example.local')
MESH_NODE_URL_TEMPLATE=os.getenv('MESH_NODE_URL_TEMPLATE','')
MESH_API_KEY=os.getenv('MESH_API_KEY','')
MESH_ADMIN_USER=os.getenv('MESH_ADMIN_USER','')
MESH_ADMIN_PASSWORD=os.getenv('MESH_ADMIN_PASSWORD','')
MESHCTRL_PATH=os.getenv('MESHCTRL_PATH','')
PORTAL_MFA_ISSUER=os.getenv('PORTAL_MFA_ISSUER','BSF Remote')
REST_FRAMEWORK={'DEFAULT_AUTHENTICATION_CLASSES':['rest_framework.authentication.SessionAuthentication'],'DEFAULT_PERMISSION_CLASSES':['rest_framework.permissions.IsAuthenticated']}
CORS_ALLOW_ALL_ORIGINS=False
CORS_ALLOWED_ORIGINS=['http://localhost','http://127.0.0.1']
SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https')
SESSION_COOKIE_SECURE=not DEBUG
CSRF_COOKIE_SECURE=not DEBUG
SESSION_COOKIE_HTTPONLY=True
SESSION_COOKIE_SAMESITE='Strict'
CSRF_COOKIE_SAMESITE='Strict'
SECURE_CONTENT_TYPE_NOSNIFF=True
SECURE_REFERRER_POLICY='no-referrer'
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=False
CSRF_TRUSTED_ORIGINS=[x.strip() for x in os.getenv('CSRF_TRUSTED_ORIGINS','').split(',') if x.strip()]
MESHCTRL_URL=os.getenv('MESHCTRL_URL', MESH_BASE_URL)
MESH_LOGIN_KEY_FILE=os.getenv('MESH_LOGIN_KEY_FILE','')
MESH_ACTION_TIMEOUT=int(os.getenv('MESH_ACTION_TIMEOUT','60'))

MESH_NODE_BIN=os.getenv('MESH_NODE_BIN','node')
MESH_SERVER_ENTRY=os.getenv('MESH_SERVER_ENTRY','')
MESH_SSO_DOMAIN=os.getenv('MESH_SSO_DOMAIN','')
MESH_SSO_ENABLED=os.getenv('MESH_SSO_ENABLED','False').lower()=='true'
