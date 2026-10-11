"""Checks for WAF matching, threat scoring, and state writes."""
from __future__ import annotations

import json

from config import rules, settings
from src import signatures, state, waf
from src.scoring import ThreatTable


def test_waf_detects_sqli():
    entry = {"path": "/api/v1/auth/login", "body": "{\"username\": \"admin' -- \"}"}
    assert "sqli" in waf.inspect(entry)


def test_waf_detects_xss():
    entry = {"path": "/api/v1/comments", "body": "<script>warzone-steal</script>"}
    assert "xss" in waf.inspect(entry)


def test_waf_detects_cmdi():
    entry = {"path": "/api/v1/diagnostics/ping", "body": "127.0.0.1; cat /flags/x"}
    assert "cmdi" in waf.inspect(entry)


def test_waf_misses_obfuscated_sqli():
    # Inline-comment spacing is the red team's deliberate dodge.
    entry = {"path": "/api/v1/auth/login", "body": "admin'/**/--/**/"}
    assert "sqli" not in waf.inspect(entry)


def test_waf_ignores_benign_traffic():
    assert waf.inspect({"path": "/healthz", "body": ""}) == []


def test_threat_table_blocks_after_threshold():
    table = ThreatTable()
    needed = rules.BLOCK_THRESHOLD // rules.HIT_SCORE + 1
    for _ in range(needed):
        table.record("10.0.0.9", 1)
    assert table.should_block("10.0.0.9")


def test_enable_mitigation_is_idempotent():
    assert state.enable_mitigation("sqli") is True
    assert state.enable_mitigation("sqli") is False
    saved = json.loads(settings.MITIGATIONS_FILE.read_text())
    assert saved["sqli"] is True


def test_block_ip_persists():
    assert state.block_ip("10.0.0.9") is True
    assert "10.0.0.9" in json.loads(settings.BLOCKLIST_FILE.read_text())


def test_rules_load_with_required_metadata():
    loaded = signatures.load()
    assert loaded
    for rule in loaded:
        assert {"id", "title", "vector", "severity", "mitre"} <= rule.keys()
        assert rule["compiled"]


def test_each_rule_matches_its_own_fixture():
    for rule in signatures.load():
        fixture = rule.get("test", {})
        path = fixture.get("path", "")
        if "match" in fixture:
            assert waf.inspect({"body": fixture["match"], "path": path}), rule["id"]
        if "no_match" in fixture:
            entry = {"body": fixture["no_match"], "path": path}
            assert rule["vector"] not in waf.inspect(entry), rule["id"]


def test_matched_rules_expose_mitre_technique():
    matched = waf.matched_rules({"body": "<script>warzone-steal</script>"})
    assert any(rule["mitre"] == "T1059.007" for rule in matched)
