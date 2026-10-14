from django.urls import path
from . import views
urlpatterns=[path('groups/',views.groups),path('users/',views.users),path('permissions/',views.permissions),path('users/provision/',views.provision_user),path('users/<int:user_id>/approve/',views.approve_user),path('users/<int:user_id>/disable/',views.disable_user),path('groups/create/',views.create_group),path('permissions/set/',views.set_permission),path('csrf/',views.csrf),path('login/',views.login_view),path('logout/',views.logout_view)]
