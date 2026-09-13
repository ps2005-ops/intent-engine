"""The neutral Market/Founder seam.

This package is joined to by two packages that must never see each other, so
it imports NEITHER. See `docs/execution/v5/ADR_COMPANY_DEMO_DOSSIER_ARCHITECTURE.md`
and the structural guard in `tests/test_the_dossier_seam_stays_neutral.py`.
"""
from intent_engine.demo_dossier.assembler import assemble
from intent_engine.demo_dossier.contracts import (FounderDemoSnapshot,
                                                  MarketDemoSnapshot,
                                                  founder_unavailable,
                                                  market_unavailable,
                                                  read_founder_snapshot,
                                                  read_market_snapshot)
from intent_engine.demo_dossier.diff import compare
from intent_engine.demo_dossier.dossier import CompanyDemoDossier
from intent_engine.demo_dossier.store import DossierStore
from intent_engine.demo_dossier.telemetry import DossierTelemetry

__all__ = ["assemble", "CompanyDemoDossier", "DossierStore",
           "DossierTelemetry", "FounderDemoSnapshot", "MarketDemoSnapshot",
           "compare", "founder_unavailable", "market_unavailable",
           "read_founder_snapshot", "read_market_snapshot"]
