"""Unit checks for target confinement, flag parsing, and payload variants."""
from __future__ import annotations

import pytest
import requests

from config import settings
from src import campaign, client, obfuscate, profiles
from src.errors import ExploitFailed
from src.exploits import sqli


def test_resolve_target_accepts_lab_host(monkeypatch):
    monkeypatch.setenv("TARGET_URL", "http://127.0.0.1:5000")
    assert settings.resolve_target() == "http://127.0.0.1:5000"


def test_resolve_target_rejects_external_host(monkeypatch):
    monkeypatch.setenv("TARGET_URL", "http://example.com")
    with pytest.raises(ValueError):
        settings.resolve_target()


def test_resolve_target_rejects_remote_ip(monkeypatch):
    monkeypatch.setenv("TARGET_URL", "http://10.0.0.5:5000")
    with pytest.raises(ValueError):
        settings.resolve_target()


def test_find_flag_extracts_token():
    assert client.find_flag("noise WARZONE{abc123} trailing") == "WARZONE{abc123}"


def test_find_flag_returns_none_when_absent():
    assert client.find_flag("nothing here") is None


def test_sqli_variant_removes_spaces():
    assert " " not in obfuscate.sqli_variant("admin' -- ")


def test_xss_variant_recases_tag():
    out = obfuscate.xss_variant("<script>warzone-steal</script>")
    assert "<ScRiPt>" in out and out.lower().startswith("<script")


def test_cmdi_variant_swaps_separator():
    out = obfuscate.cmdi_variant("127.0.0.1; cat /flags/flag_current.txt")
    assert "\n" in out and "; " not in out


def test_capture_converts_transport_error_to_exploitfailed(monkeypatch):
    sess = client.session()

    def boom(*args, **kwargs):
        raise requests.ConnectionError("target unreachable")

    monkeypatch.setattr(sess, "post", boom)
    with pytest.raises(ExploitFailed):
        sqli.capture(sess)


def test_profiles_control_payload_order():
    profiles.use("loud")
    assert profiles.payload_order("plain", "obf") == ("plain", "obf")
    profiles.use("stealth")
    assert profiles.payload_order("plain", "obf") == ("obf", "plain")
    profiles.use("loud")  # reset for other tests


def test_campaign_chain_covers_every_exploit_vector():
    vectors = {vector for vector, _ in campaign.CHAIN}
    assert vectors == {"sqli", "xss", "cmdi", "idor", "ssrf"}
    assert all(tactic.startswith("TA") for _, tactic in campaign.CHAIN)
