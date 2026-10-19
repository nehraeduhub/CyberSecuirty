"""Live Linux host security audit (read-only).

Checks the machine the agent runs on and returns findings in the same format
as detector.analyze(), so the UI, AI and PDF report treat both the same way.
Runs without root, but root (sudo) can read more: shadow, sudoers, all crontabs,
process owners and firewall state.
"""
import glob
import os
import platform
import re
import shutil
import socket
import stat
import subprocess
import time

import detector
import knowledge

LOG_FILES = ["/var/log/auth.log", "/var/log/secure", "/var/log/syslog", "/var/log/messages",
             "/var/log/nginx/access.log", "/var/log/apache2/access.log", "/var/log/httpd/access_log",
             "/var/log/ufw.log", "/var/log/kern.log"]
LOG_TAIL_BYTES = 8 * 1024 * 1024  # last 8 MB of each log keeps the audit fast

# Services that should never listen on all interfaces without a good reason
RISKY_PORTS = {
    21: ("FTP", "high"), 23: ("Telnet", "critical"), 69: ("TFTP", "high"), 111: ("rpcbind", "medium"),
    139: ("NetBIOS/SMB", "high"), 445: ("SMB", "high"), 512: ("rexec", "critical"), 513: ("rlogin", "critical"),
    2375: ("Docker API (no TLS)", "critical"), 3306: ("MySQL", "high"), 3389: ("RDP", "high"),
    5432: ("PostgreSQL", "high"), 5900: ("VNC", "high"), 6379: ("Redis", "critical"),
    8787: ("CyberSec AI Agent", "medium"), 9200: ("Elasticsearch", "high"), 11211: ("Memcached", "high"),
    11434: ("Ollama API", "high"), 27017: ("MongoDB", "critical"),
}
SUSPICIOUS_REMOTE_PORTS = {4444: "Metasploit default", 1337: "common backdoor", 3333: "mining pool",
                           5555: "common backdoor", 6667: "IRC botnet C2", 14444: "mining pool"}
MALWARE_NAMES = re.compile(r"xmrig|kdevtmpfsi|kinsing|minerd|cpuminer|\.kworker|tsunami|mirai|ncat|socat", re.I)
KNOWN_SUID = {"passwd", "sudo", "su", "mount", "umount", "chsh", "chfn", "newgrp", "gpasswd", "pkexec",
              "ping", "ping6", "fusermount", "fusermount3", "ssh-keysign", "dbus-daemon-launch-helper",
              "polkit-agent-helper-1", "Xorg.wrap", "unix_chkpwd", "pam_timestamp_check", "at", "crontab",
              "newuidmap", "newgidmap", "chage", "expiry", "ntfs-3g", "snap-confine", "staprun",
              "mount.nfs", "mount.cifs", "userhelper", "vmware-user-suid-wrapper", "write", "wall",
              "ssh-agent", "dotlockfile", "lockdev", "usernetctl", "traceroute6.iputils", "sg",
              "chrome-sandbox", "Xorg", "suexec", "exim4", "procmail", "mtr-packet", "bwrap"}
SYSCTL_CHECKS = [
    ("kernel/randomize_va_space", "2", "medium", "ASLR is not fully enabled"),
    ("net/ipv4/tcp_syncookies", "1", "low", "TCP SYN cookies disabled (SYN-flood protection)"),
    ("net/ipv4/conf/all/accept_redirects", "0", "low", "ICMP redirects accepted"),
    ("net/ipv4/conf/all/send_redirects", "0", "low", "Host sends ICMP redirects"),
    ("net/ipv4/conf/all/accept_source_route", "0", "medium", "Source-routed packets accepted"),
    ("net/ipv4/conf/all/rp_filter", "1", "low", "Reverse-path filtering disabled (IP spoofing protection)"),
    ("kernel/kptr_restrict", "1", "low", "Kernel pointers exposed to users"),
    ("kernel/dmesg_restrict", "1", "low", "Unprivileged users can read the kernel log"),
    ("fs/protected_symlinks", "1", "medium", "Symlink protection disabled"),
    ("fs/suid_dumpable", "0", "low", "SUID programs can write core dumps"),
]


