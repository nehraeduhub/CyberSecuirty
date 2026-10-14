from django.db import migrations, models
import uuid

class Migration(migrations.Migration):
 initial=True
 dependencies=[]
 operations=[migrations.CreateModel(name='Device',fields=[
 ('id',models.UUIDField(default=uuid.uuid4,editable=False,primary_key=True,serialize=False)),('name',models.CharField(max_length=255)),('hostname',models.CharField(blank=True,max_length=255)),('ip_address',models.GenericIPAddressField(blank=True,null=True)),('os',models.CharField(blank=True,max_length=100)),('unit',models.CharField(blank=True,max_length=150)),('group',models.CharField(blank=True,max_length=150)),('agent_version',models.CharField(blank=True,max_length=50)),('agent_token_hash',models.CharField(blank=True,max_length=128)),('enrollment_token_hash',models.CharField(blank=True,max_length=128)),('agent_enrolled',models.BooleanField(default=False)),('agent_last_ip',models.GenericIPAddressField(blank=True,null=True)),('online',models.BooleanField(default=False)),('last_seen',models.DateTimeField(blank=True,null=True)),('approved',models.BooleanField(default=False)),('created_at',models.DateTimeField(auto_now_add=True)),('updated_at',models.DateTimeField(auto_now=True))])]
