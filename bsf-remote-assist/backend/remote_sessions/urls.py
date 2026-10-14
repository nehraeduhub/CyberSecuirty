from django.urls import path
from . import views
from .bridge_views import execute
urlpatterns=[path('sessions/create/',views.create_session),path('sessions/',views.sessions),path('sessions/<uuid:session_id>/',views.session_detail),path('sessions/<uuid:session_id>/start/',views.start_session),path('sessions/<uuid:session_id>/end/',views.end_session),path('sessions/<uuid:session_id>/action/',views.session_action),path('sessions/<uuid:session_id>/execute/',execute)]