class Audit:
    def __init__(self):
        self.findings = []
        self.checks = []
        self.is_root = hasattr(os, "geteuid") and os.geteuid() == 0

    def add(self, fid, title, severity, mitre, evidence, description, recommendation,
            impact="", category="Configuration", references=None, count=1):
        ev = evidence if isinstance(evidence, list) else [evidence]
        self.findings.append(knowledge.enrich({
            "id": fid, "title": title, "severity": severity, "mitre": mitre, "count": count,
            "ips": [], "category": category, "description": description, "impact": impact,
            "recommendation": recommendation, "references": references or [],
            "samples": [{"line": None, "text": str(e)[:300]} for e in ev[:8]],
            "first_seen": None, "last_seen": None,
        }))


def _read(path, limit=None):
    try:
        with open(path, "rb") as fh:
            if limit:
                fh.seek(0, os.SEEK_END)
                fh.seek(max(0, fh.tell() - limit))
            return fh.read().decode("utf-8", errors="replace")
    except OSError:
        return None


def _run(cmd, timeout=15):
    if not shutil.which(cmd[0]):
        return None
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.stdout + p.stderr
    except (OSError, subprocess.TimeoutExpired):
        return None


def host_info():
    osr = _read("/etc/os-release") or ""
    m = re.search(r'^PRETTY_NAME="?([^"\n]+)', osr, re.M)
    mem = _read("/proc/meminfo") or ""
    mt = re.search(r"MemTotal:\s+(\d+)", mem)
    up = (_read("/proc/uptime") or "0").split()[0]
    return {
        "hostname": socket.gethostname(), "os": m.group(1) if m else platform.platform(),
        "kernel": platform.release(), "arch": platform.machine(), "cpus": os.cpu_count(),
        "ram_gb": round(int(mt.group(1)) / 1024 / 1024, 1) if mt else None,
        "uptime_days": round(float(up) / 86400, 1),
        "audited_as": "root" if hasattr(os, "geteuid") and os.geteuid() == 0 else "standard user",
    }


# ------------------------------------------------------------------ checks

def check_ssh(a):
    a.checks.append("SSH server configuration (sshd_config)")
    text = ""
    for f in ["/etc/ssh/sshd_config"] + sorted(glob.glob("/etc/ssh/sshd_config.d/*.conf")):
        text += (_read(f) or "") + "\n"
    if not text.strip():
        return
    # sshd uses the FIRST value it sees for each keyword (drop-ins are included first)
    conf = {}
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line.lower().startswith("match "):
            break
        parts = line.split(None, 1)
        if len(parts) == 2:
            conf.setdefault(parts[0].lower(), parts[1].strip().lower())
    root = conf.get("permitrootlogin", "prohibit-password")
    if root == "yes":
        a.add("ssh_root_login", "SSH allows direct root login with password", "high", "T1021.004",
              "PermitRootLogin yes", "Root can log in over SSH with a password.",
              "Set 'PermitRootLogin no' in /etc/ssh/sshd_config and restart sshd.",
              "Attackers can brute-force the most powerful account directly.", references=["CIS Linux 5.2.10"])
    if conf.get("passwordauthentication", "yes") == "yes":
        a.add("ssh_password_auth", "SSH password authentication enabled", "medium", "T1110",
              "PasswordAuthentication yes (or default)", "SSH accepts passwords, so it can be brute-forced.",
              "Use SSH keys and set 'PasswordAuthentication no'; install fail2ban.",
              "Weak or reused passwords can be guessed.", references=["CIS Linux 5.2"])
    if conf.get("permitemptypasswords") == "yes":
        a.add("ssh_empty_pw", "SSH permits empty passwords", "critical", "T1078",
              "PermitEmptyPasswords yes", "Accounts with no password can log in over SSH.",
              "Set 'PermitEmptyPasswords no'.", "Anyone can log in to password-less accounts.")
    if conf.get("x11forwarding") == "yes":
        a.add("ssh_x11", "SSH X11 forwarding enabled", "low", "T1021.004", "X11Forwarding yes",
              "X11 forwarding increases the attack surface of SSH sessions.", "Set 'X11Forwarding no' unless needed.")
    tries = conf.get("maxauthtries", "6")
    if tries.isdigit() and int(tries) > 4:
        a.add("ssh_maxauth", "SSH MaxAuthTries is high", "low", "T1110", f"MaxAuthTries {tries}",
              "Each connection may try many passwords.", "Set 'MaxAuthTries 3'.")


