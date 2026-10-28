#!/bin/bash
# Starts the complete TechGuardinas Remote stack on one Linux host, using the same templates as production:
# PostgreSQL, Redis, MeshCentral (rendered config, TLS offload), NGINX (deploy/nginx template),
# Django/gunicorn, the session worker, and two X displays acting as the screens of test PCs.
set -euo pipefail
. "${STACK_ENV:-$(dirname "$0")/stack.env}"
unset HTTPS_PROXY https_proxy HTTP_PROXY http_proxy
mkdir -p "$WORK"/{logs,secrets,agents,evidence,www}
L=$WORK/logs

# --- secrets
[ -s "$WORK/secrets/mesh_login_key" ] || openssl rand -hex 80 > "$WORK/secrets/mesh_login_key"

# --- Trust the internal CA in the browser certificate store (as GPO would on TechGuardinas PCs)
if command -v certutil >/dev/null; then
  mkdir -p "$HOME/.pki/nssdb"
  certutil -d "sql:$HOME/.pki/nssdb" -L >/dev/null 2>&1 || certutil -d "sql:$HOME/.pki/nssdb" -N --empty-password
  certutil -d "sql:$HOME/.pki/nssdb" -A -t "C,," -n "TechGuardinas internal CA" -i "$PKI/ca.crt"
fi

# --- PostgreSQL + Redis
id postgres >/dev/null 2>&1 || useradd -m postgres
if [ ! -d "$WORK/pg" ]; then
  mkdir -p "$WORK/pg" && chown postgres "$WORK/pg"
  su postgres -c "$PG_BIN/initdb -D $WORK/pg -A trust -U postgres" >/dev/null
fi
touch $L/postgres.log && chown postgres $L/postgres.log
su postgres -c "$PG_BIN/pg_ctl -D $WORK/pg -l $L/postgres.log -o '-p 5432 -k /tmp -c listen_addresses=127.0.0.1' start" >/dev/null
sleep 2
psql -h /tmp -U postgres -tc "select 1 from pg_roles where rolname='techguardinas_remote'" | grep -q 1 || psql -h /tmp -U postgres -c "create user techguardinas_remote password 'testpw'" >/dev/null
psql -h /tmp -U postgres -tc "select 1 from pg_database where datname='techguardinas_remote'" | grep -q 1 || psql -h /tmp -U postgres -c "create database techguardinas_remote owner techguardinas_remote" >/dev/null
redis-server --daemonize yes --port 6379 --bind 127.0.0.1 --dir "$WORK" >/dev/null

# --- MeshCentral (same render-config.js and bootstrap as the container image)
M=$WORK/meshcentral
if [ ! -d "$M/node_modules" ]; then mkdir -p "$M" && cp -al "$MESH_NODE_MODULES" "$M/node_modules"; fi
cp "$REPO/meshcentral/render-config.js" "$M/"
mkdir -p "$M/meshcentral-data" "$M/meshcentral-recordings"
( cd "$M"
  MESH_HOSTNAME=$MESH_HOST MESH_LOGIN_KEY_FILE=$WORK/secrets/mesh_login_key MESH_TRUSTED_PROXY=127.0.0.1 \
  MESH_RECORDINGS_PATH=$M/meshcentral-recordings node render-config.js > meshcentral-data/config.json
  if [ ! -f meshcentral-data/.techguardinas-service-account ]; then
    node node_modules/meshcentral --createaccount tg-portal-svc --pass "$(openssl rand -hex 24)" --email svc@techguardinas-remote.invalid >/dev/null
    node node_modules/meshcentral --adminaccount tg-portal-svc >/dev/null
    touch meshcentral-data/.techguardinas-service-account
  fi )

