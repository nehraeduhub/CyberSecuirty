import base64
import hashlib
from django.conf import settings
from django.contrib.auth import get_user_model
from cryptography.fernet import Fernet
from .models import DirectoryProvider

User=get_user_model()

def _fernet():
    key=base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)

def encrypt_secret(value):
    return _fernet().encrypt(value.encode()).decode() if value else ''

def decrypt_secret(value):
    return _fernet().decrypt(value.encode()).decode() if value else ''

def get_directory():
    return DirectoryProvider.objects.order_by('id').first()

def provision_ad_user(*, actor, username, ad_username, role='TECHNICIAN'):
    if actor.role not in ('SUPERADMIN','ADMIN'): raise PermissionError('Administrator approval required')
    user, created=User.objects.get_or_create(username=username, defaults={'ad_username':ad_username,'role':role,'portal_enabled':False,'is_active':True,'auth_source':'AD'})
    user.ad_username=ad_username; user.role=role; user.portal_enabled=False; user.is_active=True; user.auth_source='AD'; user.created_by=actor; user.save()
    return user