def check_accounts(a):
    a.checks.append("User accounts (UID 0, empty passwords, shells)")
    passwd = _read("/etc/passwd") or ""
    uid0 = [l.split(":")[0] for l in passwd.splitlines() if l.count(":") >= 6 and l.split(":")[2] == "0"
            and l.split(":")[0] != "root"]
    if uid0:
        a.add("uid0_accounts", "Extra accounts with root privileges (UID 0)", "critical", "T1136",
              uid0, "Accounts other than root have UID 0, which makes them full administrators.",
              "Remove or change the UID of these accounts unless you created them on purpose: userdel NAME",
              "A typical attacker backdoor account.", category="Persistence")
    shadow = _read("/etc/shadow")
    if shadow is None:
        return
    empty = [l.split(":")[0] for l in shadow.splitlines() if l.count(":") >= 2 and l.split(":")[1] == ""]
    if empty:
        a.add("empty_passwords", "Accounts with empty passwords", "critical", "T1078", empty,
              "These accounts have no password at all.", "Set a password or lock them: passwd -l NAME",
              "Anyone can log in as these users locally (and over SSH if allowed).")


def check_sudoers(a):
    a.checks.append("Sudo rules (NOPASSWD)")
    hits = []
    for f in ["/etc/sudoers"] + glob.glob("/etc/sudoers.d/*"):
        for line in (_read(f) or "").splitlines():
            s = line.strip()
            if s and not s.startswith("#") and "NOPASSWD" in s and "ALL" in s:
                hits.append(f"{f}: {s}")
    if hits:
        a.add("sudo_nopasswd", "Passwordless sudo to ALL commands", "medium", "T1548.003", hits,
              "These users can become root without typing a password.",
              "Remove NOPASSWD or limit it to specific commands with visudo.",
              "Any process running as these users can silently become root.", category="Privilege Escalation")


def _listening():
    """[(proto, addr, port)] for TCP LISTEN sockets, from /proc (no root needed)."""
    out = []
    for path, v6 in (("/proc/net/tcp", False), ("/proc/net/tcp6", True)):
        for line in (_read(path) or "").splitlines()[1:]:
            parts = line.split()
            if len(parts) < 4 or parts[3] != "0A":
                continue
            addr_hex, port_hex = parts[1].split(":")
            port = int(port_hex, 16)
            any_addr = set(addr_hex) == {"0"}
            loop = addr_hex in ("0100007F",) or addr_hex.endswith("01000000") and v6
            out.append(("tcp6" if v6 else "tcp", "*" if any_addr else ("loopback" if loop else "addr"), port))
    return out


def check_ports(a):
    a.checks.append("Listening network services")
    names = {}
    ss = _run(["ss", "-Htlnp"])
    for line in (ss or "").splitlines():
        m = re.search(r":(\d+)\s.*users:\(\(\"([^\"]+)\"", line)
        if m:
            names[int(m.group(1))] = m.group(2)
    exposed = sorted({p for _, where, p in _listening() if where == "*"})
    risky = [(p, *RISKY_PORTS[p]) for p in exposed if p in RISKY_PORTS]
    for port, svc, sev in risky:
        proc = f" (process: {names[port]})" if port in names else ""
        a.add(f"port_{port}", f"{svc} exposed on all interfaces (port {port})", sev, "T1046",
              f"0.0.0.0:{port} / [::]:{port} LISTEN{proc}",
              f"{svc} is reachable from the network, not just this machine.",
              f"Bind it to 127.0.0.1 in its config, or allow only trusted IPs: sudo ufw allow from 10.0.0.0/8 to any port {port}",
              "Exposed admin/database services are a top cause of breaches.", category="Network Exposure")
    if exposed:
        a.add("open_ports", f"{len(exposed)} TCP port(s) listening on all interfaces", "info", "T1046",
              [f"port {p}" + (f" ({names[p]})" if p in names else "") for p in exposed],
              "Inventory of services reachable from the network.",
              "Close anything you don't need: systemctl disable --now SERVICE", category="Network Exposure")


