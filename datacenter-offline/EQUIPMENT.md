# Your equipment: what the kit does with it

What is collected into GLPI and monitored in Grafana for each kind of device in the NehraEduHub data centre, and what to set up on the device.

| Equipment | Inventory in GLPI | Up / down (ping) | Network & hardware dashboard | How it is reached |
|---|---|---|---|---|
| **Sophos Firewall** (XG/XGS, SFOS) | Model, serial (appliance key), firmware, interfaces | Yes | Ports, traffic, memory/disk/swap, live users, **HA state** | SNMP |
| **Radware Alteon** SLB | Model, serial, firmware, interfaces | Yes | Ports, traffic, errors, uptime | SNMP |
| **HPE SimpliVity** (VMware) | Each node and every VM, via vCenter; node hardware via iLO | Yes | Per-node iLO health: power supplies, temperatures, drives | vSphere API + iLO SNMP |
| **HPE VM Essentials** (VME) | Each KVM host: hardware, OS, software, VMs | Yes | Host iLO health | SSH + iLO SNMP |
| **Accesleron cloud** | Added by hand in GLPI (monitor only) | Yes | – | Ping + HTTPS checks |
| **HP / HPE ProLiant** servers | Server via SSH/WinRM or agent; iLO via SNMP | Yes | iLO health, hottest sensor | SSH/WinRM + iLO SNMP |
| **Dell PowerEdge** servers | Server via SSH/WinRM or agent; iDRAC via SNMP | Yes | iDRAC global and storage status, temperatures | SSH/WinRM + iDRAC SNMP |
| **Cisco** switches and routers | Model, serial, IOS version, ports, VLANs, **CDP/LLDP neighbours** | Yes | Ports, traffic, errors, **CPU** | SNMP |
| **Dell** switches (OS10) | Model, serial, OS version, ports, LLDP neighbours | Yes | Ports, traffic, **CPU**, power supplies | SNMP |
| **HP/HPE Aruba** switches | Model, serial, firmware, ports, LLDP neighbours | Yes | Ports, traffic, errors | SNMP |

How it fits together:

- The **collector** reads every device in your `SNMP_RANGES` into GLPI, and every server in `REMOTES` / `ESX_HOSTS`.
- **monitor-sync** turns what is in GLPI into monitoring. Everything with an IP is pinged. Every network device, iLO and iDRAC is also polled over SNMP. It tries your SNMP credentials in order, reads the vendor from the device, and adds that vendor's health metrics (Sophos, Cisco, HPE, Dell).
- GLPI dictionary rules rename **Compaq → Hewlett Packard Enterprise** (iLO) and **Nortel/Alteon → Radware**, so manufacturers read correctly.

Before you start, allow these from the GLPI server to your management networks: **ICMP**, **UDP 161** (SNMP), **TCP 22** (SSH), **TCP 5985/5986** (WinRM) and **TCP 443** (vCenter and HTTPS checks).

> Use one **read-only SNMPv3 user** everywhere if you can (SHA + AES), restricted to the GLPI server's IP. Put it first in `SNMP_CREDENTIALS`. Menu names below are for current firmware and may differ slightly on yours.

---

## Sophos Firewall (SFOS)

1. **Administration → SNMP**: enable the SNMP agent, then add an SNMPv3 user (or a v2c community) with the GLPI server as the allowed manager.
2. **Administration → Device access**: tick **SNMP** for the zone the GLPI server sits in (usually LAN or a management zone).
3. Add the firewall's management IP to `SNMP_RANGES`.

The Network & hardware dashboard shows the **HA state** (Primary, Auxiliary, Standalone, Faulty in red), memory, disk and swap usage, and live users, from the SFOS MIB. To also check the web admin console, add an HTTPS check (see `monitoring/manual/your-services.yml.disabled`).

## Radware Alteon (SLB)

1. On the management interface, enable SNMP with a read-only v2c community or v3 user, and allow access from the GLPI server.
2. Add the Alteon management IP to `SNMP_RANGES`.

You get ports, traffic, errors and uptime. Ping and port monitoring don't cover **virtual service health**. Add an `http_2xx` or `tcp_connect` check for each important VIP in `monitoring/manual/` so you see when a service stops answering behind the load balancer.

## HPE SimpliVity (VMware vSphere)

1. In vCenter, create a user with the **Read-only** role on the top-level vCenter object, then add vCenter to `ESX_HOSTS`:
   ```
   ESX_HOSTS="
   10.10.2.10 svc-glpi@vsphere.local <password>
   "
   ```
   Each OmniStack node and all its VMs appear in GLPI.
2. On **each node's iLO** (iLO 5/6: **Management → SNMP Settings**): set a read community or v3 user. Keep **Agentless Management** enabled so iLO reports power supplies, temperatures and drives. Add the iLO IPs to `SNMP_RANGES`.
3. The OmniStack Virtual Controllers (OVC) and vCenter are pinged automatically once they're in GLPI. Add an HTTPS check for vCenter.

SimpliVity's own federation and storage health (data protection, replication) is shown by HPE's vCenter plug-in. This kit covers the hardware, the hosts and the VMs.

## HPE VM Essentials (VME)

VME hosts are Linux KVM hypervisors, so they're inventoried over SSH with no agent:

