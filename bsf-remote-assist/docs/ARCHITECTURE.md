# Production architecture

Internet / MPLS
  -> Sophos XGS / WAF
  -> DMZ reverse proxy
  -> Remote Assist API + WebSocket gateway
  -> PostgreSQL / Redis
  -> relay/signalling service
  -> endpoint agents

Recommended zones:
- DMZ: reverse proxy + signalling/relay gateway
- Application VLAN: Django/API + frontend
- Database VLAN: PostgreSQL
- Management VLAN: AD/LDAP, monitoring, backup
- Endpoint VLANs: Windows/Linux agents

Only TCP 443 should be exposed to technicians/endpoints where possible. Internal management traffic should be separately ACL'd. Do not expose RDP/SMB/WinRM directly to the Internet.

The remote transport should support outbound agent connections and a relay fallback. The control plane must never store endpoint passwords.
