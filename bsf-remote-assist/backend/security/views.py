import base64, io, secrets
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from django.core import signing
from django.contrib.auth.decorators import login_required
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import MFAMethod, StepUpGrant
try:
    import pyotp, qrcode, qrcode.image.svg
except ImportError:
    pyotp=qrcode=None

def require_staff(user): return user.role in ('ADMIN','SUPERADMIN','TECHNICIAN') and user.portal_enabled and user.is_active

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def mfa_status(request):
    m=getattr(request.user,'mfa',None)
    return Response({'configured':bool(m),'enabled':bool(m and m.enabled)})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mfa_enroll(request):
    if not require_staff(request.user): return Response({'detail':'MFA enrollment is unavailable'},403)
    if pyotp is None: return Response({'detail':'pyotp is not installed'},503)
    m, _=MFAMethod.objects.get_or_create(user=request.user,defaults={'secret':pyotp.random_base32()})
    if m.enabled: return Response({'detail':'MFA is already enabled'},409)
    uri=pyotp.TOTP(m.secret).provisioning_uri(name=request.user.username,issuer_name=settings.PORTAL_MFA_ISSUER)
    svg=''
    if qrcode is not None:
        buf=io.BytesIO(); qrcode.make(uri,image_factory=qrcode.image.svg.SvgPathImage).save(buf); svg=buf.getvalue().decode()
    return Response({'secret':m.secret,'otpauth_uri':uri,'qr_svg':svg})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mfa_verify(request):
    if pyotp is None: return Response({'detail':'pyotp is not installed'},503)
    m=getattr(request.user,'mfa',None)
    if not m: return Response({'detail':'Enroll MFA first'},400)
    code=str(request.data.get('code','')).replace(' ','')
    if not pyotp.TOTP(m.secret).verify(code,valid_window=1): return Response({'detail':'Invalid MFA code'},401)
    m.enabled=True; m.verified_at=timezone.now(); m.save(update_fields=['enabled','verified_at','updated_at'])
    from remote_sessions.services import audit
    audit(request.user,'MFA_ENABLED',request.user,request)
    return Response({'ok':True})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def stepup_verify(request):
    if pyotp is None: return Response({'detail':'pyotp is not installed'},503)
    m=getattr(request.user,'mfa',None)
    if not m or not m.enabled: return Response({'detail':'MFA must be enrolled and enabled'},403)
    code=str(request.data.get('code','')).replace(' ','')
    from remote_sessions.services import audit
    from django.core.cache import cache
    replay_key=f'mfa-used:{request.user.pk}:{code}'
    if cache.get(replay_key) or not pyotp.TOTP(m.secret).verify(code,valid_window=1):
        audit(request.user,'MFA_STEPUP_FAILED',request.user,request); return Response({'detail':'Invalid MFA code'},401)
    cache.set(replay_key,1,120)
    purpose=str(request.data.get('purpose','REMOTE_CONNECT'))[:64]
    grant=StepUpGrant.objects.create(user=request.user,purpose=purpose,expires_at=timezone.now()+timedelta(minutes=5))
    return Response({'grant':str(grant.id),'expires_at':grant.expires_at})

def consume_stepup(user,grant_id,purpose):
    try: g=StepUpGrant.objects.get(id=grant_id,user=user,purpose=purpose,used=False)
    except Exception: return False
    if g.expires_at < timezone.now(): return False
    g.used=True; g.save(update_fields=['used']); return True
