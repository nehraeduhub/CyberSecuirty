"""Offline security knowledge: what each finding means and how to fix it.

Everything here is answered locally and instantly, so the AI model only has to
summarise and reason instead of writing standard advice from scratch.
"""
import ipaddress

MITRE_NAMES = {
    "T1003": "OS Credential Dumping", "T1046": "Network Service Discovery",
    "T1053": "Scheduled Task/Job", "T1059": "Command and Scripting Interpreter",
    "T1059.001": "PowerShell", "T1059.004": "Unix Shell", "T1059.007": "JavaScript",
    "T1070": "Indicator Removal", "T1070.001": "Clear Windows Event Logs",
    "T1078": "Valid Accounts", "T1078.003": "Local Accounts", "T1083": "File and Directory Discovery",
    "T1098": "Account Manipulation", "T1105": "Ingress Tool Transfer", "T1110": "Brute Force",
    "T1110.001": "Password Guessing", "T1110.003": "Password Spraying", "T1136": "Create Account",
    "T1190": "Exploit Public-Facing Application", "T1496": "Resource Hijacking",
    "T1548.003": "Sudo and Sudo Caching", "T1595": "Active Scanning",
    "T1595.003": "Wordlist Scanning", "T1021.004": "Remote Services: SSH",
    "T1068": "Exploitation for Privilege Escalation", "T1562.004": "Disable or Modify System Firewall",
    "T1543.002": "Systemd Service", "T1574": "Hijack Execution Flow",
    "T1222": "File and Directory Permissions Modification", "T1548": "Abuse Elevation Control Mechanism",
    "T1071": "Application Layer Protocol",
}

_ATTACK = "https://attack.mitre.org/techniques/"

