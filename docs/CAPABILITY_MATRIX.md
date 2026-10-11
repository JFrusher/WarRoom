# Capability matrix

How each vector is attacked, detected, and defended. This is the purple-team
view: every offensive capability lined up against its detection and its fix.

| Vector | OWASP | ATT&CK | Red exploit | Blue detection | Mitigation (virtual patch) |
|--------|-------|--------|-------------|----------------|----------------------------|
| SQL injection | A03 | T1190 | `exploits/sqli` — auth bypass | signature `sqli` | parameterized query |
| Stored XSS | A03 | T1059.007 | `exploits/xss` — admin-bot leak | signature `xss` | escape on render |
| Command injection | A03 | T1059 | `exploits/cmdi` — file read | signature `cmdi` | arg list, no shell |
| IDOR | A01 | T1087 | `exploits/idor` — object walk | **behavioural** (enumeration) | per-object authz check |
| SSRF | A10 | T1190 | `exploits/ssrf` — hit metadata | signature `ssrf` (path-scoped) | blocked-host set + private-prefix checks; network isolation |
| SSTI | A03 | T1190 | `exploits/ssti` — `{{ config }}` | signature `ssti` (path-scoped) | render input as data |
| JWT alg=none | A07/A02 | T1550 | `exploits/jwt` — forged admin | signature `jwt` (path-scoped) | reject `none`, verify HS256 |
| Honeytoken | — | T1083 | (trap; no exploit) | signature `honeytoken` (critical) | — (decoy by design) |

Notes:
- **IDOR has no payload signature** — it is caught only by watching access
  patterns (`behaviour.py`), which is why it is the one vector a regex WAF
  misses. That gap is the teaching point.
- **SSRF confinement** depends on the Phase 0 internal network: the exploit
  reaches the internal metadata service but cannot reach the public internet.
- Red can run any vector loud or stealth (`--profile`); the referee rewards a
  capture that lands before the matching detection fires.

## Not yet implemented (next scenarios)

- **Path traversal (A01/A03)** — `GET /api/v1/files?name=../…`. Overlaps the
  existing command-injection file-read; add as a distinct endpoint with a
  `\.\./`-canonicalisation patch and a traversal signature.
- **Blind / time-based SQLi (A03)** — a boolean/time oracle on a search
  endpoint, with a red extractor that recovers the flag character by
  character. Distinct from the existing union-style SQLi.
