"""Forensic view of an analysis: one tab per attack type.

Each tab answers, for the findings of that type:
  * what kind of attack it is (and how it usually works)
  * what happened in these logs: findings, the action each device took, the systems involved
  * what to determine next (investigation questions)
  * forensic steps in order: preserve -> collect -> analyse -> scope
  * read-only collection commands for Linux and Windows (nothing here changes a system)
  * containment ideas and further suggestions - recommendations only, for an authorised person to decide

The playbooks are offline knowledge; everything about *this* case comes from the analysis itself.
"""
from collections import Counter

GENERAL_STEPS = [
    "Record who is handling the evidence, when, and why (chain of custody) before touching any system.",
    "Preserve the original log files: keep the stored copies (History page records their SHA-256) and export "
    "the same period again from the SIEM so the two can be compared.",
    "Check time sources: note each system's clock offset and time zone so the timeline lines up (UTC is used here).",
    "Collect volatile data first (memory, running processes, network connections) before rebooting or isolating "
    "a host, if your procedure allows it.",
    "Work on copies: image disks or copy artefacts to read-only storage and hash them (sha256sum / Get-FileHash).",
    "Keep notes of every command run and every finding, with time stamps, for the report.",
]

PLAYBOOKS = {
    "credential": {
        "title": "Brute force & credential attacks", "icon": "🔑",
        "categories": ("Authentication", "Credential Access", "Compromise"),
        "rule_prefixes": ("TG-AUTH", "TG-WIN", "TG-VPN", "TG-CRED"),
        "attack_type": "Password guessing, password spraying, credential stuffing or theft of credentials "
                       "(e.g. LSASS dumping). A success after many failures usually means the password was guessed; "
                       "a valid logon from an unusual place can mean stolen credentials.",
        "questions": ["Did any guessed or stolen account log on successfully, and from where?",
                      "Which accounts were targeted, and were any of them privileged or service accounts?",
                      "Was MFA in place, and was it bypassed?",
                      "What did each compromised account do after logging on?"],
        "steps": ["List every successful logon of the targeted accounts in the attack window (4624 / 'Accepted').",
                  "Compare source IPs and hosts with each account's normal pattern (see UEBA).",
                  "Check for credential-dumping artefacts on hosts where the attacker ran code (LSASS access, mimikatz strings).",
                  "Trace the sessions forward: processes, file access, lateral movement from those logons.",
                  "Identify every system where the compromised credentials are valid (domain, VPN, SaaS)."],
        "commands": {
            "Linux": ["sudo grep -E 'Failed password|Accepted|Invalid user' /var/log/auth.log* | less",
                      "last -Fiw | head -50; sudo lastb -Fiw | head -50",
                      "sudo journalctl _COMM=sshd --since '2 days ago' --no-pager"],
            "Windows": ["Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4624,4625,4648,4740,4771,4776} -MaxEvents 2000 | Export-Csv logons.csv -NoTypeInformation",
                        "Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4672} -MaxEvents 500 | Format-List TimeCreated,Message",
                        "wevtutil epl Security C:\\IR\\Security.evtx   (export a copy of the log)"]},
        "containment": ["Reset the passwords of accounts that logged on after the attack and revoke their sessions/tokens.",
                        "Block or rate-limit the attacking source addresses at the perimeter or VPN.",
                        "Enforce MFA on VPN, remote access and admin accounts."],
        "suggestions": ["Enable account lockout / smart lockout and alert on password spraying.",
                        "Remove internet-facing password logins where possible (SSH keys, VPN with certificates).",
                        "Check the passwords against breached-password lists."],
    },
    "web": {
        "title": "Web attacks & exploitation", "icon": "🌐",
        "categories": ("Web Attack",), "rule_prefixes": ("TG-WEB", "TG-API"),
        "attack_type": "Attacks against a web application: SQL injection, command injection, path traversal, Log4Shell, "
                       "file upload leading to a web shell, scanners and directory brute force. An HTTP 200 to an "
                       "attack request means the server answered it - exploitation is possible and must be checked on "
                       "the server.",
        "questions": ["Which requests succeeded (2xx) or reached the application (5xx)?",
                      "Was a file uploaded or created in the web root, and is it still there?",
                      "Did the web server process start a shell or make outbound connections?",
                      "Was data read from the database (response sizes, DB logs)?"],
        "steps": ["Preserve the web server, application and WAF logs, and a copy of the web root.",
                  "List files in the web root created or changed during and after the attack window.",
                  "Hash and copy any suspicious script (web shell) before removing it; do not open it in a browser.",
                  "Review child processes of the web server user (www-data, IIS AppPool) and its outbound connections.",
                  "Check database logs for queries matching the injected payloads and large result sets.",
                  "Find the upload / injection point (vulnerable form, plugin, endpoint) and the first successful request."],
        "commands": {
            "Linux": ["sudo find /var/www -type f -newermt '2 days ago' -ls",
                      "sudo find /var/www -name '*.php' -exec grep -lE 'eval\\(|base64_decode|system\\(|shell_exec|passthru' {} +",
                      "sudo grep -E 'shell\\.php|cmd=|UNION|%27|\\.\\./' /var/log/apache2/access.log* /var/log/nginx/access.log*",
                      "ps -eo user,pid,ppid,lstart,cmd --forest | grep -A3 -E 'www-data|apache|nginx'",
                      "sudo ss -tnp | grep -E 'www-data|apache|nginx|php'"],
            "Windows": ["Get-ChildItem C:\\inetpub\\wwwroot -Recurse -File | Where-Object LastWriteTime -gt (Get-Date).AddDays(-2)",
                        "Select-String -Path C:\\inetpub\\logs\\LogFiles\\*\\*.log -Pattern 'cmd=|UNION|%27|\\.\\./'",
                        "Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -in (Get-Process w3wp).Id } | Select ProcessId,CommandLine"]},
        "containment": ["Take the affected site offline or put it behind a blocking WAF rule while investigating.",
                        "Remove the web shell only after it has been copied and hashed; rotate secrets stored on the server.",
                        "Patch or disable the vulnerable component."],
        "suggestions": ["Disable script execution in upload folders and validate uploaded file types server-side.",
                        "Use parameterised queries; add WAF rules for the payloads seen.",
                        "Alert on web-server processes spawning shells (EDR / auditd)."],
    },
    "recon": {
        "title": "Reconnaissance & scanning", "icon": "🔭",
        "categories": ("Reconnaissance",), "rule_prefixes": ("TG-NET-001",),
        "attack_type": "Port scans, service discovery and vulnerability scanning. Usually the first stage of an attack; "
                       "what matters is which ports the firewall let through and what happened on them next.",
        "questions": ["Which ports were allowed through the firewall, and which services answer on them?",
                      "Did the same source attack any of those services afterwards?",
                      "Is the source an approved scanner or penetration test?"],
        "steps": ["List the allowed ports for the scanning source (Action taken column / port-scan details).",
                  "Check the services on those ports for known vulnerabilities and for logs of the same source.",
                  "Confirm with the owner whether the scan was authorised (pentest window, scanner inventory)."],
        "commands": {
            "Linux": ["sudo grep '<attacker ip>' /var/log/ufw.log /var/log/syslog* | head",
                      "sudo ss -tlnp   (which services are listening)"],
            "Windows": ["Get-NetTCPConnection -State Listen | Select LocalAddress,LocalPort,OwningProcess",
                        "Get-WinEvent -LogName 'Microsoft-Windows-Windows Firewall With Advanced Security/Firewall' -MaxEvents 500"]},
        "containment": ["Block the scanning source if it is not authorised.",
                        "Close or restrict ports that do not need to be reachable from the internet."],
        "suggestions": ["Keep an inventory of approved scanners in Trusted Networks & Assets.",
                        "Review the perimeter rule base for unnecessary exposure."],
    },
    "malware": {
        "title": "Malware & malicious execution", "icon": "🦠",
        "categories": ("Execution", "Impact"), "rule_prefixes": ("TG-EXE", "TG-MAL"),
        "attack_type": "Malicious code running on a host: encoded PowerShell, download cradles, reverse shells, "
                       "credential dumpers, crypto miners and ransomware preparation (deleting shadow copies).",
        "questions": ["Which process started it (parent), as which user, and when?",
                      "What was downloaded and from where? Is the file still on disk?",
                      "Did it create persistence or connect out?",
                      "Is the same file or command present on other hosts?"],
        "steps": ["Capture memory and the running process list of the affected host before shutting it down.",
                  "Collect the process tree, command lines and loaded modules around the execution time.",
                  "Copy and hash the files named in the commands (e.g. C:\\Users\\Public\\*.exe, /tmp/*).",
                  "Search all hosts for the same hash, file name and command line.",
                  "Review PowerShell script-block logs (4104) and Sysmon / EDR telemetry for the full sequence."],
        "commands": {
            "Linux": ["ps -eo user,pid,ppid,lstart,cmd --forest",
                      "sudo ls -la /tmp /var/tmp /dev/shm; sudo find / -xdev -newermt '2 days ago' -type f -perm -u+x 2>/dev/null",
                      "sudo sha256sum <suspicious file>; sudo ss -tnp"],
            "Windows": ["Get-CimInstance Win32_Process | Select ProcessId,ParentProcessId,CreationDate,CommandLine | Export-Csv procs.csv",
                        "Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-PowerShell/Operational'; Id=4104} -MaxEvents 500",
                        "Get-FileHash C:\\Users\\Public\\*.exe -Algorithm SHA256",
                        "vssadmin list shadows   (check whether shadow copies still exist)"]},
        "containment": ["Isolate the host from the network (EDR isolation or switch port) after volatile data is captured.",
                        "Block the download URLs, domains and hashes on proxy, DNS and EDR."],
        "suggestions": ["Enable PowerShell script-block logging, constrained language mode and AMSI.",
                        "Use application allow-listing for user-writable folders.",
                        "Keep offline backups and test restoring them."],
    },
    "persistence": {
        "title": "Persistence & privilege changes", "icon": "📌",
        "categories": ("Persistence", "Privilege Escalation"), "rule_prefixes": ("TG-PER", "TG-IAM", "TG-LNX"),
        "attack_type": "Ways an attacker keeps access or gains rights: new accounts, group membership changes, "
                       "services, scheduled tasks, cron jobs, SSH keys and sudo abuse.",
        "questions": ["Which accounts, groups, services, tasks or keys were created or changed, and by whom?",
                      "Do they still exist, and have they been used since?",
                      "Were the same changes made on other hosts?"],
        "steps": ["List new and changed accounts and group memberships in the attack window.",
                  "Export services, scheduled tasks, cron jobs, startup items and authorized_keys from affected hosts.",
                  "Hash and copy the binaries they point to before removing anything.",
                  "Check whether the persistence was triggered (logons of the new account, task runs)."],
        "commands": {
            "Linux": ["sudo cat /etc/passwd /etc/group | tail -30; sudo ls -la /home/*/.ssh /root/.ssh",
                      "sudo ls -la /etc/cron* /var/spool/cron/crontabs; systemctl list-unit-files --state=enabled",
                      "sudo grep -E 'useradd|usermod|sudo' /var/log/auth.log*"],
            "Windows": ["Get-LocalUser; Get-LocalGroupMember Administrators",
                        "Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4720,4722,4728,4732,4756,4698} -MaxEvents 500",
                        "Get-ScheduledTask | Where-Object { $_.Date -gt (Get-Date).AddDays(-7) }",
                        "Get-CimInstance Win32_Service | Select Name,State,StartMode,PathName"]},
        "containment": ["Disable (do not yet delete) accounts and tasks created by the attacker, after collecting them.",
                        "Remove unauthorised group memberships and SSH keys."],
        "suggestions": ["Alert on changes to privileged groups and on new services / scheduled tasks.",
                        "Review who may create accounts; use just-in-time admin rights."],
    },
    "lateral": {
        "title": "Lateral movement", "icon": "↔️",
        "categories": ("Lateral Movement",), "rule_prefixes": ("TG-LAT",),
        "attack_type": "Moving from one machine to others with stolen credentials: SMB, RDP, WinRM, PsExec, SSH. "
                       "One source logging on to many hosts in a short time is the typical sign.",
        "questions": ["Which hosts were reached from the compromised machine, with which accounts?",
                      "What was done on each of them (processes, services, file access)?",
                      "Are there hosts reached that have no logs here (coverage gap)?"],
        "steps": ["Build the list of target hosts from the attack flow and confirm each logon on the target.",
                  "Collect process creation, service installation and share access on every target host.",
                  "Check administrative shares (ADMIN$, C$) and remote-execution artefacts (PsExec service, WinRM logs).",
                  "Extend the scope: repeat the investigation for each newly identified host."],
        "commands": {
            "Linux": ["sudo grep -E 'Accepted' /var/log/auth.log* | awk '{print $9, $11}' | sort | uniq -c"],
            "Windows": ["Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4624} | Where-Object { $_.Properties[8].Value -in 3,10 }",
                        "Get-WinEvent -FilterHashtable @{LogName='System'; Id=7045} -MaxEvents 200",
                        "Get-WinEvent -FilterHashtable @{LogName='Security'; Id=5140,5145} -MaxEvents 500"]},
        "containment": ["Reset the credentials used for the movement and isolate the source host.",
                        "Restrict SMB/RDP between workstations with host firewalls."],
        "suggestions": ["Use LAPS / unique local admin passwords and tiered admin accounts.",
                        "Alert on one account logging on to many hosts in a short time."],
    },
    "c2": {
        "title": "Command & control", "icon": "📡",
        "categories": ("Command and Control",), "rule_prefixes": ("TG-C2", "TG-DNS"),
        "attack_type": "Malware talking to the attacker: regular beaconing to an external server, DNS tunnelling, "
                       "domain-generation (many NXDOMAIN answers) and connections to known C2 addresses.",
        "questions": ["Which internal hosts talk to the C2 address or domain, since when?",
                      "Which process on the host makes the connections?",
                      "How much data was sent?"],
        "steps": ["Identify the process behind the connections on each host (netstat / EDR network events).",
                  "Collect proxy, firewall and DNS logs for the C2 indicators across the whole estate.",
                  "Capture traffic (pcap) to the C2 address if it is still active and your policy allows it.",
                  "Add the indicators to the local IoC feed (mark the finding as true positive)."],
        "commands": {
            "Linux": ["sudo ss -tnp | grep <c2 ip>", "sudo tcpdump -nn -w c2.pcap host <c2 ip>   (only if authorised)"],
            "Windows": ["Get-NetTCPConnection -RemoteAddress <c2 ip> | Select OwningProcess,State,CreationTime",
                        "Get-DnsClientCache | Where-Object Entry -like '*<domain>*'"]},
        "containment": ["Block the C2 addresses and domains at firewall, proxy and DNS (sinkhole).",
                        "Isolate hosts that beacon, after capturing volatile data."],
        "suggestions": ["Force outbound traffic through a proxy; alert on DNS TXT volume and long labels.",
                        "Use DNS filtering with threat-intelligence feeds."],
    },
    "exfil": {
        "title": "Data theft & exfiltration", "icon": "📤",
        "categories": ("Exfiltration", "Collection"), "rule_prefixes": ("TG-EXF", "TG-DB"),
        "attack_type": "Collecting data (database dumps, archives with passwords) and sending it out - large uploads, "
                       "unusual destinations or tunnels.",
        "questions": ["What data was collected (tables, files) and how sensitive is it?",
                      "How much left the network, to where, and when?",
                      "Are there legal or regulatory notification duties?"],
        "steps": ["Identify the collected files (archive names, export paths) and preserve them if still present.",
                  "Quantify the transfer from firewall/proxy byte counts per destination.",
                  "Check database audit logs for the export queries and the account used.",
                  "Inform the data owner and legal/compliance about a possible breach."],
        "commands": {
            "Linux": ["sudo find / -xdev -newermt '2 days ago' \\( -name '*.zip' -o -name '*.7z' -o -name '*.tar*' -o -name '*.bak' \\) -ls 2>/dev/null"],
            "Windows": ["Get-ChildItem D:\\ -Recurse -Include *.7z,*.zip,*.bak -ErrorAction SilentlyContinue | Where-Object LastWriteTime -gt (Get-Date).AddDays(-2)",
                        "Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4663} -MaxEvents 1000   (object access, if auditing is on)"]},
        "containment": ["Block the exfiltration destination and disable the account used.",
                        "Rotate credentials that may have been in the stolen data."],
        "suggestions": ["Add DLP / egress volume alerts per host and destination.",
                        "Restrict database export tools and audit large queries."],
    },
    "evasion": {
        "title": "Defence evasion & anti-forensics", "icon": "🧹",
        "categories": ("Defense Evasion", "Forensics"), "rule_prefixes": ("TG-FOR",),
        "attack_type": "Hiding tracks: clearing event logs, changing audit policy, disabling security tools, deleting "
                       "history, firewall rule changes, gaps in logging.",
        "questions": ["Which logs were cleared or stopped, and for which period is evidence missing?",
                      "Who made the change, from which machine?",
                      "Are copies of the lost logs available elsewhere (SIEM, backups, forwarders)?"],
        "steps": ["Preserve everything still present on the host immediately - the attacker is destroying evidence.",
                  "Recover the missing period from the SIEM, log forwarders, backups or volume shadow copies.",
                  "Review the audit-policy and firewall changes and restore the approved configuration.",
                  "Treat the host as compromised even if other evidence is missing."],
        "commands": {
            "Linux": ["sudo ls -la /var/log; sudo journalctl --verify", "cat ~/.bash_history; sudo ls -la /root/.bash_history"],
            "Windows": ["Get-WinEvent -FilterHashtable @{LogName='Security'; Id=1102,4719} ; Get-WinEvent -FilterHashtable @{LogName='System'; Id=104}",
                        "auditpol /get /category:*"]},
        "containment": ["Restore audit policy and logging; forward logs off the host so they cannot be wiped locally."],
        "suggestions": ["Alert on 1102/104/4719 and on gaps in log flow from each source.",
                        "Protect log forwarders and the SIEM from administrator accounts used on endpoints."],
    },
    "ueba": {
        "title": "Unusual behaviour (UEBA)", "icon": "👤",
        "categories": ("UEBA", "Anomaly"), "rule_prefixes": ("TG-UEBA",),
        "attack_type": "Behaviour that differs from an account's own history or its peers: new source, new host, "
                       "unusual hour, first-time privilege use. Not an attack by itself, but a strong lead.",
        "questions": ["Can the user or their manager explain the activity?",
                      "Does it coincide with other findings for the same account?"],
        "steps": ["Contact the account owner through a trusted channel (not email from the account).",
                  "Compare the session with the account's baseline shown in the UEBA table.",
                  "Mark the finding as benign or true positive so the agent learns."],
        "commands": {"Linux": ["last -Fiw <user>"], "Windows": ["Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4624} | Where-Object { $_.Message -match '<user>' }"]},
        "containment": ["Temporarily require re-authentication / MFA for the account if the owner cannot explain it."],
        "suggestions": ["Keep baselines learning from normal weeks (Settings → Learn UEBA baselines)."],
    },
    "intel": {
        "title": "Threat intelligence & sensor alerts", "icon": "🛰️",
        "categories": ("Threat Intelligence", "Detection"), "rule_prefixes": ("TG-TI", "TG-IDS"),
        "attack_type": "Matches with known-bad indicators (IoC feeds, learned indicators, reputation) and alerts "
                       "raised by IDS/IPS or EDR. An IDS alert is detection only - the traffic was not necessarily blocked.",
        "questions": ["Which internal hosts communicated with the indicator, and was it allowed?",
                      "Is the indicator still active, and how reliable is the feed?"],
        "steps": ["Check the firewall/proxy action for each match (Action taken column).",
                  "Look up the indicator's reputation (Reputation card) and the feed's description.",
                  "Investigate each internal host involved as in the C2 / malware tabs."],
        "commands": {"Linux": ["sudo grep -r '<indicator>' /var/log/ 2>/dev/null | head"],
                     "Windows": ["Select-String -Path C:\\Windows\\System32\\LogFiles\\Firewall\\pfirewall.log -Pattern '<indicator>'"]},
        "containment": ["Block confirmed malicious indicators on firewall, proxy, DNS and EDR."],
        "suggestions": ["Keep IoC feeds current (config/ioc/) and switch IDS rules that fire on real attacks to prevention."],
    },
    "other": {
        "title": "Other findings", "icon": "🧩", "categories": (), "rule_prefixes": (),
        "attack_type": "Findings that do not fit the categories above.",
        "questions": ["Is the activity expected for this system?"],
        "steps": ["Review each finding's evidence and recommendation."],
        "commands": {}, "containment": [], "suggestions": [],
    },
}
ORDER = ["web", "credential", "recon", "malware", "persistence", "lateral", "c2", "exfil", "evasion", "intel", "ueba", "other"]
SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def group_of(f):
    """Web rules always go to the web tab; otherwise the ATT&CK-style category decides, then the rule family."""
    rid = str(f.get("rule_id") or "")
    if rid.startswith(PLAYBOOKS["web"]["rule_prefixes"]):
        return "web"
    cat = f.get("category") or ""
    for key in ORDER:
        if cat in PLAYBOOKS[key]["categories"]:
            return key
    for key in ORDER:
        if any(rid.startswith(p) for p in PLAYBOOKS[key]["rule_prefixes"]):
            return key
    return "other"