def check_firewall(a):
    a.checks.append("Host firewall (ufw / firewalld / nftables / iptables)")
    ufw = _run(["ufw", "status"]) if a.is_root else None
    if ufw and "Status: active" in ufw:
        return
    conf = _read("/etc/ufw/ufw.conf") or ""
    if re.search(r"^ENABLED=yes", conf, re.M):
        return
    if _run(["systemctl", "is-active", "firewalld"]) == "active\n":
        return
    if a.is_root:
        nft = _run(["nft", "list", "ruleset"]) or ""
        ipt = _run(["iptables", "-S"]) or ""
        if "hook input" in nft or re.search(r"^-A INPUT", ipt, re.M) or "-P INPUT DROP" in ipt:
            return
    a.add("no_firewall", "No active host firewall detected", "medium", "T1562.004",
          "ufw inactive / firewalld not running" + ("" if a.is_root else " (run as root for a full check)"),
          "Every listening service is reachable from the network.",
          "Enable a default-deny firewall: sudo ufw default deny incoming && sudo ufw allow OpenSSH && sudo ufw enable",
          "Accidentally exposed services become reachable by attackers.", category="Network Exposure")


def check_sysctl(a):
    a.checks.append("Kernel hardening (sysctl)")
    for key, want, sev, title in SYSCTL_CHECKS:
        val = _read("/proc/sys/" + key)
        if val is None:
            continue
        val = val.strip()
        ok = val == want or (key == "kernel/kptr_restrict" and val in ("1", "2")) \
            or (key == "net/ipv4/conf/all/rp_filter" and val in ("1", "2"))
        if not ok:
            name = key.replace("/", ".")
            a.add("sysctl_" + key.replace("/", "_"), title, sev, "-", f"{name} = {val} (recommended {want})",
                  f"Kernel setting {name} is not hardened.",
                  f"echo '{name} = {want}' | sudo tee /etc/sysctl.d/99-hardening.conf && sudo sysctl --system",
                  category="Kernel Hardening", references=["CIS Linux 3.x / 1.5"])


def check_permissions(a):
    a.checks.append("Critical file permissions")
    bad = []
    for path, max_other in (("/etc/passwd", 0o4), ("/etc/shadow", 0), ("/etc/gshadow", 0), ("/etc/group", 0o4),
                            ("/etc/sudoers", 0), ("/etc/ssh/sshd_config", 0o4), ("/etc/crontab", 0o4)):
        try:
            mode = os.stat(path).st_mode
        except OSError:
            continue
        other = mode & 0o7
        if other & ~max_other or mode & stat.S_IWGRP and path != "/etc/shadow":
            bad.append(f"{path} mode {oct(mode & 0o777)}")
    if bad:
        a.add("file_perms", "Insecure permissions on critical system files", "high", "T1222", bad,
              "Sensitive system files are readable or writable by too many users.",
              "Fix with: chmod 644 /etc/passwd /etc/group; chmod 640 /etc/shadow /etc/gshadow; chmod 440 /etc/sudoers",
              "Users can read password hashes or modify accounts.")
    ww = []
    for root, dirs, files in os.walk("/etc"):
        for n in files:
            p = os.path.join(root, n)
            try:
                st = os.lstat(p)
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode) and st.st_mode & stat.S_IWOTH:
                ww.append(p)
        if len(ww) > 20:
            break
    if ww:
        a.add("world_writable_etc", "World-writable files in /etc", "high", "T1574", ww,
              "Any user can modify these configuration files.", "chmod o-w FILE for each listed file.",
              "Local users can change system configuration to escalate privileges.")


