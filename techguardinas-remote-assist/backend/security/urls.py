from django.urls import path
from .views import mfa_status, mfa_enroll, mfa_verify, stepup_verify
urlpatterns=[
 path('mfa/status/',mfa_status), path('mfa/enroll/',mfa_enroll), path('mfa/verify/',mfa_verify), path('stepup/verify/',stepup_verify),
]
