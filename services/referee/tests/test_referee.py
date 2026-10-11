"""Referee: flag oracle, scoring, round lifecycle, and report."""
from __future__ import annotations

from src import oracle, report, scoring
from src.match import Match


def _fresh() -> Match:
    m = Match()
    m.start_round()
    return m


def test_valid_flag_is_accepted_and_scored():
    m = _fresh()
    _, token = oracle.read()
    result = m.submit_flag(token, "sqli")
    assert result["status"] == "accepted"
    assert result["points"] >= scoring.rubric()["red"]["base"]
    assert m.red_score == result["points"]


def test_wrong_flag_is_rejected():
    m = _fresh()
    assert m.submit_flag("WARZONE{nope}", "sqli")["status"] == "rejected"


def test_unknown_vector_is_rejected():
    m = _fresh()
    _, token = oracle.read()
    assert m.submit_flag(token, "bogus")["status"] == "rejected"


def test_capture_is_deduped_per_vector():
    m = _fresh()
    _, token = oracle.read()
    assert m.submit_flag(token, "sqli")["status"] == "accepted"
    assert m.submit_flag(token, "sqli")["status"] == "duplicate"


def test_detection_before_capture_denies_stealth_bonus():
    m = _fresh()
    _, token = oracle.read()
    m.ingest_blue({"kind": "detection", "vectors": ["sqli"]})
    captured = m.submit_flag(token, "sqli")
    stealthy = Match()
    stealthy.start_round()
    _, token2 = oracle.read()
    clean = stealthy.submit_flag(token2, "sqli")
    assert clean["points"] > captured["points"]


def test_blue_detection_and_mitigation_score():
    m = _fresh()
    det = m.ingest_blue({"kind": "detection", "vectors": ["cmdi"]})
    mit = m.ingest_blue({"kind": "mitigation", "vector": "cmdi"})
    assert det["points"] > 0
    assert mit["points"] > 0
    assert m.blue_score == det["points"] + mit["points"]


def test_rotation_changes_the_flag():
    m = _fresh()
    _, before = oracle.read()
    m.rotate_flag()
    _, after = oracle.read()
    assert before != after


def test_report_counts_captures():
    m = _fresh()
    _, token = oracle.read()
    m.submit_flag(token, "sqli")
    built = report.build()
    assert built["scores"]["red"] >= scoring.rubric()["red"]["base"]
    assert "sqli" in [c["vector"] for c in built["captures"]]