def check_suid(a):
    a.checks.append("SUID/SGID binaries")
    unusual, in_tmp = [], []
    for d in ("/bin", "/sbin", "/usr/bin", "/usr/sbin", "/usr/local/bin", "/usr/local/sbin", "/usr/lib/openssh"):
        for p in glob.glob(d + "/*"):
            try:
                st = os.lstat(p)
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode) and st.st_mode & stat.S_ISUID and os.path.basename(p) not in KNOWN_SUID:
                unusual.append(p)
    for d in ("/tmp", "/var/tmp", "/dev/shm"):
        for root, _, files in os.walk(d):
            for n in files[:2000]:
                p = os.path.join(root, n)
                try:
                    st = os.lstat(p)
                except OSError:
                    continue
                if stat.S_ISREG(st.st_mode) and st.st_mode & (stat.S_ISUID | stat.S_ISGID):
                    in_tmp.append(p)
    if in_tmp:
        a.add("suid_tmp", "SUID/SGID files in temporary directories", "critical", "T1548", in_tmp,
              "Set-UID programs in /tmp are almost always a root backdoor.",
              "Investigate and delete them; mount /tmp with nosuid,noexec.", "Any local user can become root.",
              category="Privilege Escalation")
    if unusual:
        a.add("suid_unusual", "Uncommon SUID binaries", "medium", "T1548", unusual,
              "These SUID programs are not in the usual system list. Some (e.g. find, vim, python, bash, nmap) "
              "allow instant root - check GTFOBins.",
              "Remove the SUID bit if not required: chmod u-s FILE", "Possible privilege escalation path.",
              category="Privilege Escalation", references=["https://gtfobins.github.io/"])


def check_tmp_executables(a):
    a.checks.append("Hidden / executable files in /tmp, /var/tmp, /dev/shm")
    found = []
    for d in ("/tmp", "/var/tmp", "/dev/shm"):
        for p in glob.glob(d + "/.*") + glob.glob(d + "/*"):
            try:
                st = os.lstat(p)
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode) and st.st_mode & 0o111:
                try:
                    with open(p, "rb") as fh:
                        head = fh.read(4)
                except OSError:
                    head = b""
                kind = "ELF binary" if head == b"\x7fELF" else "script/executable"
                found.append(f"{p} ({kind}, {st.st_size} bytes)")
    if found:
        hidden = any("/." in f for f in found)
        a.add("tmp_executables", "Executable files in temporary directories", "high" if hidden else "medium",
              "T1059", found, "Malware droppers and miners usually run from /tmp or /dev/shm.",
              "Check each file (sha256sum, strings), delete unknown ones, and mount these with noexec.",
              category="Malware Indicators")
    mounts = _read("/proc/mounts") or ""
    weak = [m for m in ("/tmp", "/dev/shm") if re.search(rf"^\S+ {m} \S+ (?!.*noexec)", mounts, re.M)]
    if weak:
        a.add("tmp_noexec", "/tmp or /dev/shm allows program execution", "low", "T1059",
              [f"{m} mounted without noexec" for m in weak],
              "Attackers can run downloaded tools from world-writable directories.",
              "Add 'noexec,nosuid,nodev' to these mounts in /etc/fstab.", category="Kernel Hardening")


def check_cron(a):
    a.checks.append("Scheduled tasks (cron, systemd timers)")
    bad = []
    files = ["/etc/crontab"] + glob.glob("/etc/cron.d/*") + glob.glob("/var/spool/cron/*") + \
        glob.glob("/var/spool/cron/crontabs/*")
    rx = re.compile(r"/tmp/|/dev/shm/|curl\s|wget\s|base64|\bnc\b|/dev/tcp|python[23]? -c|bash -i|stratum", re.I)
    for f in files:
        for line in (_read(f) or "").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and rx.search(line):
                bad.append(f"{f}: {line.strip()}")
    for f in glob.glob("/etc/systemd/system/*.service"):
        for line in (_read(f) or "").splitlines():
            if line.startswith("ExecStart") and rx.search(line):
                bad.append(f"{f}: {line.strip()}")
    if bad:
        a.add("cron_suspicious", "Suspicious scheduled task or service", "high", "T1053", bad,
              "A cron job or service downloads code, decodes data or runs from a temp directory.",
              "Verify each entry; remove unknown ones and investigate how they were added.",
              "Typical persistence for miners and backdoors.", category="Persistence")


def check_ssh_keys(a):
    a.checks.append("SSH authorized_keys")
    keys = []
    for f in ["/root/.ssh/authorized_keys"] + glob.glob("/home/*/.ssh/authorized_keys"):
        for line in (_read(f) or "").splitlines():
            if line.strip() and not line.startswith("#"):
                comment = line.split()[-1] if len(line.split()) >= 3 else ""
                keys.append(f"{f}: {line.split()[0] if not line.startswith('ssh-') else line.split()[0]} ... {comment}")
    if keys:
        a.add("ssh_keys", f"{len(keys)} SSH key(s) authorised for login", "info", "T1098", keys,
              "Every key listed can log in without a password.",
              "Remove any key you don't recognise from the authorized_keys file.", category="Persistence")


