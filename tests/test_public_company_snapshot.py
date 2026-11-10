"""A second analysis of a known company must not be a first one.

MEASURED on 517180e6: Microsoft CORE 107.78s, of which discovery 27.7s and
retrieval 40.5s -- 63% -- rediscovering a company the engine had already read.
Apple the same shape. None of that work is new information.
"""
from __future__ import annotations

import time

from intent_engine.company_ingestion import snapshot as SN


def _snap(**kw):
    base = dict(company_key="cik:789019", canonical_name="Microsoft Corporation",
                ticker="MSFT", cik="0000789019", domains=("microsoft.com",),
                sources=(SN.SourceRecord(url="https://microsoft.com/investor",
                                         content_hash="abc"),
                         SN.SourceRecord(url="https://sec.gov/msft-10k",
                                         accession="0000789019-25-000001",
                                         form="10-K")),
                created_at=time.time(), refreshed_at=time.time())
    base.update(kw)
    return SN.PublicCompanySnapshot(**base)


# --- what a snapshot may and may not hold -----------------------------------

def test_a_snapshot_holds_no_conclusion():
    """The line that keeps this from becoming a cached answer.

    A stale filing accession misleads nobody. A stale recommendation is the
    product telling a reader something it no longer believes.
    """
    fields = {f for f in SN.PublicCompanySnapshot.__dataclass_fields__}
    forbidden = {"recommendation", "thesis", "decision", "decision_delta",
                 "observations", "hypotheses", "strategic_analysis",
                 "verdict", "answer", "findings"}
    assert not (fields & forbidden), (
        f"a conclusion is stored in the snapshot: {fields & forbidden}")


def test_durability_is_stamped_by_the_writer_not_the_caller(tmp_path):
    """A snapshot may not claim more than its deployment can support."""
    store = SN.SnapshotStore(tmp_path, durability=SN.EPHEMERAL)
    assert store.put(_snap(durability=SN.DURABLE)) is True
    got = store.get("cik:789019")
    assert got.durability == SN.EPHEMERAL, (
        "a caller was able to label an ephemeral snapshot as durable")


# --- the plan ---------------------------------------------------------------

def test_no_snapshot_means_a_cold_run():
    plan = SN.plan_refresh(None)
    assert plan["mode"] == "COLD" and plan["rediscover"] is True


def test_a_fresh_snapshot_does_not_rediscover():
    plan = SN.plan_refresh(_snap())
    assert plan["mode"] == "WARM"
    assert plan["rediscover"] is False, (
        "a known company with fresh state was rediscovered from nothing")
    assert plan["known_sources"] == 2


def test_an_accessioned_filing_is_never_revalidated():
    """An EDGAR accession is immutable, so asking whether it changed is a
    request whose only possible answer is no."""
    plan = SN.plan_refresh(_snap())
    assert "https://sec.gov/msft-10k" in plan["immutable"]
    assert "https://sec.gov/msft-10k" not in plan["revalidate"]
    assert "https://microsoft.com/investor" in plan["revalidate"]


def test_a_stale_snapshot_still_rediscovers():
    """POSITIVE CONTROL: reuse must not become permanent.

    Without this, the cheapest possible implementation -- always WARM --
    would pass every test above and serve a month-old source list.
    """
    old = _snap(created_at=time.time() - 90 * 3600,
                refreshed_at=time.time() - 90 * 3600)
    plan = SN.plan_refresh(old)
    assert plan["mode"] == "STALE"
    assert plan["rediscover"] is True
    assert len(plan["revalidate"]) == 2


# --- identity ---------------------------------------------------------------

def test_the_key_prefers_the_identifier_a_company_cannot_change():
    assert SN.company_key("Microsoft Corporation", cik="0000789019") \
        == SN.company_key("MSFT", cik="789019")


def test_two_companies_sharing_a_leading_word_do_not_share_a_key():
    """`Linear` once satisfied an alias for `Linear Minerals Corp.`"""
    assert SN.company_key("Linear") != SN.company_key("Linear Minerals Corp.")


# --- the store --------------------------------------------------------------

def test_a_round_trip_preserves_the_evidence_index(tmp_path):
    store = SN.SnapshotStore(tmp_path)
    store.put(_snap())
    got = store.get("cik:789019")
    assert got.canonical_name == "Microsoft Corporation"
    assert got.source_for("https://sec.gov/msft-10k").form == "10-K"
    assert got.source_for("https://microsoft.com/investor").content_hash == "abc"


def test_a_snapshot_from_another_schema_is_not_read(tmp_path):
    store = SN.SnapshotStore(tmp_path)
    store.put(_snap())
    p = store._path("cik:789019")
    import json
    d = json.loads(p.read_text())
    d["schema"] = "public_company_snapshot.v0"
    p.write_text(json.dumps(d))
    assert store.get("cik:789019") is None, (
        "a snapshot of a different shape was migrated silently")


def test_an_unwritable_root_costs_the_head_start_and_nothing_else(tmp_path):
    store = SN.SnapshotStore(tmp_path / "nope" / "\0bad")
    assert store.put(_snap()) is False
    assert store.get("cik:789019") is None
