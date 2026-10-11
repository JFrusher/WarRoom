"""Unit checks for target confinement, flag parsing, and payload variants."""
from __future__ import annotations

import pytest

from config import settings
from src import client, obfuscate


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
