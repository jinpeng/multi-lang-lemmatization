from api.backends.registry import Registry, lazy
from api.types import Capabilities, LemmaItem


class FakeBackend:
    lang = "xx"
    name = "fake"
    version = "1.0"
    pos_scheme = None
    capabilities = Capabilities()

    def option_specs(self):
        return {}

    def lemmatize(self, text, tokens, pos, options):
        return [LemmaItem(surface="a", lemma="a")]


class BrokenBackend:
    def __init__(self):
        raise RuntimeError("dictionary not found")


def test_registers_healthy_backend():
    reg = Registry()
    reg.register("xx", FakeBackend)
    entry = reg.get("xx")
    assert entry.status == "ok"
    assert entry.backend is not None


def test_failing_factory_degrades_instead_of_raising():
    reg = Registry()
    reg.register("yy", BrokenBackend)  # must not raise
    entry = reg.get("yy")
    assert entry is not None
    assert entry.status == "unavailable"
    assert "dictionary not found" in entry.reason
    assert entry.backend is None


def test_one_failure_does_not_affect_other_languages():
    reg = Registry()
    reg.register("xx", FakeBackend)
    reg.register("yy", BrokenBackend)
    assert reg.get("xx").status == "ok"
    assert reg.get("yy").status == "unavailable"


def test_unknown_language_returns_none():
    reg = Registry()
    assert reg.get("zz") is None


def test_all_is_sorted_by_language():
    reg = Registry()
    reg.register("zz", FakeBackend)
    reg.register("aa", FakeBackend)
    assert [e.lang for e in reg.all()] == ["aa", "zz"]


def test_missing_module_degrades_instead_of_crashing():
    """A backend package absent from the image must not kill startup."""
    reg = Registry()
    reg.register("xx", FakeBackend)
    reg.register("yy", lazy("api.backends.this_module_does_not_exist"))

    assert reg.get("xx").status == "ok"
    assert reg.get("yy").status == "unavailable"
    assert "ModuleNotFoundError" in reg.get("yy").reason


def test_lazy_defers_construction_until_called():
    """lazy() must not import at module scope, or the failure escapes the try."""
    calls = []

    class Spy(FakeBackend):
        def __init__(self):
            calls.append(1)

    factory = lazy("api.backends.registry")
    assert calls == []
    reg = Registry()
    # registry.build() does not exist -> degrades, proving the import happened
    # inside the factory rather than at decoration time.
    reg.register("zz", factory)
    assert reg.get("zz").status == "unavailable"
