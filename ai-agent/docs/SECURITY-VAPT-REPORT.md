# Security assessment (VAPT) — CyberSec AI Agent

**Scope:** the agent itself: the web server and API, the web UI and Live window, log parsers and the detection engine,
file storage, threat-intelligence client, live SIEM receiver (HTTP and syslog), HTTPS setup and the CLI.
**Method:**
- An OWASP-style code review of every module, split into four areas: server/auth, front end, parsers/resources, files/network/live.
- Reproduction of each attack against a running server.
- `bandit` static analysis.
- Browser checks with Playwright: Content-Security-Policy violations and functional regressions.

**Result:** every confirmed finding was fixed. Each fix has an automated regression test in
`tests/test_security.py` (plus `tests/test_parsers_security.py`), and these tests run with the full suite on Python 3.10 and 3.13.

> No assessment can prove that software is "100% secure". This report covers the issues found by the
> method above. Repeat it after every release, and before exposing the agent beyond a trusted network.

## Findings and fixes

| # | Severity | Area | Finding | Fix | Test |
|---|---|---|---|---|---|
| 1 | High | Server | **DNS rebinding:** when bound to 127.0.0.1 with no login, GET requests did not check `Host`. A malicious website could read stored logs, the history and the live ingest token | `Host` must be a loopback name for **every** request in local mode, including live ingest | `test_dns_rebinding_get_refused` |
| 2 | High | Server | **Negative `Content-Length`** (`-1`) bypassed the size limit and `rfile.read(-1)` read until memory ran out, without a login | Strict non-negative length parsing; nothing is read from an unauthenticated client except login/logout, capped at 64 KB | `test_bad_content_length`, `test_unauthenticated_body_not_read` |
| 3 | High | Live | **Syslog listener:** one thread per UDP datagram and per TCP connection, no idle timeout, so a flood could exhaust threads and memory | UDP handled on one thread; TCP capped at 64 connections with a 120 s idle timeout; 16 KB line cap; 256 MB memory budget; binds to the agent's own interface by default | `test_syslog_tcp_idle_and_connection_cap`, `test_memory_budget` |
| 4 | High | Live | **Spool could fill the disk;** the reload read whole files | `live_spool_max_mb` budget (oldest days deleted first, writing pauses at the limit); pruned hourly; reload is streamed | `test_spool_budget` |
| 5 | Medium | Server | **Slowloris:** no socket timeout, unlimited threads, TLS handshake could stall forever | 60 s per-connection timeout (15 s on the redirect port); at most 256 concurrent requests; listen backlog 128 | `test_slow_client_does_not_hold_the_server` |
| 6 | Medium | Server | **Login rate limit raced:** parallel requests got more than 10 guesses; PBKDF2 floods could load the CPU | The attempt is counted atomically *before* the check; at most 4 password hashes run at once; separate lockout tables for login and ingest; tables pruned | `test_parallel_login_burst_cannot_exceed_limit` |
| 7 | Medium | Server | **SSRF / key theft through the AI server URL:** `file:`, `ftp:`, cloud metadata `169.254.169.254`; the stored API key was sent to any new host | http(s) only, no credentials/query/fragment, no link-local or metadata hosts; the opener has no file/ftp/data handlers; the stored key is cleared when the host changes | `test_ssrf_base_url` |
| 8 | Medium | UI | **HTML injection** of raw log text into the attack-diagram tooltip | Escaped | Playwright CSP run + code review |
| 9 | Medium | UI | **Threat-intel links from remote JSON** (URLhaus, PhishTank) could be `javascript:` | Only `http(s)` links are kept, checked on both the server and the client | `test_javascript_links_dropped` |
| 10 | Medium | Trust | **IPv6 translation ranges** (`::ffff:0:0/96`, `64:ff9b::/96`, `2002::/16`) could trust the whole IPv4 internet; mapped addresses were not classified as IPv4 | Ranges overlapping them are refused; IPv6 minimum raised to /32; embedded IPv4 is classified as IPv4 | `test_translation_ranges_refused`, `test_mapped_address_classified_as_ipv4` |
| 11 | Medium | Live | **TCP framing was O(n²)** and reopened the spool file per line | Linear offset parser, one ingest call per chunk | `test_tcp_framing_is_linear` |
| 12 | Medium | Intel | **No response size limit, and redirects forwarded API-key headers** | 2 MB cap; redirects refused; http(s) only | `test_redirects_refused_and_big_bodies_rejected` |
| 13 | Medium | Data | **Delete left derived data:** in-memory copies, sightings and rule statistics after "delete all" or retention | `history.delete` forgets sightings and statistics; the in-memory store is cleared; a partial delete is reported | `test_delete_forgets_derived_data` |
| 14 | Medium | Learning | **Learning poisoning:** live (spoofable) data taught UEBA baselines; planted domains, or your own IPs, could be learned as malicious; a verdict on a user named like an indicator could clear it | Live data never teaches baselines; bare domains are not learned; trusted IPs never learned; verdict overrides matched by type | `test_planted_domains_and_trusted_ips_not_learned` |
| 15 | Medium | Parsers | **XXE / entity expansion ("billion laughs")** in the Windows XML parser (bandit B314) | XML containing a DTD or entity declaration is refused before parsing (Windows exports never contain one) | `test_xml_bombs_refused` |
| 16 | Low | Server | **Stored analysis could be overwritten** with a client-supplied copy, which then fed the learning | Only the server's own copy is ever persisted or learned from | `test_client_supplied_analysis_never_persisted` |
| 17 | Low | Server | **Token-mode cookie held the raw token** for 30 days; logout didn't clear it; sessions couldn't be revoked | Signed session cookie for both modes; logout clears both cookies; "sign out everywhere" (session epoch) | `test_session_cookie_and_sign_out_everywhere` |
| 18 | Low | Server | **Incomplete security headers;** the Server header showed the Python version | Per-request nonce CSP, frame-ancestors, Referrer-Policy, COOP/CORP, Permissions-Policy, HSTS with TLS, on every response; no version banner | `test_security_headers_and_csp_nonce` |
| 19 | Low | Config | **config.json was written non-atomically** before `chmod`; concurrent saves could lose updates; an unreadable file was overwritten | Locked, written as a 0600 temp file and renamed; an unreadable file is kept aside, never overwritten | `test_atomic_private_config` |
| 20 | Low | Intel | **Internal IPv4 inside IPv6** (NAT64, 6to4, mapped) and URL credentials could be sent to providers | Embedded IPv4 is checked; credentials are stripped from URLs before look-up | `test_embedded_internal_addresses_and_credentials` |
| 21 | Low | Rules | **Rule overrides** in `detection_rules.json` were not validated (severity reached HTML attributes) | Severity, confidence and thresholds are validated; the UI's colour helper allows only `[a-z]` | `test_rule_override_values_validated` |
| 22 | Low | Files | Truncated PNG caused a 500 error; predictable temp folder names; `config/` was 0755 | A clean validation error; `mkdtemp` / `mkstemp`; config, data and upload folders are 0700 | `test_truncated_png_is_a_clean_error`, `test_private_directories` |
| 23 | Low | Live | **Deeply nested JSON** crashed ingest with a RecursionError; the HTTP ingest ignored the source allow-list | Clean 400; the allow-list applies to HTTP too | `test_nested_json_and_long_lines`, `test_allow_list_applies_to_http` |
| 24 | Info | Server | The login template filled placeholders twice; IPv6 loopback Host (`[::1]`) was refused | Single-pass template; IPv6 Host parsed correctly | covered in `LocalModeTests` |

