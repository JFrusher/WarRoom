"""Red-team command-line entry point.

Subcommands run a single exploit or the full automated chain. There is no
target argument by design; the target is fixed by :mod:`config.settings`.
"""
from __future__ import annotations

import argparse
import logging
import sys

from src import campaign, client, profiles, recon, report, submit
from src.errors import ExploitFailed, RedTeamError
from src.exploits import cmdi, idor, jwt, sqli, ssrf, ssti, xss

log = logging.getLogger("red.cli")

_EXPLOITS = {mod.VECTOR: mod for mod in (sqli, xss, cmdi, idor, ssrf, ssti, jwt)}


def _run_exploit(sess, vector: str) -> bool:
    """Capture and submit one flag. Return True on a scoring capture."""
    module = _EXPLOITS[vector]
    report.emit("exploit_attempt", {"vector": vector})
    try:
        flag = module.capture(sess)
    except ExploitFailed as exc:
        log.warning("[%s] %s", vector, exc)
        report.emit("exploit_failed", {"vector": vector})
        return False

    verdict = submit.submit(sess, flag, vector)
    report.emit("exploit_success", {"vector": vector, "flag": flag})
    print(f"  [{vector}] captured {flag} -> {verdict['status']}")
    return verdict["status"] == "accepted"


def cmd_recon(sess) -> int:
    result = recon.run(sess)
    print(f"reachable : {result.reachable}")
    print(f"forms     : {', '.join(result.forms)}")
    print(f"patches   : {result.mitigations}")
    return 0


def cmd_single(sess, vector: str) -> int:
    return 0 if _run_exploit(sess, vector) else 1


def cmd_full_auto(sess) -> int:
    print(f"target: {client.settings.TARGET_URL}")
    recon.run(sess)
    scored = 0
    for vector in _EXPLOITS:
        if _run_exploit(sess, vector):
            scored += 1
    print(f"\ncaptured {scored}/{len(_EXPLOITS)} vectors this round")
    return 0 if scored else 2


def cmd_campaign(sess) -> int:
    print(f"campaign: target={client.settings.TARGET_URL} profile={profiles.ACTIVE.name}")
    recon.run(sess)
    covered: list[str] = []
    for vector, tactic in campaign.CHAIN:
        report.emit("campaign_stage", {"vector": vector, "tactic": tactic})
        print(f"[{tactic}] {vector}")
        if _run_exploit(sess, vector):
            covered.append(tactic)
        profiles.pace()
    print(f"\ntactics covered: {', '.join(covered) or 'none'}")
    return 0 if covered else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="red", description="War Zone red-team agent")
    parser.add_argument("--profile", choices=["loud", "stealth"], default="loud",
                        help="attack profile: loud (default) or stealth")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("recon", help="fingerprint the target")
    sub.add_parser("sqli", help="run the SQL injection exploit")
    sub.add_parser("xss", help="run the stored XSS exploit")
    sub.add_parser("cmdi", help="run the command injection exploit")
    sub.add_parser("idor", help="run the IDOR exploit")
    sub.add_parser("ssrf", help="run the SSRF exploit")
    sub.add_parser("ssti", help="run the SSTI exploit")
    sub.add_parser("jwt", help="run the JWT alg=none exploit")
    sub.add_parser("full-auto", help="recon, exploit every vector, and submit")
    sub.add_parser("campaign", help="run the kill-chain in ATT&CK order")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")
    args = build_parser().parse_args(argv)
    profiles.use(args.profile)
    sess = client.session()

    try:
        if args.command == "recon":
            return cmd_recon(sess)
        if args.command == "full-auto":
            return cmd_full_auto(sess)
        if args.command == "campaign":
            return cmd_campaign(sess)
        return cmd_single(sess, args.command)
    except RedTeamError as exc:
        log.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
