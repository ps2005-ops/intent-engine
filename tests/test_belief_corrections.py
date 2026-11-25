"""Audit corrections withdraw or qualify a dossier belief without editing the dossier."""
import json
from intent_engine.external_intel import strategic_contract as SC


def _dossier(tmp_path, beliefs):
    d = {"export_version": SC.SCHEMA_VERSION, "company_id": "acme", "as_of": "2026-11-24",
         "company_display_name": "Acme", "strategic_beliefs": beliefs}
    p = tmp_path / "acme.json"
    p.write_text(json.dumps(d))
    return p, p.read_bytes()


B = {"proposition": "Acme is seeing demand weaken rather than pause", "confidence": 0.5,
     "update_method": "CALIBRATED_HEURISTIC", "evidence_ids": ["ev1"]}
G = {"proposition": "Acme is seeing demand strengthen rather than plateau", "confidence": 0.6,
     "update_method": "CALIBRATED_HEURISTIC", "evidence_ids": ["ev2"]}


def _write(tmp_path, verdict):
    (tmp_path / SC.CORRECTIONS_FILE).write_text(json.dumps({
        "company_id": "acme", "proposition": B["proposition"], "verdict": verdict,
        "reason": "revenue +36%", "corrected_statement": "revenue grew"}) + "\n")


def test_without_corrections_nothing_changes(tmp_path):
    p, _ = _dossier(tmp_path, [B, G])
    assert len(SC.load(p, expected_company="acme", today="2026-11-25").beliefs) == 2


def test_a_contradicted_belief_is_withdrawn_and_the_page_says_so(tmp_path):
    p, raw = _dossier(tmp_path, [B, G]); _write(tmp_path, "CONTRADICTED_BY_SOURCE")
    intel = SC.load(p, expected_company="acme", today="2026-11-25")
    assert [b["proposition"] for b in intel.beliefs] == [G["proposition"]]
    assert any(l.startswith("Withdrawn after audit") for l in intel.limitations)
    assert p.read_bytes() == raw                         # the dossier is untouched


def test_a_qualified_belief_stays_with_its_qualification(tmp_path):
    p, _ = _dossier(tmp_path, [B]); _write(tmp_path, "SUPPORTED_WITH_QUALIFICATION")
    b = SC.load(p, expected_company="acme", today="2026-11-25").beliefs[0]
    assert b["qualification"] == "revenue grew"


def test_the_latest_correction_wins(tmp_path):
    p, _ = _dossier(tmp_path, [B]); _write(tmp_path, "UNSUPPORTED")
    with open(tmp_path / SC.CORRECTIONS_FILE, "a") as fh:
        fh.write(json.dumps({"company_id": "acme", "proposition": B["proposition"],
                             "verdict": "SUPPORTED_WITH_QUALIFICATION",
                             "corrected_statement": "on review"}) + "\n")
    assert len(SC.load(p, expected_company="acme", today="2026-11-25").beliefs) == 1
