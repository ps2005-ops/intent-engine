"""Accented characters with no foreign function words do not condemn a page.

MEASURED live on 61a7981, NVIDIA Corporation: `dropped=0/0/0/8` -- eight of
twelve documents refused by the language wall alone -- and the instrument
named them with the two densities that refused them:

    m0.00/a55.84     589 chars       m168.58/a8.58    2,329 chars
    m0.00/a41.19   9,977 chars       m123.96/a13.79  10,951 chars
    m0.00/a59.50     435 chars

The last two exceed both bars and are foreign by any reading. The first three
contain NOT ONE function word from any of the five languages the table covers
-- German, French, Spanish, Italian, Dutch -- while 4-6% of their characters
are accented. Prose in those languages cannot avoid " der ", " le ", " el ",
" per ", " een ".

This module's own rule: "refusing a real company is far worse than the
silence it was meant to replace, so the burden of proof sits on the
accusation." An accusation with no corroborating evidence does not meet it.
"""
from intent_engine.company_ingestion.readiness import (
    _accent_density, _foreign_marker_density, is_english,
)


def _doc(text, repeat=30):
    return {"text_content": text * repeat}


GERMAN = _doc("Die Gesellschaft und der Vorstand haben fuer das Geschaeft "
              "mit den Kunden eine Loesung entwickelt. ")
FRENCH = _doc("La societe et les dirigeants sont pour des resultats dans le "
              "marche sur nous. ")
SPANISH = _doc("El grupo y los clientes para una solucion con los productos "
               "son nuestra prioridad. ")
ITALIAN = _doc("Il gruppo e per i clienti con le soluzioni sono nostra "
               "priorita per gli anni. ")
ENGLISH = _doc("The registrant operates a national freight network and "
               "reports segment revenue after rebates. ", 40)
LEGAL = _doc("Item 1A. Risk Factors. The Company's results of operations "
             "may be adversely affected by regulatory action. ", 40)


def test_foreign_prose_is_still_refused():
    """THE CONTROLS THAT MUST NOT MOVE."""
    for name, doc in (("de", GERMAN), ("fr", FRENCH), ("es", SPANISH),
                      ("it", ITALIAN)):
        assert is_english(doc) is False, (
            name, _foreign_marker_density(doc), _accent_density(doc))


def test_english_is_read():
    assert is_english(ENGLISH) is True
    assert is_english(LEGAL) is True


def test_accents_without_function_words_are_not_condemned():
    """THE DEFECT. NVIDIA's shape: heavy accents, zero foreign markers."""
    # NOTE the fixture carries NO foreign function word. A first version
    # said "RTX für Zürich" and was correctly refused -- " für " is a German
    # marker, so that document had corroborating evidence and this rule
    # never claimed to spare it. NVIDIA's three measured at m0.00 exactly.
    doc = _doc("NVIDIA GeForce RTX at Zürich, São Paulo, Malmö and "
               "Brønnøysund resellers listed here. ", 8)
    assert _foreign_marker_density(doc) == 0.0, _foreign_marker_density(doc)
    assert _accent_density(doc) >= 5.0, _accent_density(doc)
    assert is_english(doc) is True, (
        _foreign_marker_density(doc), _accent_density(doc))


def test_a_short_accented_page_is_not_condemned():
    """Two of NVIDIA's eight were 435 and 589 characters."""
    doc = {"text_content": "Zürich Genève Köln Malmö Århus São Tomé Bergen "
                           "Trondheim Düsseldorf resellers and partners. " * 4}
    assert is_english(doc) is True


def test_accents_WITH_function_words_are_still_condemned():
    """The rule only removes the UNCORROBORATED accusation.

    THE FIXTURE ISOLATES THE ACCENT BRANCH. An earlier version used ordinary
    German prose, which trips the marker bar (>= 40) on its own -- so
    disabling the accent branch left it condemned anyway and the break proof
    said NOT_CAUGHT, correctly. This sits below BOTH marker bars (40, and 20
    for the combined branch) while carrying one real function word, so the
    accent branch is the only thing that can refuse it.
    """
    base = ("Zürich München Köln Düsseldorf São Paulo Malmö Århus "
            "Bronnoysund resellers and partners reported here with many "
            "accented place names appearing throughout this document which "
            "is otherwise ordinary English prose about the operations of "
            "the business and its segments. ")
    doc = {"text_content": base * 10 + " le "}
    assert 0 < _foreign_marker_density(doc) < 20, _foreign_marker_density(doc)
    assert _accent_density(doc) >= 5.0
    assert is_english(doc) is False


def test_the_marker_bar_alone_still_condemns():
    """A foreign page with no accents at all is unchanged."""
    doc = _doc("Het bedrijf en de klanten zijn voor een oplossing met de "
               "producten. ")
    assert _accent_density(doc) < 5.0
    assert is_english(doc) is False