def view(result):
    """Tabs for the Forensics page / report, built from the analysis."""
    findings = result.get("findings") or []
    trusted = set((result.get("iocs") or {}).get("trusted") or [])
    groups = {}
    for f in findings:
        groups.setdefault(group_of(f), []).append(f)
    tabs = []
    for key in ORDER:
        fs = groups.get(key)
        if not fs:
            continue
        pb = PLAYBOOKS[key]
        fs = sorted(fs, key=lambda f: (SEV_RANK.get(f["severity"], 9), -(f.get("risk") or {}).get("score", 0)))
        acts = Counter()
        for f in fs:
            for a in f.get("actions_taken") or []:
                acts[(a["by"], a["action"], a["result"])] += a.get("count", 1)
        ips = sorted({ip for f in fs for ip in f.get("ips") or []})
        recs = []
        for f in fs:
            r = (f.get("recommendation") or "").strip()
            if r and r not in recs:
                recs.append(r)
        first = [f.get("first_seen") for f in fs if f.get("first_seen")]
        last = [f.get("last_seen") or f.get("first_seen") for f in fs if f.get("first_seen")]
        tabs.append({
            "key": key, "title": pb["title"], "icon": pb["icon"], "severity": fs[0]["severity"],
            "count": len(fs), "events": sum(f.get("count", 1) for f in fs),
            "window": [min(first) if first else None, max(last) if last else None],
            "attack_type": pb["attack_type"],
            "techniques": sorted({t for f in fs for t in f.get("mitre_list") or []}),
            "findings": [{k: f.get(k) for k in ("fid", "title", "severity", "confidence", "count", "rule_id", "first_seen",
                                                "last_seen", "incident", "recommendation", "evidence", "actions_taken",
                                                "analyst_verdict", "description", "impact")} for f in fs],
            "actions": [{"by": b, "action": a, "result": r, "count": c} for (b, a, r), c in acts.most_common(10)],
            "scope": {"attacker_ips": [i for i in ips if i not in trusted][:20], "your_assets": [i for i in ips if i in trusted][:20],
                      "accounts": sorted({u for f in fs for u in f.get("users") or []})[:20],
                      "hosts": sorted({h for f in fs for h in f.get("hosts") or []})[:20]},
            "recommendations": recs[:8], "questions": pb["questions"], "steps": pb["steps"],
            "commands": pb["commands"], "containment": pb["containment"], "suggestions": pb["suggestions"],
        })
    return {"tabs": tabs, "general_steps": GENERAL_STEPS,
            "incidents": [{"id": i["id"], "title": i["title"], "severity": i["severity"], "status": i.get("status"),
                           "attack_path": i.get("attack_path"), "diagram": i.get("diagram")}
                          for i in result.get("incidents") or [] if i.get("diagram")]}


def markdown(result):
    v = view(result)
    out = ["## Forensic guide", "", "**Evidence handling first:**"] + [f"- {s}" for s in v["general_steps"]]
    for t in v["tabs"]:
        out += ["", f"### {t['icon']} {t['title']} — {t['count']} finding(s), highest {t['severity']}",
                t["attack_type"], "", "**Findings:** " + "; ".join(f"{f['fid']} {f['title']}" for f in t["findings"][:8])]
        if t["actions"]:
            out.append("**What the devices did:** " + "; ".join(f"{a['by']}: {a['action']} x{a['count']}" for a in t["actions"][:5]))
        out += ["", "**Forensic steps:**"] + [f"{n}. {s}" for n, s in enumerate(t["steps"], 1)]
        for osname, cmds in t["commands"].items():
            out += [f"\n*{osname} (read-only):*", "```"] + cmds + ["```"]
    return "\n".join(out)
