from django.urls import path
from . import views

urlpatterns = [
    path('csrf/', views.csrf),
    path('login/', views.login_view),
    path('logout/', views.logout_view),
    path('users/', views.users),
    path('users/provision/', views.provision_user),
    path('users/<int:user_id>/approve/', views.approve_user),
    path('users/<int:user_id>/disable/', views.disable_user),
    path('groups/', views.groups),
    path('groups/<int:group_id>/', views.update_group),
    path('groups/<int:group_id>/agent/<str:platform>/', views.group_agent),
    path('permissions/', views.permissions),
    path('permissions/set/', views.set_permission),
    path('permissions/<int:perm_id>/delete/', views.delete_permission),
]
