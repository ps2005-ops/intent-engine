"""The founder-facing market context, built through the channel that serves it.

`founder_brief.market` was a SECOND market consumer, parallel to
`external_intel`, reading a `market_intel_export.v1` shape that no producer in
this repository has emitted since v2 landed. It was deleted in f2b7a18 -- whose
message says the module was "left in place", which its own diff contradicts --
and the tests driving it were left importing a module that no longer exists.

The safeguards those tests carried are real, so they are asserted against the
channel a founder is actually served:

    real producer -> validated v2 payload -> MarketIntel -> ExternalContext
    -> presenter.market_context_dict -> brief.market_context

which is the sequence `WebApp._market_context` runs in production. Hand-writing
the dict here instead would let the two ends drift apart silently -- which is
precisely how a dead v1 consumer survived in the tree long enough to be tested.
"""
import datetime

from intent_engine.external_intel import market_contract as MC
from intent_engine.external_intel import market_producer as MP
from intent_engine.external_intel import pack as PK
from intent_engine.external_intel import presenter as PS


def closes(n=300, start=100.0, step=0.25, first="2025-01-01"):
    """A weekday close series long enough for every measurement window."""
    out, day, price = {}, datetime.date.fromisoformat(first), start
    while len(out) < n:
        if day.weekday() < 5:
            out[day.isoformat()] = round(price, 4)
            price += step
        day += datetime.timedelta(days=1)
    return out


def export(ticker="ACME", **kw):
    """One validated `market_intel_export.v2` payload, from the real producer.

    `build_export` validates on the way out, so anything this returns has
    already passed the allowlist a founder-facing surface depends on.
    """
    base = dict(ticker=ticker, closes=closes(),
                benchmark_closes=closes(start=400.0, step=0.10),
                exchange="NYSE", currency="USD")
    base.update(kw)
    # After the override, so a caller passing a shorter series does not get an
    # `as_of` from the series it replaced.
    base.setdefault("as_of", max(base["closes"]))
    return MP.build_export(**base)


def intel(tmp_path, ticker="ACME", today="", **kw):
    """A `MarketIntel` that made the real round trip through the filesystem.

    Published and re-read rather than constructed, because freshness is
    recomputed by the loader from the latest session -- an in-memory shortcut
    would assert on a staleness the product never actually calculates.
    """
    payload = export(ticker=ticker, **kw)
    MP.write_export(payload, tmp_path)
    return MP.load_export(tmp_path, ticker,
                          today=today or payload["as_of"])


def context(tmp_path, ticker="ACME", today="", **kw):
    return PK.ExternalContext(market=intel(tmp_path, ticker, today, **kw))


def market_context(tmp_path, ticker="ACME", today="", **kw):
    """The `brief.market_context` dict, via the presenter the webapp calls."""
    return PS.market_context_dict(context(tmp_path, ticker, today, **kw))


def absent_market_context(reason="no snapshot", ticker=""):
    """The same dict for the reasoned-absence case, which is not an error."""
    return PS.market_context_dict(
        PK.ExternalContext(market=MC.absent(reason, ticker)))


def malformed(tmp_path, raw, ticker="ACME", today="2026-07-31"):
    """What a founder gets when the PUBLISHED artefact is unreadable.

    Returns `(intel, market_context)`. The bytes are written to the real export
    path and read by the real loader, because the property under test is that
    the loader refuses -- asserting on a hand-built `absent()` would prove only
    that a constructor works.
    """
    path = MP.export_path(tmp_path, ticker)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw)
    loaded = MP.load_export(tmp_path, ticker, today=today)
    return loaded, PS.market_context_dict(PK.ExternalContext(market=loaded))
