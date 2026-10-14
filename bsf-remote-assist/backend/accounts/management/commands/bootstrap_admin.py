import os
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
class Command(BaseCommand):
 help='Create the initial local BSF Remote administrator. Existing admin passwords are not changed unless reset is explicitly enabled.'
 def handle(self,*args,**kwargs):
  User=get_user_model(); username=os.getenv('BOOTSTRAP_ADMIN_USERNAME','').strip(); password=os.getenv('BOOTSTRAP_ADMIN_PASSWORD','')
  if not username or not password: raise CommandError('BOOTSTRAP_ADMIN_USERNAME and BOOTSTRAP_ADMIN_PASSWORD are required')
  u=User.objects.filter(username=username).first()
  if not u:
   u=User(username=username); u.set_password(password)
  elif os.getenv('BOOTSTRAP_ADMIN_RESET','false').lower()=='true':
   u.set_password(password)
  u.role='SUPERADMIN'; u.portal_enabled=True; u.is_active=True; u.is_staff=True; u.is_superuser=True; u.auth_source='LOCAL'; u.save()
  self.stdout.write(self.style.SUCCESS(f'Bootstrap administrator ready: {username}'))
