from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid

class Migration(migrations.Migration):
    initial=True
    dependencies=[('devices','0002_device_mesh_fields'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations=[
        migrations.CreateModel(name='RemoteSession',fields=[('id',models.UUIDField(default=uuid.uuid4,editable=False,primary_key=True,serialize=False)),('code',models.CharField(max_length=12,unique=True)),('mode',models.CharField(choices=[('ATTENDED','Attended'),('UNATTENDED','Unattended')],max_length=20)),('status',models.CharField(choices=[('PENDING','Pending'),('ACTIVE','Active'),('ENDED','Ended'),('DENIED','Denied')],default='PENDING',max_length=20)),('started_at',models.DateTimeField(blank=True,null=True)),('ended_at',models.DateTimeField(blank=True,null=True)),('created_at',models.DateTimeField(auto_now_add=True)),('mesh_launch_url',models.URLField(blank=True)),('metadata',models.JSONField(blank=True,default=dict)),('device',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.PROTECT,to='devices.device')),('technician',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to=settings.AUTH_USER_MODEL))]),
        migrations.CreateModel(name='AuditLog',fields=[('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),('action',models.CharField(max_length=100)),('target_type',models.CharField(blank=True,max_length=100)),('target_id',models.CharField(blank=True,max_length=100)),('source_ip',models.GenericIPAddressField(blank=True,null=True)),('details',models.JSONField(default=dict)),('created_at',models.DateTimeField(auto_now_add=True)),('actor',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,to=settings.AUTH_USER_MODEL))])
    ]