# rule id -> category, description, impact, recommendation, references
KB = {
    "web_sqli": ("Web Attack", "Requests contain SQL syntax (UNION SELECT, OR 1=1, SLEEP) injected into parameters.",
                 "If the application is vulnerable, the attacker can read or modify the database, steal credentials or bypass login.",
                 "Use parameterised queries everywhere, validate input, run the DB with least privilege, and put a WAF (ModSecurity + OWASP CRS) in front. Check responses with status 200/500 for these requests to see whether any succeeded.",
                 ["OWASP A03:2021 Injection", "CWE-89"]),
    "web_xss": ("Web Attack", "Requests contain HTML/JavaScript payloads (<script>, onerror=, javascript:).",
                "Stored or reflected XSS lets an attacker run script in users' browsers, steal sessions or deface pages.",
                "Encode all output, add a strict Content-Security-Policy, set HttpOnly/SameSite on cookies, and validate input.",
                ["OWASP A03:2021 Injection", "CWE-79"]),
    "web_traversal": ("Web Attack", "Requests or commands try to read sensitive files using ../ sequences or direct paths (/etc/passwd, win.ini).",
                      "Successful traversal exposes configuration, source code, keys and password hashes.",
                      "Never build file paths from user input; resolve and check paths against an allow-list; run the web server without read access to system files.",
                      ["OWASP A01:2021 Broken Access Control", "CWE-22"]),
    "web_log4shell": ("Web Attack", "A ${jndi:...} string was sent, the Log4Shell (CVE-2021-44228) exploit pattern.",
                      "On a vulnerable Java/Log4j service this gives the attacker remote code execution.",
                      "Upgrade Log4j to 2.17.1+ on every Java service, block outbound LDAP/RMI from servers, and check for outbound connections to the address in the payload.",
                      ["CVE-2021-44228", "CWE-917"]),
    "web_cmdi": ("Web Attack", "Requests contain shell metacharacters followed by commands (; cat, | id, $(whoami)).",
                 "Command injection gives the attacker a shell on the server with the web server's privileges.",
                 "Never pass user input to a shell; use safe APIs with argument lists; validate input strictly; review responses (200) for signs of success.",
                 ["OWASP A03:2021 Injection", "CWE-78"]),
    "web_shell": ("Web Attack", "A script in an upload or static folder was called with a command parameter "
                                "(e.g. /uploads/shell.php?cmd=id), the typical use of an uploaded web shell.",
                  "If the server answered 200, the attacker can likely run commands on the web server with its privileges.",
                  "Take the site offline or block the source, preserve the file and logs, remove the shell, find the upload "
                  "path (vulnerable form or plugin) and fix it, rotate credentials stored on the server, and check for "
                  "outbound connections and new files.",
                  ["OWASP A04:2021 Insecure Design", "CWE-434", "T1505.003"]),
    "web_scanner": ("Reconnaissance", "User-Agent or request patterns match automated attack tools (sqlmap, nikto, gobuster, nuclei…).",
                    "Scanning usually precedes exploitation; the attacker is mapping weaknesses.",
                    "Rate-limit and block the source IPs, enable a WAF bot-protection rule set, and verify nothing the scanner found is actually exposed.",
                    ["MITRE T1595"]),
    "web_sensitive": ("Reconnaissance", "Probes for secret files: .env, .git, cloud credentials, wp-config, phpMyAdmin.",
                      "If any of these return 200 the attacker can obtain passwords, API keys or source code.",
                      "Deny access to dot-files and backups in the web server config, move secrets out of the web root, and rotate any secret that was ever reachable.",
                      ["OWASP A05:2021 Security Misconfiguration", "CWE-538"]),
    "web_enum": ("Reconnaissance", "One IP generated a large number of 404 responses: directory/file brute forcing.",
                 "The attacker is searching for hidden admin panels, backups and APIs.",
                 "Block or rate-limit the IP (fail2ban), remove unused files and admin panels from public access.",
                 ["MITRE T1595.003"]),
    "ssh_fail": ("Authentication", "Failed SSH password/key logins.",
                 "A few failures are normal; many from one source indicate password guessing.",
                 "Use key-based SSH only (PasswordAuthentication no), install fail2ban, and restrict SSH to trusted IPs or a VPN.",
                 ["CIS Linux 5.2", "MITRE T1110"]),
    "ssh_invalid": ("Authentication", "SSH logins for usernames that do not exist on the system.",
                    "Typical of automated username/password spraying bots.",
                    "Same as SSH brute force: disable password auth, fail2ban, and firewall SSH to known networks.",
                    ["MITRE T1110.001"]),
    "ssh_bruteforce": ("Authentication", "Many failed SSH logins from the same IP address.",
                       "Weak or reused passwords will eventually be guessed, giving full shell access.",
                       "Block the IP now, enforce key-only SSH, enable fail2ban (maxretry 3), disable root login, and check whether any login from this IP succeeded.",
                       ["CIS Linux 5.2", "MITRE T1110.001"]),
    "bruteforce_success": ("Compromise", "A successful login came from an IP that had just failed many times.",
                           "Very likely the password was guessed and the attacker now has access to the account.",
                           "Treat as an incident: disable the account / reset its password, kill its sessions (pkill -u USER), review its commands (.bash_history, auth.log, audit logs), check for persistence (cron, authorized_keys, new users, services) and isolate the host if needed.",
                           ["NIST SP 800-61r2", "MITRE T1078"]),
    "ssh_root_ok": ("Authentication", "Root logged in directly over SSH.",
                    "Direct root login removes accountability and is the most valuable target for attackers.",
                    "Set PermitRootLogin no, log in as a named user and use sudo; verify this login was expected.",
                    ["CIS Linux 5.2.10"]),
    "sudo_fail": ("Privilege Escalation", "Failed or unauthorised sudo attempts.",
                  "A user (or attacker using a compromised account) tried to gain root.",
                  "Confirm with the user; review /etc/sudoers and group membership; investigate the account if not expected.",
                  ["MITRE T1548.003"]),
    "account_create": ("Persistence", "A new user account was created or a user was added to an admin group.",
                       "Attackers create accounts to keep access after the initial break-in.",
                       "Verify the change was authorised; remove unknown accounts; check for UID 0 accounts (awk -F: '$3==0' /etc/passwd).",
                       ["MITRE T1136"]),
    "win_admin_group": ("Persistence", "An account was added to a privileged Windows group (Event 4728/4732/4756).",
                        "Gives the account administrator rights, a common persistence step.",
                        "Verify against change records; remove unauthorised members; alert on these event IDs.",
                        ["MITRE T1098"]),
    "win_log_cleared": ("Defense Evasion", "The Windows Security log was cleared (Event 1102).",
                        "Strong sign of an attacker hiding their tracks.",
                        "Treat as an incident; collect remaining evidence (other logs, EDR, SIEM copies); forward logs to a central server so they cannot be wiped locally.",
                        ["MITRE T1070.001"]),
    "win_logon_fail": ("Authentication", "Failed Windows logons (Event 4625).",
                       "Many failures indicate password guessing or spraying.",
                       "Enable account lockout policy, restrict RDP/SMB exposure, and use MFA.",
                       ["MITRE T1110"]),
    "win_bruteforce": ("Authentication", "Many failed Windows logons from one source.",
                       "Password spraying or brute force against Windows accounts.",
                       "Block the source, enforce lockout and MFA, and check for a following successful logon (Event 4624).",
                       ["MITRE T1110.003"]),
    "download_exec": ("Execution", "A file was downloaded and piped straight into a shell (curl|bash, wget|sh).",
                      "Arbitrary attacker code ran on the host, typically installing malware or a backdoor.",
                      "Isolate the host, fetch the URL in a sandbox to see what it does, look for new files, cron jobs, services and outbound connections; rebuild if in doubt.",
                      ["MITRE T1105", "MITRE T1059.004"]),
    "reverse_shell": ("Execution", "A reverse shell command (bash -i >& /dev/tcp, nc -e, socat exec) was run.",
                      "The attacker has an interactive shell on the host.",
                      "Isolate the host immediately, block the remote IP/port at the firewall, identify the process (ss -tnp) and the account used, then perform full incident response.",
                      ["MITRE T1059.004"]),
    "encoded_powershell": ("Execution", "PowerShell ran with an encoded (-enc) command.",
                           "Encoding is used to hide malicious scripts from logging and defenders.",
                           "Decode the Base64 to see the script; enable PowerShell script-block logging and Constrained Language Mode; investigate the parent process.",
                           ["MITRE T1059.001"]),
    "cred_dump": ("Credential Access", "Credential dumping tool or technique detected (mimikatz, LSASS dump, hashdump).",
                  "All passwords and hashes on the host should be considered stolen; lateral movement is likely.",
                  "Isolate the host, reset all credentials used on it (including service and domain admin accounts), enable LSA protection / Credential Guard.",
                  ["MITRE T1003"]),
    "persistence": ("Persistence", "A persistence mechanism was modified (cron, systemd, SSH authorized_keys, Run keys, scheduled tasks).",
                    "Lets the attacker survive reboots and regain access.",
                    "Review the exact entry; remove anything unknown; compare against a known-good baseline.",
                    ["MITRE T1053"]),
    "tmp_exec": ("Execution", "An executable was placed or run in a temp directory (/tmp, /dev/shm), often as a hidden dot-file.",
                 "Typical of malware droppers and crypto miners.",
                 "Inspect and hash the file, kill its process, mount /tmp and /dev/shm with noexec, and find how it got there.",
                 ["MITRE T1059"]),
    "log_tamper": ("Defense Evasion", "Logs or shell history were deleted or disabled.",
                   "Attacker is hiding activity; the logs you have are probably incomplete.",
                   "Forward logs to a remote syslog/SIEM, make logs append-only (chattr +a), and investigate the account involved.",
                   ["MITRE T1070"]),
    "crypto_miner": ("Impact", "Cryptocurrency mining software or mining-pool connections detected.",
                     "Your CPU/power is being stolen; the miner usually arrives via another compromise.",
                     "Kill the process, remove the binary and its persistence, block the pool address, and find the initial entry point.",
                     ["MITRE T1496"]),
    "port_scan": ("Reconnaissance", "One source probed many different ports (seen in firewall logs).",
                  "The attacker is discovering which services you expose.",
                  "Your firewall blocked these; make sure only required ports are open and consider blocking the source.",
                  ["MITRE T1046"]),
}