def check_processes(a):
    a.checks.append("Running processes (malware names, deleted / temp binaries)")
    bad = []
    for pid_dir in glob.glob("/proc/[0-9]*"):
        try:
            exe = os.readlink(pid_dir + "/exe")
        except OSError:
            exe = ""
        comm = (_read(pid_dir + "/comm") or "").strip()
        cmd = (_read(pid_dir + "/cmdline") or "").replace("\0", " ").strip()[:200]
        if "runc_cloned" in exe:
            continue  # container runtime's legitimate in-memory copy of itself
        if exe.startswith(("/tmp/", "/dev/shm/", "/var/tmp/")) or (exe.endswith(" (deleted)") and
                                                                    not exe.startswith(("/usr/", "/opt/", "/snap/"))):
            bad.append(f"PID {pid_dir[6:]} {comm}: {exe} | {cmd}")
        elif MALWARE_NAMES.search(comm) or MALWARE_NAMES.search(cmd.split(" ")[0] if cmd else ""):
            bad.append(f"PID {pid_dir[6:]} {comm}: {cmd}")
    if bad:
        a.add("bad_processes", "Suspicious running processes", "critical", "T1059", bad,
              "Processes run from temporary directories, from deleted files, or match known malware names.",
              "Capture evidence (ls -l /proc/PID/exe; cp /proc/PID/exe /root/sample), then kill the process "
              "and find its persistence.", "Active malware or attacker tooling.", category="Malware Indicators")


def check_connections(a):
    a.checks.append("Outbound connections to suspicious ports")
    bad = []
    for path in ("/proc/net/tcp", "/proc/net/tcp6"):
        for line in (_read(path) or "").splitlines()[1:]:
            parts = line.split()
            if len(parts) < 4 or parts[3] != "01":
                continue
            rhex, rport = parts[2].split(":")
            port = int(rport, 16)
            if port in SUSPICIOUS_REMOTE_PORTS:
                ip = ".".join(str(int(rhex[i:i + 2], 16)) for i in (6, 4, 2, 0)) if len(rhex) == 8 else rhex
                bad.append(f"ESTABLISHED to {ip}:{port} ({SUSPICIOUS_REMOTE_PORTS[port]})")
    if bad:
        a.add("bad_connections", "Connections to known backdoor / mining ports", "high", "T1071", bad,
              "This host is connected to remote ports commonly used by reverse shells, botnets or miners.",
              "Identify the process with 'sudo ss -tnp', block the remote address and investigate.",
              category="Malware Indicators")


def check_updates(a):
    a.checks.append("Pending updates and reboot")
    if os.path.exists("/var/run/reboot-required"):
        a.add("reboot_required", "Reboot required to apply updates", "low", "-", "/var/run/reboot-required exists",
              "Installed security updates (often the kernel) are not active until reboot.",
              "Schedule a reboot.", category="Patch Management")
    out = _run(["apt", "list", "--upgradable"], timeout=20)
    if out is None:
        return
    pkgs = [l for l in out.splitlines() if "/" in l and "[upgradable" in l]
    sec = [l.split("/")[0] for l in pkgs if "-security" in l]
    if sec:
        a.add("security_updates", f"{len(sec)} security update(s) not installed", "high", "T1068", sec[:30],
              "Packages with published security fixes are not updated.",
              "sudo apt update && sudo apt upgrade -y  (enable unattended-upgrades for automatic patches)",
              "Known, public vulnerabilities remain exploitable.", category="Patch Management", count=len(sec))
    elif pkgs:
        a.add("pending_updates", f"{len(pkgs)} package update(s) pending", "low", "-",
              [l.split("/")[0] for l in pkgs[:30]], "Non-security updates are waiting.",
              "sudo apt update && sudo apt upgrade", category="Patch Management", count=len(pkgs))


