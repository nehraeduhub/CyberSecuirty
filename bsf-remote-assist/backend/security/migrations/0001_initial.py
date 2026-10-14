from django.db import migrations, models
import django.db.models.deletion
import django.conf
import uuid
class Migration(migrations.Migration):
 initial=True
 dependencies=[migrations.swappable_dependency(django.conf.settings.AUTH_USER_MODEL)]
 operations=[migrations.CreateModel(name='MFAMethod',fields=[('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),('secret',models.CharField(max_length=64)),('enabled',models.BooleanField(default=False)),('verified_at',models.DateTimeField(blank=True,null=True)),('created_at',models.DateTimeField(auto_now_add=True)),('updated_at',models.DateTimeField(auto_now=True)),('user',models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,related_name='mfa',to=django.conf.settings.AUTH_USER_MODEL))]),migrations.CreateModel(name='StepUpGrant',fields=[('id',models.UUIDField(default=uuid.uuid4,editable=False,primary_key=True,serialize=False)),('purpose',models.CharField(max_length=64)),('expires_at',models.DateTimeField()),('used',models.BooleanField(default=False)),('created_at',models.DateTimeField(auto_now_add=True)),('user',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,to=django.conf.settings.AUTH_USER_MODEL))])]