SEV_CVSS = {"critical": "9.0-10.0", "high": "7.0-8.9", "medium": "4.0-6.9", "low": "0.1-3.9", "info": "0.0"}


def enrich(finding):
    """Add category/description/impact/recommendation/references to a finding (in place)."""
    cat, desc, impact, rec, refs = KB.get(finding["id"], ("General", "", "", "", []))
    finding.setdefault("category", cat)
    finding.setdefault("description", desc)
    finding.setdefault("impact", impact)
    finding.setdefault("recommendation", rec)
    refs = list(finding.get("references") or refs)
    mitre = finding.get("mitre")
    if mitre and mitre != "-":
        finding["mitre_name"] = MITRE_NAMES.get(mitre, "")
        url = _ATTACK + mitre.replace(".", "/")
        if url not in refs:
            refs.append(url)
    finding["references"] = refs
    finding["cvss_band"] = SEV_CVSS.get(finding["severity"], "")
    return finding


_INTERNAL = [ipaddress.ip_network(n) for n in
             ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "169.254.0.0/16",
              "0.0.0.0/8", "100.64.0.0/10", "::1/128", "fe80::/10", "fc00::/7")]


def is_public_ip(ip):
    """True for addresses outside your own networks (LAN, loopback, link-local)."""
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not any(a in n for n in _INTERNAL if n.version == a.version)