# --- NGINX from the production template; upstreams on localhost, SPA served from disk
python3 - "$REPO/deploy/nginx/default.conf.template" "$WORK/nginx.conf" <<PY
import sys
t=open(sys.argv[1]).read().replace('\${PORTAL_HOSTNAME}','$PORTAL_HOST').replace('\${MESH_HOSTNAME}','$MESH_HOST').replace('\${HTTPS_PORT}','443')
t=t.replace('http://web:8000','http://127.0.0.1:8000').replace('http://meshcentral:4430','http://127.0.0.1:4430')
t=t.replace('/etc/nginx/certs/','$PKI/').replace('alias /static/;','alias $REPO/backend/staticfiles/;')
t=t.replace('''        proxy_pass http://frontend:80;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-Proto https;''','''        root $WORK/www; try_files \$uri /index.html;''')
open(sys.argv[2],'w').write(t)
PY
cat > "$WORK/nginx-main.conf" <<NG
worker_processes 2; pid $WORK/nginx.pid; error_log $L/nginx-error.log;
events { worker_connections 1024; }
http { include /etc/nginx/mime.types; access_log $L/nginx-access.log; include $WORK/nginx.conf; }
NG
nginx -c "$WORK/nginx-main.conf"
( cd "$WORK/meshcentral" && setsid node node_modules/meshcentral >> "$L/meshcentral.log" 2>&1 & )
for i in $(seq 1 60); do grep -q "Loaded web certificate" "$L/meshcentral.log" 2>/dev/null && break; sleep 1; done

# --- Frontend (built offline from the committed lockfile's node_modules)
( cd "$REPO/frontend" && npx vite build --outDir "$WORK/www" --emptyOutDir >/dev/null )

# --- Django
cat > "$WORK/portal.env" <<PE
DJANGO_SECRET_KEY=$(openssl rand -hex 32)
DJANGO_ALLOWED_HOSTS=$PORTAL_HOST,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://$PORTAL_HOST
POSTGRES_PASSWORD=testpw
POSTGRES_HOST=127.0.0.1
REDIS_URL=redis://127.0.0.1:6379/0
PORTAL_PUBLIC_URL=https://$PORTAL_HOST
MESH_PUBLIC_URL=https://$MESH_HOST
MESH_CA_BUNDLE=$PKI/ca.crt
MESH_LOGIN_KEY_FILE=$WORK/secrets/mesh_login_key
MESH_SESSION_RECORDING=true
ATTENDED_OFFLINE_GRACE_SECONDS=10
BOOTSTRAP_ADMIN_USERNAME=tgadmin
BOOTSTRAP_ADMIN_PASSWORD=$ADMIN_PASSWORD
PE
run_django() { ( set -a; . "$WORK/portal.env"; set +a; . "$VENV/bin/activate"; cd "$REPO/backend"; exec "$@" ); }
run_django python manage.py migrate --noinput >/dev/null
run_django python manage.py bootstrap_admin
run_django python manage.py collectstatic --noinput >/dev/null
( run_django setsid gunicorn core.wsgi:application --bind 127.0.0.1:8000 --workers 3 --timeout 120 --capture-output \
    --access-logfile "$L/gunicorn-access.log" --error-logfile "$L/gunicorn.log" & )
( run_django setsid sh -c "python manage.py session_worker --interval 3 >> $L/worker.log 2>&1" & )

# --- Test PC screens: one X display each, with a visible "desktop" window
"$REPO/tests/local-stack/fake-session/install.sh"
for n in 1 2; do
  d=$([ $n = 1 ] && echo :5 || echo :6)
  ( setsid Xvfb $d -screen 0 1280x800x24 > "$L/xvfb$n.log" 2>&1 & )
  sleep 1
  python3 "$REPO/tests/local-stack/fake-session/utmp_login.py" "$d"
  ( env -i PATH=/usr/bin:/bin HOME=/root DISPLAY=$d setsid "$CHROMIUM" --no-sandbox --user-data-dir="$WORK/pc$n-browser" \
      --no-first-run --window-position=0,0 --window-size=1280,800 --kiosk "file://$REPO/tests/local-stack/remote-pc/pc$n.html" > /dev/null 2>&1 & )
done
sleep 5
curl -sf --cacert "$PKI/ca.crt" "https://$PORTAL_HOST/api/health/" && echo && echo "Stack is up: https://$PORTAL_HOST"
