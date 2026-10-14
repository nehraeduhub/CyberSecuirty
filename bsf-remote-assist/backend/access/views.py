import json
from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth import login, logout
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.middleware.csrf import get_token
from .models import DeviceGroup, TechnicianDevicePermission
from remote_sessions.models import AuditLog

User=get_user_model()
def admin_only(request): return request.user.is_authenticated and request.user.role in ('SUPERADMIN','ADMIN')
def groups(request):
    if not admin_only(request): return JsonResponse({'detail':'Admin only'}, status=403)
    return JsonResponse(list(DeviceGroup.objects.values()), safe=False)
def users(request):
    if not admin_only(request): return JsonResponse({'detail':'Admin only'}, status=403)
    data=list(User.objects.values('id','username','ad_username','role','portal_enabled','is_active','date_joined','last_login'))
    return JsonResponse(data, safe=False)
@require_http_methods(['POST'])
def provision_user(request):
    if not admin_only(request): return JsonResponse({'detail':'Admin only'}, status=403)
    try: d=json.loads(request.body or '{}')
    except json.JSONDecodeError: return JsonResponse({'detail':'Invalid JSON'}, status=400)
    ad_username=(d.get('ad_username') or '').strip()
    if not ad_username: return JsonResponse({'detail':'ad_username required'}, status=400)
    if User.objects.filter(ad_username__iexact=ad_username).exists(): return JsonResponse({'detail':'User already provisioned'}, status=409)
    role=d.get('role','TECHNICIAN')
    if role not in User.Role.values: return JsonResponse({'detail':'Invalid role'}, status=400)
    u=User.objects.create(username=ad_username,ad_username=ad_username,role=role,portal_enabled=False,is_active=True,created_by=request.user)
    AuditLog.objects.create(actor=request.user,action='USER_PROVISIONED',target_type='USER',target_id=str(u.id),source_ip=request.META.get('REMOTE_ADDR'),details={'ad_username':ad_username,'role':role})
    return JsonResponse({'id':u.id,'username':u.username,'role':u.role,'portal_enabled':False}, status=201)
@require_http_methods(['POST'])
def approve_user(request,user_id):
    if not admin_only(request): return JsonResponse({'detail':'Admin only'}, status=403)
    u=User.objects.get(pk=user_id); u.portal_enabled=True; u.is_active=True; u.save(update_fields=['portal_enabled','is_active'])
    AuditLog.objects.create(actor=request.user,action='USER_APPROVED',target_type='USER',target_id=str(u.id),details={'username':u.username})
    return JsonResponse({'ok':True})
@require_http_methods(['POST'])
def disable_user(request,user_id):
    if not admin_only(request): return JsonResponse({'detail':'Admin only'}, status=403)
    u=User.objects.get(pk=user_id); u.portal_enabled=False; u.save(update_fields=['portal_enabled'])
    AuditLog.objects.create(actor=request.user,action='USER_DISABLED',target_type='USER',target_id=str(u.id),details={'username':u.username})
    return JsonResponse({'ok':True})
def permissions(request):
    if not admin_only(request): return JsonResponse({'detail':'Admin only'}, status=403)
    return JsonResponse(list(TechnicianDevicePermission.objects.values()), safe=False)
def csrf(request): return JsonResponse({'csrfToken':get_token(request)})
@require_http_methods(['POST'])
def login_view(request):
    try: d=json.loads(request.body or '{}')
    except json.JSONDecodeError: return JsonResponse({'detail':'Invalid JSON'}, status=400)
    username=(d.get('username') or '').strip(); password=d.get('password') or ''
    user=authenticate(request,username=username,password=password)
    if user is None: return JsonResponse({'detail':'Invalid credentials or portal access not approved'}, status=401)
    login(request,user); AuditLog.objects.create(actor=user,action='LOGIN',source_ip=request.META.get('REMOTE_ADDR'),details={})
    return JsonResponse({'ok':True,'username':user.username,'role':user.role})
def logout_view(request):
    if request.user.is_authenticated: AuditLog.objects.create(actor=request.user,action='LOGOUT',source_ip=request.META.get('REMOTE_ADDR'),details={})
    logout(request); return JsonResponse({'ok':True})

@require_http_methods(['POST'])
def create_group(request):
    if not admin_only(request): return JsonResponse({'detail':'Admin only'}, status=403)
    try: d=json.loads(request.body or '{}')
    except json.JSONDecodeError: return JsonResponse({'detail':'Invalid JSON'}, status=400)
    name=(d.get('name') or '').strip()
    if not name: return JsonResponse({'detail':'name required'}, status=400)
    g=DeviceGroup.objects.create(name=name,description=d.get('description',''))
    AuditLog.objects.create(actor=request.user,action='GROUP_CREATED',target_type='GROUP',target_id=str(g.id),details={'name':g.name})
    return JsonResponse({'id':g.id,'name':g.name},status=201)
@require_http_methods(['POST'])
def set_permission(request):
    if not admin_only(request): return JsonResponse({'detail':'Admin only'}, status=403)
    try: d=json.loads(request.body or '{}')
    except json.JSONDecodeError: return JsonResponse({'detail':'Invalid JSON'}, status=400)
    try: u=User.objects.get(pk=d['user_id']); g=DeviceGroup.objects.get(pk=d['group_id'])
    except (KeyError,User.DoesNotExist,DeviceGroup.DoesNotExist): return JsonResponse({'detail':'User/group not found'},status=404)
    perm,created=TechnicianDevicePermission.objects.get_or_create(user=u,group=g,device=None,defaults={
        'can_connect':bool(d.get('can_connect',True)),'can_file_transfer':bool(d.get('can_file_transfer',False)),'can_terminal':bool(d.get('can_terminal',False)),'can_reboot':bool(d.get('can_reboot',False))})
    if not created:
        for f in ('can_connect','can_file_transfer','can_terminal','can_reboot'): setattr(perm,f,bool(d.get(f,getattr(perm,f))))
        perm.save()
    AuditLog.objects.create(actor=request.user,action='PERMISSION_CHANGED',target_type='PERMISSION',target_id=str(perm.id),details={'user_id':u.id,'group_id':g.id})
    return JsonResponse({'id':perm.id,'created':created})