def valid_ip(ip):
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


# ------------------------------------------------------------------ instant answers

def block_commands(ips):
    """Firewall commands to block the given IPs on common platforms."""
    ips = [ip for ip in ips if valid_ip(ip)]
    if not ips:
        return "No attacker IP addresses to block."
    lines = ["### Linux - UFW", "```bash"] + [f"sudo ufw insert 1 deny from {ip}" for ip in ips] + ["```",
             "### Linux - iptables", "```bash"] + [f"sudo iptables -I INPUT -s {ip} -j DROP" for ip in ips] + [
             "sudo netfilter-persistent save   # keep after reboot", "```",
             "### Linux - nftables", "```bash",
             "sudo nft add table inet blocklist",
             "sudo nft 'add set inet blocklist bad { type ipv4_addr; }'",
             "sudo nft 'add chain inet blocklist input { type filter hook input priority -10; }'",
             "sudo nft add rule inet blocklist input ip saddr @bad drop",
             f"sudo nft add element inet blocklist bad {{ {', '.join(ips)} }}", "```",
             "### Linux - fail2ban (permanent ban)", "```bash"] + [
             f"sudo fail2ban-client set sshd banip {ip}" for ip in ips] + ["```",
             "### Windows Firewall (PowerShell, as Administrator)", "```powershell",
             f'New-NetFirewallRule -DisplayName "Block attackers" -Direction Inbound -Action Block -RemoteAddress {",".join(ips)}',
             "```"]
    return "\n".join(lines)


def iocs_markdown(result):
    i = result.get("iocs", {})
    parts = []
    for key, title in (("ips", "Malicious IP addresses"), ("urls", "URLs"), ("domains", "Domains"),
                       ("files", "Suspicious files"), ("users", "Targeted / affected accounts")):
        if i.get(key):
            parts.append(f"### {title}\n```\n" + "\n".join(i[key]) + "\n```")
    return "\n".join(parts) or "No indicators of compromise were extracted."


def playbook_markdown(result):
    """Prioritised response plan built from the findings - no AI needed."""
    f = result.get("findings", [])
    if not f:
        return "No findings - no response actions required. Keep monitoring."
    buckets = [("🔴 Immediate (now - 24 h)", ("critical",)), ("🟠 Today / this week", ("high",)),
               ("🟡 This month", ("medium",)), ("🔵 Hardening backlog", ("low", "info"))]
    out = []
    for title, sevs in buckets:
        items = [x for x in f if x["severity"] in sevs]
        if items:
            out.append(f"### {title}")
            out += [f"- **{x['title']}**: {x.get('recommendation') or 'Review and verify.'}" for x in items]
    bad = [p["ip"] for p in result.get("ip_profiles", []) if p["verdict"] in ("Malicious", "Suspicious")
           and p.get("public")]
    if bad:
        out.append(f"\n**Block these source IPs:** {', '.join(bad)}  (ask: *Block IPs* for commands)")
    return "\n".join(out)


def explain_markdown(finding):
    enrich(finding)
    ips = ", ".join(finding.get("ips", [])[:10]) or "n/a"
    sample = finding["samples"][0]["text"] if finding.get("samples") else ""
    return (f"### {finding['title']}  `{finding['severity'].upper()}`\n"
            f"**MITRE ATT&CK:** {finding.get('mitre', '-')} {finding.get('mitre_name', '')}  \n"
            f"**Events:** {finding.get('count', 1)}  **Sources:** {ips}\n\n"
            f"**What it is:** {finding.get('description')}\n\n"
            f"**Impact:** {finding.get('impact')}\n\n"
            f"**What to do:** {finding.get('recommendation')}\n\n"
            + (f"**Evidence:**\n```\n{sample}\n```" if sample else ""))
