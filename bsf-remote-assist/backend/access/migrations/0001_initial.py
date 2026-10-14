from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True
    dependencies = [('accounts','0001_initial'), ('devices','0001_initial')]
    operations = [
        migrations.CreateModel(
            name='DeviceGroup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, unique=True)),
                ('description', models.TextField(blank=True)),
                ('active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='TechnicianDevicePermission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('can_connect', models.BooleanField(default=True)),
                ('can_file_transfer', models.BooleanField(default=False)),
                ('can_terminal', models.BooleanField(default=False)),
                ('can_reboot', models.BooleanField(default=False)),
                ('device', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='devices.device')),
                ('group', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='access.devicegroup')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='accounts.portaluser')),
            ],
            options={'unique_together': {('user','group','device')}},
        ),
        migrations.AddConstraint(
            model_name='techniciandevicepermission',
            constraint=models.CheckConstraint(condition=models.Q(group__isnull=False) | models.Q(device__isnull=False), name='permission_has_target'),
        ),
    ]