1. On each host, create an `inventory` account with the collector's public key (`collector/ssh/id_ed25519.pub`). To list VMs, add the account to the `libvirt` group.
2. Add the hosts to `REMOTES`:
   ```
   REMOTES="
   ssh://inventory@10.10.3.21
   ssh://inventory@10.10.3.22
   "
   ```
3. Add each host's iLO to `SNMP_RANGES` (as for SimpliVity).
4. Add an HTTPS check for the **VME Manager** portal.

## Accesleron cloud (monitor only)

As agreed, Accesleron is monitored but not inventoried in depth:

1. In GLPI, add its management endpoints by hand (**Assets → Computers** or **Network devices**) with their IP addresses. They're then pinged automatically.
2. Add HTTPS checks for the portal and API in `monitoring/manual/` (template in `your-services.yml.disabled`).

If you later find out what it runs on, switch to fuller inventory: VMware → `ESX_HOSTS`, KVM/Linux → `REMOTES` over SSH, Hyper-V → `REMOTES` over WinRM.

## HP / HPE ProLiant servers

- **iLO**: enable SNMP as for SimpliVity and add the iLO IPs to `SNMP_RANGES`. This gives hardware health and the hottest temperature sensor.
- **Operating system**: Linux over SSH or Windows over WinRM in `REMOTES`, or install the GLPI Agent.

The server and its iLO appear as two GLPI assets: the server under Computers, the iLO under Network devices. Put both in the same rack position, or link them in GLPI.

## Dell PowerEdge servers

- **iDRAC** (iDRAC9: **iDRAC Settings → Services → SNMP Agent**): enable it, then set the community or SNMPv3 user and the protocol. Add the iDRAC IPs to `SNMP_RANGES`. The dashboard shows **global system status**, **storage status** and temperatures.
- **Operating system**: as for HP servers.

## Windows servers (WinRM)

The GLPI agent logs in to WinRM with **Basic authentication only**. Windows has Basic turned off by default, and Basic never works with **domain** accounts, so a domain login always fails with "wrong credentials" even when the password is right. On each Windows server (admin PowerShell), or for all of them with a GPO:

```powershell
# local inventory account (use your own strong password)
net user inventory "S0me-Strong-Pass" /add /passwordchg:no /expires:never
net localgroup Administrators inventory /add
winrm quickconfig -q
winrm set winrm/config/service/auth '@{Basic="true"}'
winrm set winrm/config/service '@{AllowUnencrypted="true"}'
# allow only the GLPI server to reach WinRM
New-NetFirewallRule -DisplayName "WinRM from GLPI" -Direction Inbound -Protocol TCP -LocalPort 5985 -RemoteAddress <GLPI-server-IP> -Action Allow
```

Then list it as `winrm://inventory:PASSWORD@<ip>` in `REMOTES` (or use `check-unidentified.sh --write --winrm-user inventory`). Test one server with `./scripts/test-remote.sh <ip>`: it says whether the port is open, whether Basic is offered and whether the login works.

`AllowUnencrypted` sends the login only base64-encoded over port 5985. Keep it to the management network, firewalled to the GLPI server, with a dedicated account. To encrypt it, add an HTTPS listener (port 5986) with a certificate and use `winrm://inventory:PASSWORD@<ip>:5986/?mode=ssl` instead; then `AllowUnencrypted` is not needed.

## Cisco switches and routers (IOS / IOS-XE)

```
! read-only SNMPv3, limited to the GLPI server
ip access-list standard GLPI-SNMP
 permit <glpi-server-ip>
snmp-server group DCMON v3 priv access GLPI-SNMP
snmp-server user dcmon DCMON v3 auth sha <auth-pass> priv aes 128 <priv-pass>
! neighbours for the network map
cdp run
lldp run
```

Matching collector line: `version:3,username:dcmon,authprotocol:sha,authpassword:<auth-pass>,privprotocol:aes,privpassword:<priv-pass>`

For NX-OS, use `snmp-server user dcmon network-operator auth sha <auth-pass> priv aes-128 <priv-pass>` and `feature lldp`.

## Dell switches (OS10)

```
snmp-server community <community> ro
```

LLDP is on by default on OS10. For SNMPv3, create a group and user with the `snmp-server group` and `snmp-server user` commands (see Dell's OS10 guide for your release).

## HP / HPE Aruba switches

- ArubaOS-Switch (ProCurve): `snmp-server community "<community>" operator restricted` and `lldp run`
- ArubaOS-CX: `snmp-server community <community>`, plus `snmp-server vrf mgmt` when you manage it through the mgmt VRF. LLDP is on by default.

---

## If a device doesn't appear

- **Administration → Inventory → Refused equipment** in GLPI: GLPI refuses network devices that report **neither a serial number nor a MAC address** (rule "NetworkEquipment import denied"). This usually means the device's SNMP view is too restricted. Allow the ENTITY-MIB and IF-MIB.
- **Inventory dashboard → Automatic collection** shows each collector run and its errors.
- **Network & hardware → Not answering SNMP**: the device is in GLPI, but none of your credentials work from the GLPI server. Check the ACL or allowed hosts on the device, and the order of `SNMP_CREDENTIALS`.