PARSER_FINDINGS

## Controls in place

- **Transport:** HTTPS (TLS 1.2+) with your own or a self-signed certificate; HSTS; http→https redirect.
- **Authentication:**
  - username + PBKDF2-SHA256 (600k rounds) password, or a random token
  - signed, expiring, revocable HttpOnly / SameSite=Strict / Secure session cookies
  - atomic rate limit and lockout
- **Browser:**
  - strict nonce-based Content-Security-Policy (no inline handlers, no `eval`)
  - all data HTML-escaped
  - X-Frame-Options / frame-ancestors, nosniff, no-referrer, COOP / CORP
- **Requests:**
  - CSRF: JSON content type plus SameSite cookies
  - DNS rebinding: loopback Host check
  - size limits checked before reading
  - per-connection timeouts and a thread cap
- **Data:**
  - config, data and evidence are owner-only (0700 / 0600)
  - atomic writes
  - SHA-256 of every stored log, checked before re-analysis
  - full audit trail of changes
- **Outbound:**
  - the local AI only on http(s) with no metadata hosts
  - threat intelligence opt-in and on request; only indicator values sent, never internal or trusted addresses; responses capped; no redirects
- **Parsers:** streaming, line-length caps, no DTD / entities, no code execution (no `eval`, no `shell=True`).
- **Safety by design:** the agent and its AI never block, disable or execute anything; trust never suppresses a finding.

## Residual risks and recommendations

- **Plain HTTP:** keep HTTPS on whenever the agent listens on a network address (`python3 agent.py make-cert --port 443`).
- **UDP syslog is not authenticated:** sender addresses can be forged. Prefer the HTTPS ingest, or restrict sources with `live_allowed_sources` and the firewall.
- **Ingest token in the URL:** `?token=` is accepted for SIEMs that cannot set headers, but proxies may log it. Prefer the `X-Ingest-Token` header.
- **Prompt injection:** log text is attacker-controlled and reaches the local model. The model has no tools or actions, and its answer is checked against the evidence register. Still, treat AI text as advice.
- **One role:** all signed-in users are administrators. Multi-user roles are on the roadmap.
- **Re-test:** after every release, run `python3 -m unittest discover -s tests` and a fresh assessment.
