"""Minimal BSF Remote Windows-agent heartbeat client.
The production MSI wraps this module as a Windows Service and stores the token in protected service configuration.
"""
import json, os, platform, socket, time, urllib.request

SERVER=os.environ.get('BSF_REMOTE_URL','https://remote.example.local')
DEVICE_ID=os.environ.get('BSF_DEVICE_ID','')
TOKEN=os.environ.get('BSF_ENROLLMENT_TOKEN','')
VERSION=os.environ.get('BSF_AGENT_VERSION','0.1.0')
INTERVAL=int(os.environ.get('BSF_HEARTBEAT_SECONDS','30'))

def local_ip():
    try:
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.connect(('1.1.1.1',80)); ip=s.getsockname()[0]; s.close(); return ip
    except Exception: return ''

def heartbeat():
    payload=json.dumps({'device_id':DEVICE_ID,'token':TOKEN,'hostname':socket.gethostname(),'ip_address':local_ip(),'os':platform.platform(),'agent_version':VERSION}).encode()
    req=urllib.request.Request(SERVER.rstrip('/')+'/api/devices/heartbeat/',data=payload,headers={'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(req,timeout=15) as r: return json.loads(r.read())

def main():
    if not DEVICE_ID or not TOKEN: raise SystemExit('BSF_DEVICE_ID and BSF_ENROLLMENT_TOKEN are required')
    while True:
        try: heartbeat()
        except Exception as exc: print('heartbeat failed:',exc,flush=True)
        time.sleep(INTERVAL)
if __name__=='__main__': main()
