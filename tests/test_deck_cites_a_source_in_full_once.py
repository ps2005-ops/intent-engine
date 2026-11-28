"""A deck gives each source in full once and cites it by number after
(prospect-98 round 8: 20 decks repeated source titles across slides)."""
from intent_engine.strategic_intelligence import slides as S


def _slide(i, cites):
    return {"id": f"s{i}", "title": f"Slide {i}", "kicker": "", "bullets": [
        {"text": f"Point {i}", "evidence": list(cites), "date": ""}]}


def test_second_citation_is_a_numbered_reference_to_the_first():
    html = S.render_deck([_slide(1, ["obs-a"]), _slide(2, ["obs-a", "obs-b"])],
                         company="Acme", run_id="r1",
                         cite_labels={"obs-a": "Acme triples revenue - TechCrunch", "obs-b": "Acme platform"})
    assert html.count("Acme triples revenue - TechCrunch") == 1
    assert "Source 1 (cited above)" in html
    assert html.count('/runs/r1/evidence/obs-a"') == 2        # every slide still links its evidence
