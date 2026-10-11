# Threat model

This document describes the lab as a system under attack: what is worth
protecting, how it is reached, how each bug is exploited and defended, and the
risks the lab's own design carries.

## Assets

- The live flag. Proof that a vector worked. It rotates on a timer and sits in
  the `flags` table and in `/flags/flag_current.txt`.
- Service availability. The scoreboard rewards blue for defending without
  taking the target down, measured as SLA uptime.
- The admin account. Its session response is what leaks the SQLi flag.

## Entry points

| Endpoint | Method | Intended use | Bug |
|----------|--------|--------------|-----|
| `/api/v1/auth/login` | POST | user authentication | SQL injection |
| `/api/v1/comments` | GET/POST | team notes | stored XSS |
| `/api/v1/diagnostics/ping` | POST | network check | command injection / file read |
| `/api/v1/flags/submit` | POST | score a captured flag | none |
| `/healthz` | GET | liveness + patch state | none |

## Trust boundaries

The only client that should ever reach the target is traffic inside the lab.
The request log and the mitigation/blocklist state are a boundary between the
target and the blue agent: the target produces log lines and consumes state;
the blue agent consumes log lines and produces state. Neither executes the
other's code.

## Per-vector analysis

### SQL injection

- Attack: `username = admin' -- ` comments out the password check and returns
  the admin row; the response carries the flag.
- Signal: the request body contains `' --`, `' OR`, or `UNION SELECT`.
- Defence: switch the login query to parameterized binding. The injected input
  is then treated as a literal and authentication fails.

### Stored XSS

- Attack: a comment body of `<script>warzone-steal</script>` is stored raw.
  The simulated admin browser renders it and leaks its session flag.
- Signal: a stored value contains `<script`, `onerror=`, or `javascript:`.
- Defence: HTML-escape comment bodies on input. The payload becomes inert text
  and the admin browser has nothing to run.

### Command injection / arbitrary file read

- Attack: a host of `127.0.0.1; cat /flags/flag_current.txt` runs a second
  command through the shell and returns the file contents.
- Signal: the body contains `; cat`, `| id`, `/etc/passwd`, and similar.
- Defence: validate the host against a strict character set and execute `ping`
  with an argument list and `shell=False`, removing the shell entirely.

## Defence pipeline

1. The target logs every request as a JSON line.
2. The blue agent tails the log and runs the WAF signatures over each entry.
3. A hit adds threat points to the source IP and, the first time a vector is
   seen, switches on that vector's mitigation.
4. Once an IP crosses the block threshold it is added to the blocklist and the
   target returns HTTP 429 to it.
5. Health checks come from the dashboard, never match a signature, and are
   never blocked, so availability holds.

## Residual risks (by design)

- The WAF is signature-based, so lightly obfuscated payloads slip past it until
  the mitigation is on. The red agent ships one alternate form per vector to
  demonstrate exactly this gap. The real fix is the parameterized/escaped/
  shell-free code path, not the signature.
- Mitigations are one-way for the life of a run: once patched, a vector stays
  patched. Restart the stack to reset the board.
- The dashboard trusts event submitters on the internal network. That is
  acceptable only because the network is private to the Compose project.