def check_services(a):
    a.checks.append("Security services (fail2ban, auditd) and failed units")
    comms = {(_read(p) or "").strip() for p in glob.glob("/proc/[0-9]*/comm")}
    if "sshd" in comms and not any(c.startswith("fail2ban") for c in comms):
        a.add("no_fail2ban", "SSH is running without fail2ban", "low", "T1110", "sshd running, fail2ban not running",
              "Nothing automatically blocks brute-force attackers.",
              "sudo apt install fail2ban && sudo systemctl enable --now fail2ban", category="Monitoring")
    if "auditd" not in comms:
        a.add("no_auditd", "Linux audit daemon (auditd) not running", "low", "-", "auditd not running",
              "Detailed records of commands, file access and privilege changes are not kept.",
              "sudo apt install auditd && sudo systemctl enable --now auditd", category="Monitoring")
    failed = _run(["systemctl", "--failed", "--no-legend", "--plain"])
    units = [w for l in (failed or "").splitlines() for w in l.split()[:2]
             if re.fullmatch(r"[\w@.\-\\]+\.(service|timer|socket|mount|path|target)", w)]
    if units:
        a.add("failed_units", f"{len(units)} failed systemd service(s)", "info", "-", units,
              "Some services failed to start.", "Check with: systemctl status UNIT", category="Monitoring")


def check_password_policy(a):
    a.checks.append("Password ageing policy (/etc/login.defs)")
    text = _read("/etc/login.defs") or ""
    m = re.search(r"^PASS_MAX_DAYS\s+(\d+)", text, re.M)
    if m and int(m.group(1)) > 365:
        a.add("pass_max_days", "Passwords never expire", "low", "-", f"PASS_MAX_DAYS {m.group(1)}",
              "Password ageing is not enforced for new accounts.", "Set PASS_MAX_DAYS 365 (or per policy).",
              category="Authentication", references=["CIS Linux 5.5.1"])


CHECKS = [check_ssh, check_accounts, check_sudoers, check_ports, check_firewall, check_sysctl,
          check_permissions, check_suid, check_tmp_executables, check_cron, check_ssh_keys,
          check_processes, check_connections, check_updates, check_services, check_password_policy]


def scan_system_logs():
    """Run the log detector on the system's own logs (tail of each)."""
    texts, used = [], []
    for f in LOG_FILES:
        t = _read(f, LOG_TAIL_BYTES)
        if t:
            texts.append(t)
            used.append(f)
    if not texts:
        j = _run(["journalctl", "-q", "--no-pager", "-n", "20000", "-o", "short"], timeout=30)
        if j and "No journal files" not in j:
            texts.append(j)
            used.append("journalctl (last 20000 entries)")
    return (detector.analyze("\n".join(texts)) if texts else None), used


def run_audit(include_logs=True):
    t0 = time.time()
    if platform.system() != "Linux":
        a = Audit()
        a.add("unsupported", "Host audit supports Linux only", "info", "-", platform.platform(),
              "The live host audit reads Linux system files.", "Use the Win Audit & Hardening tool on Windows.")
        res = detector.score(a.findings)
        res.update(kind="host", host={"hostname": socket.gethostname(), "os": platform.platform()},
                   checks_run=[], log_sources=[])
        return res
    a = Audit()
    for check in CHECKS:
        try:
            check(a)
        except Exception as e:  # one broken check must not stop the audit
            a.checks.append(f"{check.__name__}: error {e}")
    logs, used = scan_system_logs() if include_logs else (None, [])
    findings = list(a.findings)
    if logs:
        for f in logs["findings"]:
            f = dict(f, id="log_" + f["id"], title="Logs: " + f["title"])
            findings.append(f)
        a.checks.append("System log analysis: " + ", ".join(used))
    findings.sort(key=lambda f: (detector.SEV_RANK[f["severity"]], -f.get("count", 1)))
    res = detector.score(findings)
    res.update({
        "kind": "host", "host": host_info(), "checks_run": a.checks, "log_sources": used,
        "duration_s": round(time.time() - t0, 2), "lines": logs["lines"] if logs else 0,
        "log_types": logs["log_types"] if logs else [],
    })
    for key in ("ip_profiles", "timeline", "timeline_bucket", "iocs", "targeted_users", "time_range", "top_ips"):
        if logs:
            res[key] = logs[key]
    return res
