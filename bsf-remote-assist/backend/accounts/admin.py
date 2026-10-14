from django.contrib import admin
from .models import PortalUser, DirectoryProvider
@admin.register(PortalUser)
class PortalUserAdmin(admin.ModelAdmin):
 list_display=('username','auth_source','role','portal_enabled','is_active','last_login')
 list_filter=('auth_source','role','portal_enabled','is_active')
 search_fields=('username','ad_username','email')
 readonly_fields=('last_login','last_login_ip')
@admin.register(DirectoryProvider)
class DirectoryProviderAdmin(admin.ModelAdmin):
 list_display=('name','enabled','server_uri','verify_ssl','updated_at')
