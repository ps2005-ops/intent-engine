"""The read box and "What matters now" must not print the same paragraph.

MEASURED 2026-11-28 (prospect-98 baseline): 57 intro/result pages printed the
standing reason in "The strategic read" and again as "What matters now" 01.
"""
from types import SimpleNamespace as NS

from intent_engine.founder_brief import steps as S


class _Read(NS):
    def __getattr__(self, name):          # every field the page does not set
        return None


def _st(text):
    return NS(text=text, standing="")


REASON = ("What kind of business this is has not been established: no regulator "
          "classifies this company.")


def _read(matters):
    return _Read(identity="", strategic_position="", standing=S.READ_UNIDENTIFIED,
                 central_question="What kind of business Acme is.", standing_reason=REASON,
                 level1_facts=(), what_matters_now=tuple(_st(t) for t in matters), options=())


def test_a_statement_the_read_box_made_is_not_repeated_below_it():
    html = S.render_intro(_read([REASON, "Pricing moved in March."]), run_id="r", company="Acme")
    assert html.count("has not been established: no regulator") == 1
    assert '<span class="n">01</span> Pricing moved in March.' in html


def test_nothing_left_means_no_empty_heading():
    html = S.render_intro(_read([REASON]), run_id="r", company="Acme")
    assert "What matters now" not in html
