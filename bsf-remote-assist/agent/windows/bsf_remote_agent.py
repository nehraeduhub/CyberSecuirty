"""BSF Remote Windows management heartbeat agent.
This is the management/health component. MeshCentral remains the remote-control engine.
"""
import json, os, platform, socket, time, urllib.request
from pathlib import Path

ROOT = Path(os.environ.get('PROGRAMDATA', r'C:\ProgramData')) / 'BSFRemote'
CONFIG = ROOT / 'config.json'
VERSION = '0.7.0'

def load_config():
    if not CONFIG.exists():
        raise RuntimeError(f'Missing {CONFIG}')
    return json.loads(CONFIG.read_text(encoding='utf-8-sig'))

def local_ip():
    try:
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.connect(('1.1.1.1',80)); ip=s.getsockname()[0]; s.close(); return ip
    except Exception: return ''

def heartbeat(cfg):
    payload=json.dumps({
        'device_id':cfg['device_id'],
        'token':cfg['token'],
        'hostname':socket.gethostname(),
        'ip_address':local_ip(),
        'os':platform.platform(),
        'agent_version':cfg.get('agent_version',VERSION)
    }).encode()
    req=urllib.request.Request(cfg['server'].rstrip('/')+'/api/devices/heartbeat/',data=payload,headers={'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(req,timeout=15) as r: return json.loads(r.read())

def main():
    cfg=load_config()
    while True:
        try:
            result=heartbeat(cfg)
            if result.get('approved') is not None:
                (ROOT/'status.json').write_text(json.dumps(result),encoding='utf-8')
        except Exception as exc:
            (ROOT/'last_error.txt').write_text(str(exc),encoding='utf-8')
        time.sleep(int(cfg.get('heartbeat_seconds',30)))

if __name__=='__main__': main()
