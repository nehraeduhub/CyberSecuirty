from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from .services import get_directory, decrypt_secret
from ldap3.utils.conv import escape_filter_chars

User=get_user_model()

class LocalPortalBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        user=super().authenticate(request, username=username, password=password, **kwargs)
        if user and user.is_active and user.portal_enabled and user.auth_source == 'LOCAL': return user
        return None

class PortalADBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password: return None
        cfg=get_directory()
        if not cfg or not cfg.enabled: return None
        try:
            from ldap3 import Server, Connection, ALL, Tls
            import ssl
            tls=Tls(validate=ssl.CERT_REQUIRED if cfg.verify_ssl else ssl.CERT_NONE)
            server=Server(cfg.server_uri, get_info=ALL, use_ssl=cfg.server_uri.lower().startswith('ldaps://'), tls=tls)
            bind_password=decrypt_secret(cfg.bind_password_enc)
            service=Connection(server, user=cfg.bind_dn, password=bind_password, auto_bind=True)
            safe=escape_filter_chars(username)
            service.search(cfg.user_base_dn, f'(&(objectClass=user)(sAMAccountName={safe}))', attributes=['distinguishedName','givenName','sn','mail','sAMAccountName'])
            if len(service.entries)!=1: service.unbind(); return None
            entry=service.entries[0]
            dn=str(entry.distinguishedName.value)
            service.unbind()
            user_conn=Connection(server, user=dn, password=password, auto_bind=True)
            user_conn.unbind()
            user=User.objects.filter(ad_username__iexact=username, auth_source='AD').first()
            if not user or not user.is_active or not user.portal_enabled: return None
            return user
        except Exception:
            return None
