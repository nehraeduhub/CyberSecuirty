from django.urls import path
from .views import me, users, directory
urlpatterns=[path('me/',me),path('users/',users),path('directory/',directory)]
