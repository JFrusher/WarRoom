# Security and safe-use boundaries

War Zone is a training range. It contains working exploits and three
intentionally vulnerable endpoints. Those are features of the lab, and they are
only safe because the lab is sealed off. Read this before you run it.

## Scope: the lab targets itself, nothing else

- The red-team agent resolves its target from a fixed allow-list:
  `target_app:5000`, `127.0.0.1:5000`, `localhost:5000`. It has no target
  argument and no free-form override. Point it anywhere else and it refuses to
  start. See `agents/red_team/config/settings.py`.
- The published ports bind to loopback only (`127.0.0.1:5000` and
  `127.0.0.1:8080`), so nothing is reachable from off the host.
- Container-to-container traffic stays on the private Compose network.

Do not change these bindings to run the attacker against a host you do not own
and have explicit written authorization to test. That is the single rule that
keeps this project legal and ethical to use.

## Keep the vulnerable app contained

- Never expose the target on a public interface, a shared network, or a
  reverse proxy. It is built to be exploited.
- The command-injection endpoint runs shell commands by design. Treat the
  target container as untrusted and disposable. Do not mount host paths into it
  or add secrets to its environment.
- The flags are random per run and worthless outside the lab.

## What this project is not

- Not a scanner, proxy, or framework for testing third-party systems.
- Not hardened. The dashboard and target skip production controls (CSRF,
  auth on the dashboard, subresource integrity on CDN scripts) on purpose, to
  keep the teaching surface small. Do not copy these services into production.

## Reporting

This is a personal lab with no deployed instance and no data. If you find a way
the agent could be coaxed into targeting something outside the allow-list, open
an issue — that is the one class of bug that matters here.
