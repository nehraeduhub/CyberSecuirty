from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from .models import DirectoryProvider
from .services import encrypt_secret, get_directory
User=get_user_model()

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me(request):
    u=request.user
    return Response({'username':u.username,'role':u.role,'portal_enabled':u.portal_enabled,'is_staff':u.is_staff,'auth_source':u.auth_source})

def is_admin(u): return bool(u.is_authenticated and u.role in ('ADMIN','SUPERADMIN'))

@api_view(['GET','POST'])
@permission_classes([IsAuthenticated])
def users(request):
    if not is_admin(request.user): return Response({'detail':'Admin only'},403)
    if request.method=='GET': return Response(list(User.objects.values('id','username','ad_username','email','role','portal_enabled','is_active','auth_source')))
    d=request.data; username=(d.get('username') or '').strip(); password=d.get('password') or ''
    if not username or not password: return Response({'error':'username and password required'},400)
    if User.objects.filter(username__iexact=username).exists(): return Response({'error':'username already exists'},409)
    role=d.get('role','TECHNICIAN')
    if role not in User.Role.values: return Response({'error':'invalid role'},400)
    if role in ('ADMIN','SUPERADMIN') and request.user.role!='SUPERADMIN': return Response({'error':'only SUPERADMIN can create administrators'},403)
    u=User.objects.create_user(username=username,email=d.get('email',''),password=password,role=role,portal_enabled=True,is_active=True,auth_source='LOCAL',created_by=request.user)
    return Response({'id':u.id,'username':u.username,'role':u.role,'auth_source':'LOCAL'},201)

@api_view(['GET','POST'])
@permission_classes([IsAuthenticated])
def directory(request):
    if not is_admin(request.user): return Response({'detail':'Admin only'},403)
    cfg=get_directory()
    if request.method=='GET':
        return Response({'configured':bool(cfg),'enabled':bool(cfg and cfg.enabled),'name':cfg.name if cfg else 'Active Directory','server_uri':cfg.server_uri if cfg else '','bind_dn':cfg.bind_dn if cfg else '','user_base_dn':cfg.user_base_dn if cfg else '','group_dn':cfg.group_dn if cfg else '','verify_ssl':cfg.verify_ssl if cfg else True})
    d=request.data; cfg=cfg or DirectoryProvider(name='Active Directory')
    cfg.server_uri=(d.get('server_uri') or '').strip(); cfg.bind_dn=(d.get('bind_dn') or '').strip(); cfg.user_base_dn=(d.get('user_base_dn') or '').strip(); cfg.group_dn=(d.get('group_dn') or '').strip(); cfg.verify_ssl=bool(d.get('verify_ssl',True)); cfg.enabled=bool(d.get('enabled',False))
    if d.get('bind_password'): cfg.bind_password_enc=encrypt_secret(d['bind_password'])
    cfg.save(); return Response({'ok':True,'enabled':cfg.enabled,'message':'Directory settings saved. AD login is available immediately for provisioned AD portal users.'})
