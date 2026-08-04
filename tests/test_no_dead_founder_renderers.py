"""An unrouted founder renderer is a defect, so it cannot be committed.

WHY THIS GUARD EXISTS
---------------------
Three cycles were spent on one contradiction: the primary screen said "No
strategic conclusion is being asserted about this company" while the deck one
click away carried two options and a recommendation. The cause was
`render_brief` -- a second founder renderer, in a file nothing served, built on
a different source of truth (`FounderBrief.key_insight`) than the composed
`FounderDecision`. It survived because it had tests. Tests kept it green; no
route kept it honest.

The pattern repeated three more times before this guard existed:

    render_brief            deleted -- built the primary screen from a field
                            that is None whenever the thesis view is withheld
    _brief_page             deleted -- `/brief` has routed to
                            `_executive_brief_page` since the deep-documents
                            cycle
    render_market           deleted -- market context reaches the page through
                            `layers.build_dashboard`
    render_executive_brief  deleted -- the executive brief is served from the
                            shared dossier

So the rule is structural rather than advisory: a renderer with no caller in
`src/` fails this test. Delete it, or wire the route. Moving its contracts onto
the surface that actually serves them is the point -- a contract proven against
HTML no founder can reach proves nothing about the product.

WHY CALLER-REACHABILITY RATHER THAN ROUTE-TABLE PARSING
-------------------------------------------------------
The router dispatches on split path segments across several branches, so a
literal route table does not exist to compare against. "Referenced anywhere in
`src/` outside its own definition" is the weaker claim, but it is the one that
actually catches the failure this guard is for: every renderer above was dead
by this measure, and no live renderer is.
"""
import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"

#: Deliberately empty, and meant to stay that way. Adding a name here is the
#: decision to ship a founder surface nothing can reach -- if that is ever
#: genuinely right, the reason belongs beside the name.
EXEMPT: dict = {}


def _defs(path, prefix, *, methods_of=None):
    """(name, lineno) for top-level functions, or methods of one class."""
    tree = ast.parse(path.read_text())
    if methods_of is None:
        return [(n.name, n.lineno) for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name.startswith(prefix)]
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == methods_of:
            return [(n.name, n.lineno) for n in node.body
                    if isinstance(n, ast.FunctionDef)
                    and n.name.startswith(prefix)]
    raise AssertionError(f"class {methods_of} not found in {path}")


def _callers(name, own_file):
    """Files under src/ that mention `name` other than where it is defined.

    The defining file counts only when the mention is not the `def` line
    itself, so a helper used within its own module stays reachable.
    """
    hits = []
    for py in SRC.rglob("*.py"):
        text = py.read_text()
        if name not in text:
            continue
        if py == own_file:
            body = [ln for ln in text.splitlines()
                    if name in ln and not ln.lstrip().startswith(
                        (f"def {name}(", f"async def {name}("))
                    and not ln.lstrip().startswith("#")]
            # A docstring naming a deleted renderer must not resurrect it.
            body = [ln for ln in body if "`" not in ln]
            if body:
                hits.append(py.name)
        else:
            hits.append(py.name)
    return hits


def test_every_founder_renderer_has_a_caller():
    path = SRC / "intent_engine/founder_brief/render.py"
    dead = [(n, ln) for n, ln in _defs(path, "render_")
            if n not in EXEMPT and not _callers(n, path)]
    assert not dead, (
        "unrouted founder renderer(s) in founder_brief/render.py: "
        + ", ".join(f"{n} (line {ln})" for n, ln in dead)
        + " -- delete it, or wire a route and move its contracts onto the "
          "surface that serves them")


def test_every_webapp_page_method_has_a_caller():
    path = SRC / "intent_engine/webapp/app.py"
    dead = [(n, ln) for n, ln in _defs(path, "_", methods_of="WebApp")
            if n.endswith("_page") and n not in EXEMPT
            and not _callers(n, path)]
    assert not dead, (
        "unrouted page method(s) on WebApp: "
        + ", ".join(f"{n} (line {ln})" for n, ln in dead)
        + " -- the router dispatches nothing to these")


def test_the_guard_would_actually_catch_a_dead_renderer():
    """The guard's own break proof.

    A guard that passes because its detector is broken is worse than none, so
    the detector is checked against a name that genuinely has no caller.
    """
    path = SRC / "intent_engine/founder_brief/render.py"
    assert not _callers("render_a_thing_that_does_not_exist", path)
    # ...and against one that genuinely does.
    assert _callers("render_dashboard", path)


def test_the_deleted_renderers_stay_deleted():
    """Named individually: each one cost a cycle to find."""
    render = (SRC / "intent_engine/founder_brief/render.py").read_text()
    app = (SRC / "intent_engine/webapp/app.py").read_text()
    for gone in ("def render_brief(", "def render_market(",
                 "def render_executive_brief("):
        assert gone not in render, f"{gone} came back"
    assert "def _brief_page(" not in app, "_brief_page came back"
