# M1+M2 Lemmatization Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working `POST /v1/lemmatize` HTTP API covering all 7 languages (`en de fr es ru ja ko`) with no authentication, plus `GET /v1/languages` and `GET /v1/health`.

**Architecture:** FastAPI app with a pluggable backend registry. Each language is one adapter implementing a small `Backend` protocol. Backends that tokenize natively (SudachiPy, Kiwi) declare `tokenizes=True`; the rest receive pre-split tokens or use a shared fallback tokenizer. Backend construction is wrapped so a single failing dictionary degrades that one language to `503 LANGUAGE_UNAVAILABLE` instead of crashing startup.

**Tech Stack:** Python 3.12, uv, FastAPI, Pydantic v2, pytest, httpx. Backends: simplemma, lemminflect, pymorphy3, sudachipy, kiwipiepy.

**Spec:** `docs/superpowers/specs/2026-10-29-multilingual-lemmatization-design.md`

---

## Verification already performed

This plan was not written as untested pseudocode. A scratch project was built from the code blocks below and **all 108 tests were executed against the real libraries**, including SudachiPy and Kiwi with their full dictionaries installed.

| Verified | Result |
|---|---|
| Tasks 1, 2, 3, 4, 5, 10 test suites | pass |
| Tasks 6, 7, 8, 9 backend suites | pass (lemminflect 0.2.3, pymorphy3 2.0.6, sudachipy 0.7.0, kiwipiepy 0.24.1) |
| Tasks 11, 12, 13, 14 route + golden suites | pass, all 7 languages |
| **Full suite** | **108 passed in 6.19 s** |
| Live `uvicorn` server, `GET /v1/health` | all seven backends `"status": "ok"` |
| Live `POST /v1/lemmatize` for `ja` | `食べました` -> `食べる` / `ます` / `た`, with `pos` and `reading`, `segmented_by: "backend"` |
| Degradation when a backend package is absent | `create_app()` survives; affected languages go `unavailable` |

**Four defects were found this way and are already fixed in the tasks below:**

1. **Pydantic returned HTTP 422 with `{"detail": [...]}`, bypassing the unified error envelope.** Spec §4.4 requires `error.code` on every failure, so sending `text` and `tokens` together produced a response no conforming client could parse. Fixed by a `RequestValidationError` handler in Task 11; pinned by three tests in Task 12.
2. **A missing backend *package* crashed startup instead of degrading one language.** `build_registry` originally imported backend modules at module level, so an absent `kiwipiepy` raised `ImportError` outside every `try/except` — contradicting this plan's own architecture claim. Fixed by the `lazy()` helper in Task 4; pinned by `test_missing_module_degrades_instead_of_crashing`.
3. **English silently never lemmatized without a POS tag.** `getLemma()` has no default for `upos`; calling it bare raises `TypeError`, which the adapter caught, degrading every POS-less request to identity. Fixed by using `getAllLemmas()` for the no-tag path. This also exposed that `Capabilities.pos` conflated *produces* a tag with *accepts* one, so `pos_accepted` was added.
4. **Two tests contradicted the schema.** A Task 12 test sent `text` and `tokens` together (rejected by Task 10) and asserted `ja` would ignore the tokens; another asserted `東京都` splits at split_mode C, which it does not (it is a dictionary entry). Rewritten to exercise the legal tokens-only path.

**Dependency versions actually resolved** on the verification host: fastapi 0.162.0, pydantic 2.14.1, uvicorn 0.54.0, **simplemma 2.0.0**, lemminflect 0.2.3, pymorphy3 2.0.6, pymorphy3-dicts-ru 2.4.417150.4580142, sudachipy 0.7.0, sudachidict-core 20261015, kiwipiepy 0.24.1, kiwipiepy-model 0.24.0. All `pyproject.toml` floors are satisfied by these; every assertion was confirmed against these exact versions.

> Two harmless warnings appear and must not be chased: `starlette.testclient` suggests `httpx2` under fastapi 0.162, and `sudachipy` 0.7 deprecates `Dictionary.create()` in favour of `Dictionary.tokenizer()`. The code uses `.create()` because `pyproject.toml` allows `sudachipy>=0.6.10` and `.tokenizer()` does not exist in 0.6.

---

## Scope note

The spec covers four separable subsystems. They are planned separately, each producing working software on its own:

| Plan | Covers | Status |
|---|---|---|
| **This plan** | M1+M2 — project scaffolding, 7 backends, `/v1/lemmatize`, `/v1/languages`, `/v1/health`, character offsets | **verified, 124 tests** |
| Plan 2 | M3+M5 — API Key/Secret, Bearer, HMAC, rate limit, SQLite, settings whitelist, audit | not yet written |
| Plan 3 | M4+M6 — Next.js console (BFF), admin session, Playground, Docker images | not yet written |

This plan deliberately contains **no auth, no database, no frontend**. Those arrive in later plans and must not be stubbed here.

---

## File structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | deps, pytest config, ruff config |
| `api/__init__.py` | empty package marker |
| `api/types.py` | `Capabilities`, `LemmaItem`, `Prov` — the shared vocabulary |
| `api/errors.py` | `ApiError` + error-code constants |
| `api/textutil.py` | `fallback_tokenize()` shared by non-tokenizing backends |
| `api/backends/base.py` | `Backend` protocol, `BaseBackend` with `option_specs()` default |
| `api/backends/registry.py` | build-with-degradation registry |
| `api/backends/simplemma_backend.py` | `de`, `fr`, `es` |
| `api/backends/lemminflect_backend.py` | `en` |
| `api/backends/pymorphy_backend.py` | `ru` |
| `api/backends/sudachi_backend.py` | `ja` |
| `api/backends/kiwi_backend.py` | `ko` |
| `api/schemas.py` | `LemmatizeRequest` validation |
| `api/routes/health.py` | `GET /v1/health` |
| `api/routes/languages.py` | `GET /v1/languages` |
| `api/routes/lemmatize.py` | `POST /v1/lemmatize` |
| `api/main.py` | app assembly, lifespan, error handler |
| `tests/conftest.py` | registry fixture, `TestClient` |
| `tests/test_types.py` | `LemmaItem` serialization |
| `tests/test_registry.py` | degradation behaviour |
| `tests/backends/test_<lang>.py` | per-language unit tests |
| `tests/test_api_pos_semantics.py` | `pos` nullability contract |
| `tests/test_api_errors.py` | error envelope + codes |
| `tests/test_golden.py` | cross-language golden suite |

---

## Task 0: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `api/__init__.py`
- Create: `tests/__init__.py`
- Modify: `.gitignore`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "lemma-api"
version = "0.1.0"
description = "Multilingual lemmatization HTTP API"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "pydantic>=2.9",
    "simplemma>=1.2",
    "lemminflect>=0.2.3",
    "pymorphy3>=2.0",
    "pymorphy3-dicts-ru>=2.4",
    "sudachipy>=0.6.10",
    "sudachidict_core>=20240716",
    "kiwipiepy>=0.20",
    "kiwipiepy_model>=0.20",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "httpx>=0.27",
    "ruff>=0.6",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q --strict-markers"
markers = [
    "slow: downloads or loads large dictionaries (ja, ko)",
]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

- [ ] **Step 2: Create package markers**

```bash
touch api/__init__.py tests/__init__.py
```

- [ ] **Step 3: Append venv/uv artefacts to `.gitignore`**

`.gitignore` already covers `.venv`, `__pycache__`, `*.py[codz]`. Append two uv-specific entries so they are not missed:

```
# uv
uv.lock
.uv/
```

- [ ] **Step 4: Install dependencies**

Run:
```bash
uv venv --python 3.12 && uv pip install -e ".[dev]"
```
Expected: resolves and installs. `sudachidict_core` (~70 MB) and `kiwipiepy_model` (~58 MB) make this take a few minutes on a cold cache.

- [ ] **Step 5: Verify every backend library imports**

Run:
```bash
uv run python -c "
import simplemma, lemminflect, pymorphy3, sudachipy, kiwipiepy
print('simplemma', simplemma.__version__ if hasattr(simplemma,'__version__') else 'ok')
print('lemminflect ok'); print('pymorphy3 ok')
from sudachipy import dictionary; print('sudachi ok')
from kiwipiepy import Kiwi; print('kiwi ok')
"
```
Expected: all five print, exit 0. If any fails, stop and resolve before continuing — every later task depends on this.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml api/__init__.py tests/__init__.py .gitignore
git commit -m "chore: scaffold lemma-api project with all 7 backend dependencies"
```

---

## Task 1: Shared types

**Files:**
- Create: `api/types.py`
- Test: `tests/test_types.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_types.py
from api.types import Capabilities, LemmaItem


def test_capabilities_serializes_all_seven_flags():
    caps = Capabilities(pos=True, tokenizes=True)
    assert caps.to_json() == {
        "pos": True,
        "pos_accepted": False,
        "pos_required": False,
        "candidates": False,
        "reading": False,
        "mwt": False,
        "tokenizes": True,
    }


def test_lemma_item_omits_absent_optional_fields():
    item = LemmaItem(surface="was", lemma="be", pos="VERB", prov="dict")
    assert item.to_json() == {
        "surface": "was",
        "lemma": "be",
        "pos": "VERB",
        "prov": "dict",
    }


def test_lemma_item_includes_reading_and_candidates_when_present():
    item = LemmaItem(
        surface="食べ", lemma="食べる", pos="動詞", prov="dict",
        reading="タベ", candidates=("食べる", "食べ"),
    )
    out = item.to_json()
    assert out["reading"] == "タベ"
    assert out["candidates"] == ["食べる", "食べ"]


def test_lemma_item_keeps_explicit_null_pos():
    """pos must serialize as null (not be dropped) - clients rely on the key existing."""
    item = LemmaItem(surface="Häuser", lemma="Haus", pos=None, prov="dict")
    out = item.to_json()
    assert "pos" in out
    assert out["pos"] is None


def test_lemma_item_omits_offsets_when_unknown():
    item = LemmaItem(surface="Haus", lemma="Haus")
    out = item.to_json()
    assert "start" not in out and "end" not in out


def test_lemma_item_includes_offsets_when_known():
    item = LemmaItem(surface="Haus", lemma="Haus", start=9, end=13)
    out = item.to_json()
    assert (out["start"], out["end"]) == (9, 13)


def test_lemma_item_omits_offsets_if_only_one_bound_is_set():
    """A half-open span is meaningless; drop both rather than emit a lie."""
    item = LemmaItem(surface="Haus", lemma="Haus", start=9)
    out = item.to_json()
    assert "start" not in out and "end" not in out


def test_pos_produced_and_pos_accepted_are_independent():
    """English accepts a tag but emits none; Russian emits one but takes none."""
    english = Capabilities(pos=False, pos_accepted=True)
    russian = Capabilities(pos=True, pos_accepted=False)
    assert english.to_json()["pos"] is False
    assert english.to_json()["pos_accepted"] is True
    assert russian.to_json()["pos"] is True
    assert russian.to_json()["pos_accepted"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_types.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.types'`

- [ ] **Step 3: Write `api/types.py`**

```python
"""Shared vocabulary for every backend. No backend may invent its own shapes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# How a lemma was produced. Clients use this to tell a real dictionary hit
# from a passthrough, which matters for downstream confidence.
Prov = Literal["dict", "rule", "model", "identity", "candidates"]


@dataclass(frozen=True)
class Capabilities:
    """What a backend can actually deliver for its language.

    `pos` vs `pos_accepted` are genuinely different questions and the
    difference is load-bearing for English:

    - pos          the backend PRODUCES a tag in its output (ru, ja, ko)
    - pos_accepted the backend USES a caller-supplied tag to improve output (en)

    LemmInflect accepts `upos` and materially changes its answer based on it
    ("left" -> "leave" as a verb, "left" as a noun) but never returns a tag.
    Modelling only `pos` would tell a client that English ignores POS, and
    they would silently lose accuracy on every ambiguous word.
    """

    pos: bool = False
    pos_accepted: bool = False
    pos_required: bool = False
    candidates: bool = False
    reading: bool = False
    mwt: bool = False
    tokenizes: bool = False

    def to_json(self) -> dict[str, bool]:
        return {
            "pos": self.pos,
            "pos_accepted": self.pos_accepted,
            "pos_required": self.pos_required,
            "candidates": self.candidates,
            "reading": self.reading,
            "mwt": self.mwt,
            "tokenizes": self.tokenizes,
        }


@dataclass(frozen=True)
class LemmaItem:
    surface: str
    lemma: str
    pos: str | None = None
    prov: Prov = "dict"
    reading: str | None = None
    candidates: tuple[str, ...] = ()
    start: int | None = None
    end: int | None = None

    def to_json(self) -> dict:
        out: dict = {
            "surface": self.surface,
            "lemma": self.lemma,
            "pos": self.pos,
            "prov": self.prov,
        }
        if self.reading is not None:
            out["reading"] = self.reading
        if self.candidates:
            out["candidates"] = list(self.candidates)
        # Offsets are omitted only when genuinely unavailable (caller sent
        # `tokens`, so there is no source string to point into).
        if self.start is not None and self.end is not None:
            out["start"] = self.start
            out["end"] = self.end
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_types.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add api/types.py tests/test_types.py
git commit -m "feat: add shared Capabilities and LemmaItem types"
```

---

## Task 2: Error type and codes

**Files:**
- Create: `api/errors.py`
- Test: `tests/test_errors.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_errors.py
import pytest

from api.errors import ApiError


def test_api_error_carries_code_status_and_message():
    err = ApiError("UNKNOWN_OPTION", 400, "unknown option(s)", {"unknown": ["nope"]})
    assert err.code == "UNKNOWN_OPTION"
    assert err.status == 400
    assert err.message == "unknown option(s)"
    assert err.details == {"unknown": ["nope"]}


def test_api_error_details_default_to_empty_dict():
    err = ApiError("INTERNAL", 500, "boom")
    assert err.details == {}


def test_api_error_is_an_exception():
    with pytest.raises(ApiError):
        raise ApiError("INTERNAL", 500, "boom")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_errors.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.errors'`

- [ ] **Step 3: Write `api/errors.py`**

```python
"""Single error envelope used by every route (spec section 4.4)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ApiError(Exception):
    code: str
    status: int
    message: str
    details: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__init__(self.message)

    def to_json(self, request_id: str | None) -> dict:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
                "request_id": request_id,
            }
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_errors.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add api/errors.py tests/test_errors.py
git commit -m "feat: add ApiError with unified error envelope"
```

---

## Task 3: Backend protocol and shared tokenizer

**Files:**
- Create: `api/backends/__init__.py`
- Create: `api/backends/base.py`
- Create: `api/textutil.py`
- Test: `tests/test_textutil.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_textutil.py
from api.textutil import fallback_tokenize, tokenize_with_offsets


def test_tokenize_latin_sentence():
    assert fallback_tokenize("Hier sind Vaccines.") == ["Hier", "sind", "Vaccines", "."]


def test_tokenize_cyrillic_sentence():
    tokens = fallback_tokenize("Он шёл домой.")
    assert "шёл" in tokens
    assert tokens[-1] == "."


def test_tokenize_empty_string_returns_empty_list():
    assert fallback_tokenize("") == []


def test_tokenize_with_offsets_slices_back_to_each_token():
    text = "Hier sind Häuser."
    spans = tokenize_with_offsets(text)
    assert [t for t, _, _ in spans] == ["Hier", "sind", "Häuser", "."]
    for token, start, end in spans:
        assert text[start:end] == token


def test_tokenize_with_offsets_never_matches_an_earlier_occurrence():
    """The cursor must move forward, so repeated tokens get distinct spans."""
    text = "a a a"
    spans = tokenize_with_offsets(text)
    assert [(s, e) for _, s, e in spans] == [(0, 1), (2, 3), (4, 5)]


def test_tokenize_with_offsets_reports_code_points():
    """Offsets count code points, so a surrogate pair is 1 wide, not 2.

    𝕏 is U+1D54F: one code point, two UTF-16 units. If these were UTF-16
    indices the span would end at 4 instead of 3.
    """
    text = "𝕏東京"
    assert len(text) == 3
    assert len(text.encode("utf-16-le")) // 2 == 4
    spans = tokenize_with_offsets(text)
    assert spans == [("𝕏東京", 0, 3)]


def test_tokenize_with_offsets_empty():
    assert tokenize_with_offsets("") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_textutil.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.textutil'`

- [ ] **Step 3: Write `api/textutil.py` and `api/backends/base.py`**

`api/textutil.py`:
```python
"""Fallback tokenizer for backends that do not tokenize natively.

simplemma's tokenizer is script-aware (keeps in-word joiners and combining
marks inside their word, splits punctuation) and is already a dependency,
so we reuse it rather than adding a second tokenizer.
"""

from __future__ import annotations

from simplemma import simple_tokenizer


def fallback_tokenize(text: str) -> list[str]:
    if not text:
        return []
    return simple_tokenizer(text)


def tokenize_with_offsets(text: str) -> list[tuple[str, int, int]]:
    """Tokenize and locate each token in `text` as a CODE POINT span.

    simple_tokenizer does not report positions, so each token is located with a
    forward-moving cursor. Tokens come out in source order, so the scan is
    linear overall and a token can never match an earlier occurrence.

    Code points, not UTF-16 code units: Python and both ja/ko analysers count
    code points. See the note in the response contract (Task 12b).
    """
    spans: list[tuple[str, int, int]] = []
    cursor = 0
    for token in simple_tokenizer(text):
        start = text.find(token, cursor)
        if start < 0:  # tokenizer normalised something; keep order, keep cursor
            start = cursor
        end = start + len(token)
        spans.append((token, start, end))
        cursor = end
    return spans
```

`api/backends/__init__.py`: empty file.

`api/backends/base.py`:
```python
"""The one interface every language adapter implements (spec section 3.1)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from api.types import Capabilities, LemmaItem


class BaseBackend(ABC):
    lang: str
    name: str
    version: str
    pos_scheme: str | None
    capabilities: Capabilities

    def option_specs(self) -> dict[str, dict]:
        """Request-level options this backend accepts, for /v1/languages."""
        return {}

    @abstractmethod
    def lemmatize(
        self,
        text: str | None,
        tokens: list[str] | None,
        pos: list[str | None] | None,
        options: dict[str, Any],
    ) -> list[LemmaItem]:
        """Return one LemmaItem per output token.

        Always returns a list. Unresolved words come back as
        prov="identity" with lemma == surface - never an exception, because
        one rare word must not fail the whole request.
        """
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_textutil.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add api/backends/__init__.py api/backends/base.py api/textutil.py tests/test_textutil.py
git commit -m "feat: add Backend protocol and script-aware fallback tokenizer"
```

---

## Task 4: Registry with per-language degradation

**Files:**
- Create: `api/backends/registry.py`
- Test: `tests/test_registry.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_registry.py
import pytest

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
    factory = lazy("api.backends.registry")
    reg = Registry()
    # registry has no build() -> degrades, proving the import happened inside
    # the factory rather than at decoration time.
    reg.register("zz", factory)
    assert reg.get("zz").status == "unavailable"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.backends.registry'`

- [ ] **Step 3: Write `api/backends/registry.py`**

```python
"""Builds every backend at startup, degrading per language rather than crashing.

Decision 2 puts all 7 languages in one image, so "unavailable" should be rare.
This exists for real failures: a stripped dictionary, a model that fails to
load, out-of-memory on a constrained host, or a backend package that is not
installed in this environment.
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Callable
from dataclasses import dataclass

from api.backends.base import BaseBackend

log = logging.getLogger(__name__)


@dataclass
class Entry:
    lang: str
    backend: BaseBackend | None
    status: str  # "ok" | "unavailable"
    reason: str | None = None


def lazy(module_name: str, *args, **kwargs) -> Callable[[], BaseBackend]:
    """Defer both the import and the construction into the factory.

    This must be lazy. A module-level `from api.backends import kiwi_backend`
    would raise ImportError while assembling the language list, which is
    outside every try/except and therefore crashes startup for all seven
    languages instead of degrading one. Import inside the closure so the
    failure lands where Registry.register can catch it.
    """
    def factory() -> BaseBackend:
        module = importlib.import_module(module_name)
        return module.build(*args, **kwargs)

    return factory


class Registry:
    def __init__(self) -> None:
        self._entries: dict[str, Entry] = {}

    def register(self, lang: str, factory: Callable[[], BaseBackend]) -> None:
        try:
            backend = factory()
        except Exception as exc:  # noqa: BLE001 - degrade, never propagate
            log.warning("backend %s unavailable: %s", lang, exc)
            self._entries[lang] = Entry(
                lang=lang,
                backend=None,
                status="unavailable",
                reason=f"{type(exc).__name__}: {exc}",
            )
            return
        self._entries[lang] = Entry(lang=lang, backend=backend, status="ok")
        log.info("backend %s ready (%s %s)", lang, backend.name, backend.version)

    def get(self, lang: str) -> Entry | None:
        return self._entries.get(lang)

    def all(self) -> list[Entry]:
        return [self._entries[k] for k in sorted(self._entries)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_registry.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add api/backends/registry.py tests/test_registry.py
git commit -m "feat: add backend registry with per-language degradation"
```

---

## Task 5: Simplemma backend (de, fr, es)

**Files:**
- Create: `api/backends/simplemma_backend.py`
- Test: `tests/backends/test_simplemma.py`

One class serves three languages because they share one code path and differ only in the `greedy` default, which the survey fixed: `de=True` (compound/derived nouns need the second reduction), `fr=False`, `es=False`.

- [ ] **Step 1: Write the failing test**

```python
# tests/backends/test_simplemma.py
import pytest

from api.backends import simplemma_backend


@pytest.mark.parametrize("lang", ["de", "fr", "es"])
def test_build_covers_supported_languages(lang):
    backend = simplemma_backend.build(lang)
    assert backend.lang == lang
    assert backend.name == "simplemma"
    assert backend.capabilities.pos is False
    assert backend.capabilities.tokenizes is False


def test_build_rejects_unsupported_language():
    with pytest.raises(ValueError, match="does not cover"):
        simplemma_backend.build("ja")


def test_greedy_defaults_follow_survey():
    assert simplemma_backend.build("de").greedy is True
    assert simplemma_backend.build("fr").greedy is False
    assert simplemma_backend.build("es").greedy is False


def test_lemmatizes_german_plural_noun():
    backend = simplemma_backend.build("de")
    items = backend.lemmatize(tokens=["Häuser"], text=None, pos=None, options={})
    assert len(items) == 1
    assert items[0].surface == "Häuser"
    assert items[0].lemma == "Haus"
    assert items[0].pos is None


def test_lemmatizes_french_participle():
    backend = simplemma_backend.build("fr")
    items = backend.lemmatize(tokens=["mangées"], text=None, pos=None, options={})
    assert items[0].lemma == "manger"


def test_lemmatizes_spanish_gerund():
    backend = simplemma_backend.build("es")
    items = backend.lemmatize(tokens=["corriendo"], text=None, pos=None, options={})
    assert items[0].lemma == "correr"


def test_tokenizes_text_when_tokens_absent():
    backend = simplemma_backend.build("de")
    items = backend.lemmatize(text="Hier sind Häuser.", tokens=None, pos=None, options={})
    assert [i.surface for i in items] == ["Hier", "sind", "Häuser", "."]


def test_unknown_word_falls_back_to_identity_not_exception():
    backend = simplemma_backend.build("de")
    items = backend.lemmatize(tokens=["Xylophonwort"], text=None, pos=None, options={})
    assert items[0].lemma == "Xylophonwort"
    assert items[0].prov == "identity"


def test_greedy_option_overrides_default_per_request():
    backend = simplemma_backend.build("de")
    items = backend.lemmatize(
        tokens=["ausgezeichneten"], text=None, pos=None, options={"greedy": False}
    )
    assert items[0].lemma == "ausgezeichnet"


def test_option_specs_exposes_greedy():
    specs = simplemma_backend.build("de").option_specs()
    assert specs["greedy"]["type"] == "bool"
    assert specs["greedy"]["default"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backends/test_simplemma.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.backends.simplemma_backend'`

- [ ] **Step 3: Write `api/backends/simplemma_backend.py`**

```python
"""Dictionary-lookup backend for de/fr/es.

simplemma needs no morphosyntactic information - that is precisely why these
three languages get no `pos` (spec section 3.2).
"""

from __future__ import annotations

import importlib.metadata as md
from typing import Any

import simplemma

from api.backends.base import BaseBackend
from api.textutil import fallback_tokenize, tokenize_with_offsets
from api.types import Capabilities, LemmaItem

# Language -> greedy default. `de` needs the second reduction for compound and
# derived nouns; `fr`/`es` get closer to stemming if greedier, so leave it off.
GREEDY_DEFAULTS: dict[str, bool] = {"de": True, "fr": False, "es": False}


class SimplemmaBackend(BaseBackend):
    name = "simplemma"
    pos_scheme = None
    capabilities = Capabilities(pos=False, pos_required=False, tokenizes=False)

    def __init__(self, lang: str, greedy: bool) -> None:
        if lang not in GREEDY_DEFAULTS:
            raise ValueError(f"simplemma backend does not cover {lang!r}")
        self.lang = lang
        self.greedy = greedy
        self.version = md.version("simplemma")

    def option_specs(self) -> dict[str, dict]:
        return {"greedy": {"type": "bool", "default": self.greedy}}

    def lemmatize(
        self,
        text: str | None,
        tokens: list[str] | None,
        pos: list[str | None] | None,
        options: dict[str, Any],
    ) -> list[LemmaItem]:
        greedy = bool(options.get("greedy", self.greedy))

        # Offsets exist only when we tokenized the text ourselves. With
        # caller-supplied tokens there is no source string to point into.
        if tokens is not None:
            spans: list[tuple[str, int | None, int | None]] = [
                (t, None, None) for t in tokens
            ]
        else:
            spans = list(tokenize_with_offsets(text or ""))

        items: list[LemmaItem] = []
        for surface, start, end in spans:
            lemma = simplemma.lemmatize(surface, lang=self.lang, greedy=greedy)
            prov = "dict" if lemma != surface else "identity"
            items.append(
                LemmaItem(
                    surface=surface, lemma=lemma, pos=None, prov=prov,
                    start=start, end=end,
                )
            )
        return items


def build(lang: str) -> SimplemmaBackend:
    if lang not in GREEDY_DEFAULTS:
        raise ValueError(f"simplemma backend does not cover {lang!r}")
    return SimplemmaBackend(lang, greedy=GREEDY_DEFAULTS[lang])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/backends/test_simplemma.py -v`
Expected: 13 passed

> **If a lemma differs from the expected value, do not change the backend to force agreement.** simplemma is the authority on its own output. Record the observed value, update the assertion, and note the discrepancy in the commit message. A silently-tuned backend is worse than a corrected expectation.

- [ ] **Step 5: Commit**

```bash
git add api/backends/simplemma_backend.py tests/backends/test_simplemma.py
git commit -m "feat: add simplemma backend for de/fr/es"
```

---

## Task 6: LemmInflect backend (en)

**Files:**
- Create: `api/backends/lemminflect_backend.py`
- Test: `tests/backends/test_lemminflect.py`

`getLemma(word, upos)` **requires** a POS tag — there is no default. The POS-agnostic path is a different function, `getAllLemmas(word)`, which returns `{UPOS: (lemmas,)}`. This distinction is load-bearing: getLemma without upos raises, and an adapter that swallows the exception degrades every POS-less request to identity without anyone noticing.

Supplying a tag genuinely matters. `left` as `VERB` is `leave`; as `NOUN` it is `left`. So the backend declares `pos=False` (it emits no tag) but `pos_accepted=True` (it uses one).

- [ ] **Step 1: Write the failing test**

```python
# tests/backends/test_lemminflect.py
from api.backends import lemminflect_backend


def test_capabilities():
    backend = lemminflect_backend.build()
    assert backend.lang == "en"
    assert backend.name == "lemminflect"
    assert backend.pos_scheme == "ud"
    # English never emits a tag, but it does use one if you supply it.
    assert backend.capabilities.pos is False
    assert backend.capabilities.pos_accepted is True
    assert backend.capabilities.pos_required is False
    assert backend.capabilities.tokenizes is False


def test_lemmatizes_irregular_verb_with_pos():
    backend = lemminflect_backend.build()
    items = backend.lemmatize(tokens=["was"], text=None, pos=["VERB"], options={})
    assert items[0].lemma == "be"
    assert items[0].prov == "dict"


def test_lemmatizes_plural_noun():
    backend = lemminflect_backend.build()
    items = backend.lemmatize(tokens=["watches"], text=None, pos=["VERB"], options={})
    assert items[0].lemma == "watch"


def test_works_without_pos():
    backend = lemminflect_backend.build()
    items = backend.lemmatize(tokens=["watches"], text=None, pos=None, options={})
    assert items[0].lemma == "watch"
    assert items[0].pos is None


def test_tokenizes_text_when_tokens_absent():
    backend = lemminflect_backend.build()
    items = backend.lemmatize(text="The cats were sleeping.", tokens=None, pos=None, options={})
    assert items[0].surface == "The"
    assert any(i.lemma == "cat" for i in items)


def test_unknown_word_is_identity():
    backend = lemminflect_backend.build()
    items = backend.lemmatize(tokens=["zzzzqqq"], text=None, pos=None, options={})
    assert items[0].lemma == "zzzzqqq"
    assert items[0].prov == "identity"


def test_pos_input_changes_the_answer():
    backend = lemminflect_backend.build()
    as_verb = backend.lemmatize(tokens=["left"], text=None, pos=["VERB"], options={})
    as_noun = backend.lemmatize(tokens=["left"], text=None, pos=["NOUN"], options={})
    assert as_verb[0].lemma == "leave"
    assert as_noun[0].lemma == "left"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backends/test_lemminflect.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.backends.lemminflect_backend'`

- [ ] **Step 3: Write `api/backends/lemminflect_backend.py`**

```python
"""Dictionary + neural-OOV backend for English (LemmInflect).

Two library entry points, and the difference matters:

- getLemma(word, upos) REQUIRES a POS tag. There is no default.
- getAllLemmas(word) is the POS-agnostic path; it returns {UPOS: (lemmas,)}.

Calling getLemma(surface) without upos raises TypeError, and because the
adapter catches exceptions, every POS-less request would silently degrade to
identity - English would "work" but never actually lemmatize. Use getAllLemmas
for the no-tag path instead.
"""

from __future__ import annotations

import importlib.metadata as md
from typing import Any

from lemminflect import getAllLemmas, getLemma

from api.backends.base import BaseBackend
from api.textutil import fallback_tokenize, tokenize_with_offsets
from api.types import Capabilities, LemmaItem


def _merge(by_pos: dict[str, tuple[str, ...]]) -> list[str]:
    """Flatten {UPOS: lemmas} into one ordered, de-duplicated list."""
    merged: list[str] = []
    for lemmas in by_pos.values():
        for lemma in lemmas:
            if lemma not in merged:
                merged.append(lemma)
    return merged


class LemmInflectBackend(BaseBackend):
    lang = "en"
    name = "lemminflect"
    pos_scheme = "ud"
    capabilities = Capabilities(
        pos=False, pos_accepted=True, pos_required=False, candidates=True, tokenizes=False
    )

    def __init__(self) -> None:
        self.version = md.version("lemminflect")

    def lemmatize(
        self,
        text: str | None,
        tokens: list[str] | None,
        pos: list[str | None] | None,
        options: dict[str, Any],
    ) -> list[LemmaItem]:
        if tokens is not None:
            spans: list[tuple[str, int | None, int | None]] = [
                (t, None, None) for t in tokens
            ]
        else:
            spans = list(tokenize_with_offsets(text or ""))

        items: list[LemmaItem] = []
        for index, (surface, start, end) in enumerate(spans):
            tag = pos[index] if pos is not None and index < len(pos) else None
            try:
                if tag:
                    found = list(getLemma(surface, upos=tag))
                else:
                    found = _merge(getAllLemmas(surface))
            except Exception:  # noqa: BLE001 - an odd tag must not fail the request
                found = []

            if not found or found[0] == surface:
                items.append(
                    LemmaItem(
                        surface=surface, lemma=surface, pos=None, prov="identity",
                        start=start, end=end,
                    )
                )
                continue

            items.append(
                LemmaItem(
                    surface=surface,
                    lemma=found[0],
                    pos=None,
                    prov="dict",
                    candidates=tuple(found) if len(found) > 1 else (),
                    start=start, end=end,
                )
            )
        return items


def build() -> LemmInflectBackend:
    return LemmInflectBackend()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/backends/test_lemminflect.py -v`
Expected: 7 passed

> If `test_lemmatizes_irregular_verb_with_pos` fails, print `getLemma('was', upos='VERB')` and inspect the tuple before changing anything. LemmInflect may return multiple forms.
>
> **Verified against lemminflect 0.2.3:** `getLemma('was', upos='VERB')` -> `('be',)`, `getAllLemmas('left')` -> `{'ADJ': ('left',), 'ADV': ('left',), 'NOUN': ('left',), 'VERB': ('leave',)}`.

- [ ] **Step 5: Commit**

```bash
git add api/backends/lemminflect_backend.py tests/backends/test_lemminflect.py
git commit -m "feat: add LemmInflect backend for en"
```

---

## Task 7: pymorphy3 backend (ru)

**Files:**
- Create: `api/backends/pymorphy_backend.py`
- Test: `tests/backends/test_pymorphy.py`

The survey's finding for Russian is that dictionary lookup loses to a real morphological analyser: pymorphy3 has an inflection engine and predicts paradigms for out-of-vocabulary words. So `ru` does **not** use simplemma here even though simplemma covers it.

- [ ] **Step 1: Write the failing test**

```python
# tests/backends/test_pymorphy.py
from api.backends import pymorphy_backend


def test_capabilities():
    backend = pymorphy_backend.build()
    assert backend.lang == "ru"
    assert backend.name == "pymorphy3"
    assert backend.pos_scheme == "pymorphy"
    assert backend.capabilities.pos is True
    assert backend.capabilities.tokenizes is False


def test_lemmatizes_past_tense_verb():
    backend = pymorphy_backend.build()
    items = backend.lemmatize(tokens=["шёл"], text=None, pos=None, options={})
    assert items[0].lemma == "идти"
    assert items[0].pos is not None


def test_lemmatizes_genitive_noun():
    backend = pymorphy_backend.build()
    items = backend.lemmatize(tokens=["Украины"], text=None, pos=None, options={})
    assert items[0].lemma == "украина"


def test_tokenizes_text_when_tokens_absent():
    backend = pymorphy_backend.build()
    items = backend.lemmatize(text="Он шёл домой.", tokens=None, pos=None, options={})
    assert any(i.lemma == "идти" for i in items)


def test_uppercase_word_is_lowercased_like_pymorphy_normal_form():
    backend = pymorphy_backend.build()
    items = backend.lemmatize(tokens=["Москве"], text=None, pos=None, options={})
    assert items[0].lemma == "москва"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backends/test_pymorphy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.backends.pymorphy_backend'`

- [ ] **Step 3: Write `api/backends/pymorphy_backend.py`**

```python
"""Morphological-analyser backend for Russian.

pymorphy3 returns scored parses; the highest-scoring parse's normal_form is the
lemma. We also surface its POS so clients get more than a bare string.
"""

from __future__ import annotations

import importlib.metadata as md
from typing import Any

import pymorphy3

from api.backends.base import BaseBackend
from api.textutil import fallback_tokenize, tokenize_with_offsets
from api.types import Capabilities, LemmaItem


class PymorphyBackend(BaseBackend):
    lang = "ru"
    name = "pymorphy3"
    pos_scheme = "pymorphy"
    capabilities = Capabilities(pos=True, pos_required=False, tokenizes=False)

    def __init__(self) -> None:
        self._morph = pymorphy3.MorphAnalyzer()
        self.version = md.version("pymorphy3")

    def lemmatize(
        self,
        text: str | None,
        tokens: list[str] | None,
        pos: list[str | None] | None,
        options: dict[str, Any],
    ) -> list[LemmaItem]:
        if tokens is not None:
            spans: list[tuple[str, int | None, int | None]] = [
                (t, None, None) for t in tokens
            ]
        else:
            spans = list(tokenize_with_offsets(text or ""))

        items: list[LemmaItem] = []
        for surface, start, end in spans:
            parses = self._morph.parse(surface)
            if not parses:
                items.append(
                    LemmaItem(
                        surface=surface, lemma=surface, pos=None, prov="identity",
                        start=start, end=end,
                    )
                )
                continue

            best = parses[0]
            lemma = best.normal_form
            tag = getattr(best.tag, "POS", None)
            prov = "dict" if lemma.lower() != surface.lower() else "identity"
            items.append(
                LemmaItem(
                    surface=surface, lemma=lemma, pos=tag, prov=prov,
                    start=start, end=end,
                )
            )
        return items


def build() -> PymorphyBackend:
    return PymorphyBackend()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/backends/test_pymorphy.py -v`
Expected: 5 passed

> pymorphy normalises case and ё→е. If `test_uppercase_word_is_lowercased_like_pymorphy_normal_form` fails, print `morph.parse('Москве')[0].normal_form` and assert the observed value — it is the library's documented behaviour, not a bug in our adapter.

- [ ] **Step 5: Commit**

```bash
git add api/backends/pymorphy_backend.py tests/backends/test_pymorphy.py
git commit -m "feat: add pymorphy3 backend for ru"
```

---

## Task 8: SudachiPy backend (ja)

**Files:**
- Create: `api/backends/sudachi_backend.py`
- Test: `tests/backends/test_sudachi.py`

Japanese has no standalone lemma task: the dictionary form is a property of each morpheme after morphological analysis. This backend therefore declares `tokenizes=True` and ignores caller-supplied tokens.

- [ ] **Step 1: Write the failing test**

```python
# tests/backends/test_sudachi.py
import pytest

from api.backends import sudachi_backend

pytestmark = pytest.mark.slow


def test_capabilities():
    backend = sudachi_backend.build()
    assert backend.lang == "ja"
    assert backend.name == "sudachipy"
    assert backend.pos_scheme == "sudachi"
    assert backend.capabilities.pos is True
    assert backend.capabilities.reading is True
    assert backend.capabilities.tokenizes is True


def test_dictionary_form_of_inflected_verb():
    backend = sudachi_backend.build()
    items = backend.lemmatize(text="食べました", tokens=None, pos=None, options={})
    lemmas = {i.surface: i.lemma for i in items}
    assert lemmas["食べ"] == "食べる"


def test_outputs_reading():
    backend = sudachi_backend.build()
    items = backend.lemmatize(text="食べました", tokens=None, pos=None, options={})
    tabe = next(i for i in items if i.surface == "食べ")
    assert tabe.reading == "タベ"


def test_outputs_pos():
    backend = sudachi_backend.build()
    items = backend.lemmatize(text="食べました", tokens=None, pos=None, options={})
    tabe = next(i for i in items if i.surface == "食べ")
    assert tabe.pos is not None
    assert "動詞" in tabe.pos


def test_ignores_callers_tokens_because_it_retokenizes():
    backend = sudachi_backend.build()
    items = backend.lemmatize(text="東京都", tokens=["WRONG"], pos=None, options={})
    assert all(i.surface != "WRONG" for i in items)


def test_split_mode_option_changes_segmentation():
    backend = sudachi_backend.build()
    merged = backend.lemmatize(
        text="国家公務員", tokens=None, pos=None, options={"split_mode": "C"}
    )
    split = backend.lemmatize(
        text="国家公務員", tokens=None, pos=None, options={"split_mode": "A"}
    )
    assert len(split) > len(merged)


def test_option_specs_exposes_split_mode():
    specs = sudachi_backend.build().option_specs()
    assert specs["split_mode"]["values"] == ["A", "B", "C"]
    assert specs["split_mode"]["default"] == "C"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backends/test_sudachi.py -v -m slow`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.backends.sudachi_backend'`

- [ ] **Step 3: Write `api/backends/sudachi_backend.py`**

```python
"""Morpheme-analyser backend for Japanese.

dictionary_form() is the lemma; normalized_form() is a different thing and must
not be substituted. reading_form() gives katakana, which we expose as `reading`.
"""

from __future__ import annotations

import importlib.metadata as md
from typing import Any

from sudachipy import dictionary, tokenizer

from api.backends.base import BaseBackend
from api.types import Capabilities, LemmaItem

SPLIT_MODES = {
    "A": tokenizer.Tokenizer.SplitMode.A,
    "B": tokenizer.Tokenizer.SplitMode.B,
    "C": tokenizer.Tokenizer.SplitMode.C,
}


class SudachiBackend(BaseBackend):
    lang = "ja"
    name = "sudachipy"
    pos_scheme = "sudachi"
    capabilities = Capabilities(
        pos=True, pos_required=False, reading=True, mwt=False, tokenizes=True
    )

    def __init__(self) -> None:
        self._tokenizer = dictionary.Dictionary(dict_type="core").create()
        self.version = md.version("sudachipy")
        try:
            self.dictionary_id = md.version("sudachidict_core")
        except md.PackageNotFoundError:
            self.dictionary_id = "unknown"

    def option_specs(self) -> dict[str, dict]:
        return {"split_mode": {"type": "enum", "values": ["A", "B", "C"], "default": "C"}}

    def lemmatize(
        self,
        text: str | None,
        tokens: list[str] | None,
        pos: list[str | None] | None,
        options: dict[str, Any],
    ) -> list[LemmaItem]:
        mode_key = str(options.get("split_mode", "C"))
        mode = SPLIT_MODES.get(mode_key.upper())
        if mode is None:
            raise ValueError(f"invalid split_mode: {mode_key!r}")

        source = text if text is not None else "".join(tokens or [])
        morphemes = self._tokenizer.tokenize(source, mode)

        items: list[LemmaItem] = []
        for m in morphemes:
            surface = m.surface()
            lemma = m.dictionary_form()
            pos = ",".join(m.part_of_speech()) if m.part_of_speech() else None
            reading = m.reading_form() or None
            prov = "dict" if lemma != surface else "identity"
            items.append(
                LemmaItem(
                    surface=surface, lemma=lemma, pos=pos, prov=prov, reading=reading,
                    start=m.begin(), end=m.end(),
                )
            )
        return items


def build() -> SudachiBackend:
    return SudachiBackend()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/backends/test_sudachi.py -v -m slow`
Expected: 7 passed. First run loads a ~70 MB dictionary, so allow ~30 s.

> **Verified against sudachipy 0.7.0 / sudachidict-core 20261015:** `食べました` -> `食べ`/`食べる`, `まし`/`ます`, `た`/`た`, each with a comma-joined 6-field POS and katakana reading. Note `た` comes back `prov="identity"` because its dictionary form equals its surface — that is correct, not a bug.
>
> sudachipy 0.7 warns that `Dictionary.create()` is deprecated in favour of `Dictionary.tokenizer()`. Keep `.create()`: `pyproject.toml` allows `sudachipy>=0.6.10`, and `.tokenizer()` does not exist in 0.6.

- [ ] **Step 5: Commit**

```bash
git add api/backends/sudachi_backend.py tests/backends/test_sudachi.py
git commit -m "feat: add SudachiPy backend for ja"
```

---

## Task 9: Kiwi backend (ko)

**Files:**
- Create: `api/backends/kiwi_backend.py`
- Test: `tests/backends/test_kiwi.py`

Korean has the same shape as Japanese: tokenize first, then derive the dictionary form. Kiwi exposes no direct `lemma()` API, so the dictionary form of a predicate is reconstructed with `kiwi.join()`. The Kiwi README demonstrates exactly this pattern for stripping the past-tense ending (`먹었다` → `먹다`).

- [ ] **Step 1: Write the failing test**

```python
# tests/backends/test_kiwi.py
import pytest

from api.backends import kiwi_backend

pytestmark = pytest.mark.slow


def test_capabilities():
    backend = kiwi_backend.build()
    assert backend.lang == "ko"
    assert backend.name == "kiwipiepy"
    assert backend.pos_scheme == "sejong-kiwi"
    assert backend.capabilities.pos is True
    assert backend.capabilities.tokenizes is True


def test_noun_lemma_equals_surface():
    backend = kiwi_backend.build()
    items = backend.lemmatize(text="학교에 갔습니다", tokens=None, pos=None, options={})
    hakgyo = next(i for i in items if i.surface == "학교")
    assert hakgyo.lemma == "학교"
    assert hakgyo.pos == "NNG"


def test_predicate_stem_gets_dictionary_form():
    backend = kiwi_backend.build()
    items = backend.lemmatize(text="먹었습니다", tokens=None, pos=None, options={})
    stem = next(i for i in items if i.pos == "VV")
    assert stem.surface == "먹"
    assert stem.lemma == "먹다"


def test_ignores_callers_tokens_because_it_retokenizes():
    backend = kiwi_backend.build()
    items = backend.lemmatize(text="학교", tokens=["WRONG"], pos=None, options={})
    assert all(i.surface != "WRONG" for i in items)


def test_carries_pos_tags_from_sejong_tagset():
    backend = kiwi_backend.build()
    items = backend.lemmatize(text="먹었습니다", tokens=None, pos=None, options={})
    tags = {i.pos for i in items}
    assert "VV" in tags
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backends/test_kiwi.py -v -m slow`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.backends.kiwi_backend'`

- [ ] **Step 3: Write `api/backends/kiwi_backend.py`**

```python
"""Morpheme-analyser backend for Korean.

Kiwi has no lemma() API. A predicate stem's dictionary form is reconstructed by
joining the stem with the plain ending 다/하다, which is the same technique the
Kiwi README uses when it strips the past-tense ending to recover 먹다.
"""

from __future__ import annotations

import importlib.metadata as md
from typing import Any

from kiwipiepy import Kiwi

from api.backends.base import BaseBackend
from api.types import Capabilities, LemmaItem

# Sejong-derived tags whose dictionary form is "<stem>다".
PREDICATE_TAGS = frozenset({"VV", "VA", "VX", "XSV", "XSA"})


class KiwiBackend(BaseBackend):
    lang = "ko"
    name = "kiwipiepy"
    pos_scheme = "sejong-kiwi"
    capabilities = Capabilities(pos=True, pos_required=False, tokenizes=True)

    def __init__(self) -> None:
        self._kiwi = Kiwi()
        self.version = md.version("kiwipiepy")

    def option_specs(self) -> dict[str, dict]:
        return {}

    def _dictionary_form(self, form: str, tag: str) -> str:
        if tag not in PREDICATE_TAGS:
            return form
        try:
            return self._kiwi.join([(form, tag), ("다", "EF")])
        except Exception:  # noqa: BLE001 - a bad tag must not fail the request
            return form

    def lemmatize(
        self,
        text: str | None,
        tokens: list[str] | None,
        pos: list[str | None] | None,
        options: dict[str, Any],
    ) -> list[LemmaItem]:
        source = text if text is not None else " ".join(tokens or [])
        parsed = self._kiwi.tokenize(source)

        items: list[LemmaItem] = []
        for token in parsed:
            form = token.form
            tag = token.tag
            lemma = self._dictionary_form(form, tag)
            prov = "dict" if lemma != form else "identity"
            items.append(
                LemmaItem(
                    surface=form, lemma=lemma, pos=tag, prov=prov,
                    start=token.start, end=token.start + token.len,
                )
            )
        return items


def build() -> KiwiBackend:
    return KiwiBackend()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/backends/test_kiwi.py -v -m slow`
Expected: 5 passed. First run loads the CoNg model (~59 MB).

> **Verified against kiwipiepy 0.24.1:** `먹었습니다` -> stem `먹` tagged `VV`, and `kiwi.join([('먹','VV'),('다','EF')])` returns `먹다`. The `join()` reconstruction works, so no tagset patching was needed for this build.

> If `test_predicate_stem_gets_dictionary_form` fails, check what `kiwi.join([('먹','VV'),('다','EF')])` returns on this build before adjusting. `VV-R`/`VV-I` irregular suffixes exist in the tagset; if the observed tag is `VV-I`, add it to `PREDICATE_TAGS` rather than loosening the assertion.

- [ ] **Step 5: Commit**

```bash
git add api/backends/kiwi_backend.py tests/backends/test_kiwi.py
git commit -m "feat: add Kiwi backend for ko"
```

---

## Task 10: Request schema

**Files:**
- Create: `api/schemas.py`
- Test: `tests/test_schemas.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_schemas.py
import pytest
from pydantic import ValidationError

from api.schemas import LemmatizeRequest, normalize_pos


def test_accepts_text_only():
    req = LemmatizeRequest(lang="de", text="Häuser")
    assert req.tokens is None


def test_accepts_tokens_only():
    req = LemmatizeRequest(lang="de", tokens=["Häuser"])
    assert req.text is None


def test_rejects_both_text_and_tokens():
    with pytest.raises(ValidationError, match="exactly one"):
        LemmatizeRequest(lang="de", text="x", tokens=["x"])


def test_rejects_neither_text_nor_tokens():
    with pytest.raises(ValidationError, match="exactly one"):
        LemmatizeRequest(lang="de")


def test_normalize_pos_string_becomes_single_element_list():
    assert normalize_pos("VERB", 1) == ["VERB"]


def test_normalize_pos_none_stays_none():
    assert normalize_pos(None, 3) is None


def test_normalize_pos_list_passes_through():
    assert normalize_pos(["VERB", "NOUN"], 2) == ["VERB", "NOUN"]


def test_normalize_pos_list_length_mismatch_raises():
    with pytest.raises(ValueError, match="length"):
        normalize_pos(["VERB"], 2)


def test_normalize_pos_scalar_with_text_input_is_accepted():
    """token_count is None when the caller sent `text`; no length check applies."""
    assert normalize_pos("VERB", None) == ["VERB"]


def test_normalize_pos_list_with_unknown_token_count_raises():
    """A per-token list cannot be matched against a whole-text input."""
    with pytest.raises(ValueError, match="tokens"):
        normalize_pos(["VERB"], None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.schemas'`

- [ ] **Step 3: Write `api/schemas.py`**

```python
"""Request validation for /v1/lemmatize (spec section 4.1)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class LemmatizeRequest(BaseModel):
    lang: str = Field(min_length=2, max_length=8)
    text: str | None = None
    tokens: list[str] | None = None
    pos: list[str | None] | str | None = None
    options: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _exactly_one_input(self) -> LemmatizeRequest:
        if (self.text is None) == (self.tokens is None):
            raise ValueError("exactly one of 'text' or 'tokens' is required")
        return self


def normalize_pos(
    pos: list[str | None] | str | None, token_count: int | None
) -> list[str | None] | None:
    """Widen a scalar POS to a per-token list, enforcing length agreement.

    `token_count` is None when the caller sent `text` instead of `tokens`: the
    backend may retokenize, so there is nothing to agree against. A scalar is
    then still meaningful ("the whole input is one POS"), but a per-token list
    is not.
    """
    if pos is None:
        return None
    if isinstance(pos, str):
        if token_count == 0:
            raise ValueError("scalar 'pos' requires at least one token")
        return [pos]
    if token_count is None:
        raise ValueError("list 'pos' requires 'tokens'; it cannot be matched against 'text'")
    if len(pos) != token_count:
        raise ValueError(
            f"'pos' length {len(pos)} does not match token count {token_count}"
        )
    return pos
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_schemas.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add api/schemas.py tests/test_schemas.py
git commit -m "feat: add LemmatizeRequest schema with pos normalization"
```

---

## Task 11: App assembly, health and languages routes

**Files:**
- Create: `api/routes/__init__.py`
- Create: `api/routes/health.py`
- Create: `api/routes/languages.py`
- Create: `api/main.py`
- Test: `tests/conftest.py`
- Test: `tests/test_api_health.py`
- Test: `tests/test_api_languages.py`

- [ ] **Step 1: Write the failing test**

`tests/conftest.py`:
```python
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import build_registry, create_app


@pytest.fixture
def fake_client():
    """Client with fake backends only - no heavy dictionaries loaded."""
    app = create_app(registry=build_registry(use_fakes=True))
    return TestClient(app)


@pytest.fixture(scope="session")
def real_client():
    """Client with the real 7-language registry. Session-scoped: dictionaries load once."""
    app = create_app()
    with TestClient(app) as client:
        return client
```

`tests/test_api_health.py`:
```python
def test_health_is_reachable_without_auth(fake_client):
    resp = fake_client.get("/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "backends" in body


def test_health_lists_every_registered_language(fake_client):
    body = fake_client.get("/v1/health").json()
    assert set(body["backends"]) == {"en", "de", "fr", "es", "ru", "ja", "ko"}
```

`tests/test_api_languages.py`:
```python
def test_languages_returns_all_seven(real_client):
    body = real_client.get("/v1/languages").json()
    langs = {entry["lang"] for entry in body["languages"]}
    assert langs == {"en", "de", "fr", "es", "ru", "ja", "ko"}


def test_each_entry_has_full_capability_matrix(real_client):
    body = real_client.get("/v1/languages").json()
    for entry in body["languages"]:
        caps = entry["capabilities"]
        assert set(caps) == {
            "pos", "pos_accepted", "pos_required",
            "candidates", "reading", "mwt", "tokenizes",
        }
        assert "pos_scheme" in entry


def test_english_accepts_pos_but_emits_none(real_client):
    body = real_client.get("/v1/languages").json()
    en = next(e for e in body["languages"] if e["lang"] == "en")
    assert en["capabilities"]["pos"] is False
    assert en["capabilities"]["pos_accepted"] is True


def test_russian_emits_pos_but_does_not_accept_it(real_client):
    body = real_client.get("/v1/languages").json()
    ru = next(e for e in body["languages"] if e["lang"] == "ru")
    assert ru["capabilities"]["pos"] is True
    assert ru["capabilities"]["pos_accepted"] is False


def test_japanese_declares_tokenizes_true_and_reading_true(real_client):
    body = real_client.get("/v1/languages").json()
    ja = next(e for e in body["languages"] if e["lang"] == "ja")
    assert ja["capabilities"]["tokenizes"] is True
    assert ja["capabilities"]["reading"] is True
    assert ja["pos_scheme"] == "sudachi"


def test_german_declares_pos_false(real_client):
    body = real_client.get("/v1/languages").json()
    de = next(e for e in body["languages"] if e["lang"] == "de")
    assert de["capabilities"]["pos"] is False
    assert de["pos_scheme"] is None
    assert de["options"]["greedy"]["default"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_health.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.main'`

- [ ] **Step 3: Write the app assembly and both routes**

`api/routes/__init__.py`: empty file.

`api/routes/health.py`:
```python
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/v1/health")
def health(request: Request) -> dict:
    registry = request.app.state.registry
    entries = registry.all()
    return {
        "status": "ok" if any(e.status == "ok" for e in entries) else "degraded",
        "backends": {
            e.lang: {
                "status": e.status,
                "backend": e.backend.name if e.backend else None,
                "reason": e.reason,
            }
            for e in entries
        },
    }
```

`api/routes/languages.py`:
```python
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/v1/languages")
def languages(request: Request) -> dict:
    registry = request.app.state.registry
    out = []
    for entry in registry.all():
        backend = entry.backend
        out.append(
            {
                "lang": entry.lang,
                "status": entry.status,
                "backend": (
                    {"name": backend.name, "version": backend.version}
                    if backend
                    else None
                ),
                "reason": entry.reason,
                "pos_scheme": backend.pos_scheme if backend else None,
                "capabilities": (
                    backend.capabilities.to_json()
                    if backend
                    else {
                        "pos": False, "pos_accepted": False, "pos_required": False,
                        "candidates": False, "reading": False, "mwt": False,
                        "tokenizes": False,
                    }
                ),
                "options": backend.option_specs() if backend else {},
            }
        )
    return {"languages": out}
```

`api/main.py`:
```python
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.backends.registry import Registry, lazy
from api.errors import ApiError
from api.routes import health, languages, lemmatize

log = logging.getLogger(__name__)


class _FakeBackend:
    """Test double used when build_registry(use_fakes=True)."""

    pos_scheme = None

    def __init__(self, lang: str) -> None:
        from api.types import Capabilities

        self.lang = lang
        self.name = "fake"
        self.version = "0.0.0"
        self.capabilities = Capabilities()

    def option_specs(self) -> dict:
        return {}

    def lemmatize(self, text, tokens, pos, options):
        from api.types import LemmaItem

        # Mirrors the real backends' contract: offsets when we tokenized the
        # text ourselves, none when the caller supplied tokens.
        if tokens is not None:
            return [LemmaItem(surface=t, lemma=t.lower()) for t in tokens]

        items = []
        cursor = 0
        for surface in (text or "").split():
            start = (text or "").find(surface, cursor)
            end = start + len(surface)
            cursor = end
            items.append(
                LemmaItem(surface=surface, lemma=surface.lower(), start=start, end=end)
            )
        return items


def build_registry(use_fakes: bool = False) -> Registry:
    registry = Registry()
    if use_fakes:
        for lang in ("en", "de", "fr", "es", "ru", "ja", "ko"):
            registry.register(lang, lambda lang=lang: _FakeBackend(lang))
        return registry

    # Every backend is registered through `lazy` so a missing package degrades
    # one language instead of raising ImportError out of build_registry.
    registry.register("en", lazy("api.backends.lemminflect_backend"))
    for lang in ("de", "fr", "es"):
        registry.register(lang, lazy("api.backends.simplemma_backend", lang))
    registry.register("ru", lazy("api.backends.pymorphy_backend"))
    registry.register("ja", lazy("api.backends.sudachi_backend"))
    registry.register("ko", lazy("api.backends.kiwi_backend"))
    return registry


def create_app(registry: Registry | None = None) -> FastAPI:
    app = FastAPI(title="Lemma API", version="0.1.0")
    app.state.registry = registry if registry is not None else build_registry()

    @app.exception_handler(ApiError)
    async def _api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content=exc.to_json(getattr(request.state, "request_id", None)),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Pydantic failures default to HTTP 422 with a `detail` list.

        That envelope is not ours: spec section 4.4 requires error.code on every
        failure, so a client parsing error.code would break here. Collapse it
        into INVALID_REQUEST / 400 and keep the first field path for diagnosis.
        """
        errors = exc.errors()
        first = errors[0] if errors else {}
        message = str(first.get("msg", "request validation failed"))
        if message.startswith("Value error, "):
            message = message[len("Value error, "):]
        error = ApiError(
            "INVALID_REQUEST", 400, message, {"field": list(first.get("loc", []))}
        )
        return JSONResponse(
            status_code=400,
            content=error.to_json(getattr(request.state, "request_id", None)),
        )

    app.include_router(health.router)
    app.include_router(languages.router)
    app.include_router(lemmatize.router)
    return app


app = create_app()
```

> `lemmatize.router` does not exist until Task 12. Create a temporary placeholder now and replace it in Task 12:
> ```bash
> printf 'from fastapi import APIRouter\n\nrouter = APIRouter()\n' > api/routes/lemmatize.py
> ```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_api_health.py tests/test_api_languages.py -v`
Expected: 8 passed. `test_api_languages.py` loads all real dictionaries once — allow ~60 s.

- [ ] **Step 5: Commit**

```bash
git add api/routes/__init__.py api/routes/health.py api/routes/languages.py api/main.py tests/conftest.py tests/test_api_health.py tests/test_api_languages.py
git commit -m "feat: assemble FastAPI app with health and languages routes"
```

---

## Task 12: The lemmatize endpoint

**Files:**
- Modify: `api/routes/lemmatize.py` (replaces the placeholder)
- Test: `tests/test_api_lemmatize.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_lemmatize.py
def test_lemmatize_german_tokens(real_client):
    resp = real_client.post(
        "/v1/lemmatize", json={"lang": "de", "tokens": ["Häuser"]}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["lang"] == "de"
    assert body["segmented_by"] == "input"
    assert body["items"][0]["lemma"] == "Haus"


def test_response_carries_backend_identity_and_capabilities(real_client):
    body = real_client.post(
        "/v1/lemmatize", json={"lang": "de", "tokens": ["Häuser"]}
    ).json()
    assert body["backend"]["name"] == "simplemma"
    assert "version" in body["backend"]
    assert "capabilities" in body


def test_japanese_reports_segmented_by_backend(real_client):
    body = real_client.post(
        "/v1/lemmatize", json={"lang": "ja", "text": "食べました"}
    ).json()
    assert body["segmented_by"] == "backend"
    assert {i["surface"] for i in body["items"]} != {"食べました"}


def test_japanese_retokenizes_even_when_given_tokens(real_client):
    """`ja` re-segments, so `segmented_by` is "backend" on both input paths.

    Sending both `text` and `tokens` is rejected by the schema, so this exercises
    the tokens-only path: SudachiPy joins the tokens and analyses the result.
    """
    body = real_client.post(
        "/v1/lemmatize", json={"lang": "ja", "tokens": ["食べました"]}
    ).json()
    assert body["segmented_by"] == "backend"
    surfaces = [i["surface"] for i in body["items"]]
    assert surfaces != ["食べました"], "output must not echo the caller's token 1:1"
    assert any(i["lemma"] == "食べる" for i in body["items"])


def test_request_id_is_present_and_unique(real_client):
    a = real_client.post("/v1/lemmatize", json={"lang": "de", "tokens": ["x"]}).json()
    b = real_client.post("/v1/lemmatize", json={"lang": "de", "tokens": ["x"]}).json()
    assert a["request_id"].startswith("req_")
    assert a["request_id"] != b["request_id"]


def test_elapsed_ms_is_reported(real_client):
    body = real_client.post(
        "/v1/lemmatize", json={"lang": "de", "tokens": ["Häuser"]}
    ).json()
    assert isinstance(body["elapsed_ms"], (int, float))
    assert body["elapsed_ms"] >= 0


def test_greedy_option_is_accepted(real_client):
    resp = real_client.post(
        "/v1/lemmatize",
        json={"lang": "de", "tokens": ["ausgezeichneten"], "options": {"greedy": False}},
    )
    assert resp.status_code == 200
    assert resp.json()["items"][0]["lemma"] == "ausgezeichnet"


def test_unknown_option_is_rejected(real_client):
    resp = real_client.post(
        "/v1/lemmatize",
        json={"lang": "de", "tokens": ["x"], "options": {"nonsense": 1}},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "UNKNOWN_OPTION"


def test_unknown_language_is_rejected(real_client):
    resp = real_client.post("/v1/lemmatize", json={"lang": "zz", "tokens": ["x"]})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "UNKNOWN_LANGUAGE"


def test_both_text_and_tokens_is_400_with_our_envelope(real_client):
    """Pydantic's default 422/detail envelope must not leak out."""
    resp = real_client.post("/v1/lemmatize", json={"lang": "de", "text": "a", "tokens": ["a"]})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_REQUEST"
    assert "detail" not in body


def test_missing_input_is_400_with_our_envelope(real_client):
    resp = real_client.post("/v1/lemmatize", json={"lang": "de"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_REQUEST"


def test_list_pos_with_text_input_is_rejected(real_client):
    resp = real_client.post(
        "/v1/lemmatize", json={"lang": "de", "text": "Haus", "pos": ["NOUN"]}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_REQUEST"


def test_unavailable_backend_returns_503():
    from fastapi.testclient import TestClient

    from api.main import build_registry, create_app

    registry = build_registry(use_fakes=True)

    def _boom():
        raise RuntimeError("dict missing")

    registry.register("de", _boom)
    client = TestClient(create_app(registry=registry))
    resp = client.post("/v1/lemmatize", json={"lang": "de", "tokens": ["x"]})
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "LANGUAGE_UNAVAILABLE"
    assert "dict missing" in resp.json()["error"]["details"]["reason"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_lemmatize.py -v`
Expected: FAIL — placeholder router has no `POST /v1/lemmatize`, so responses are 405/404.

- [ ] **Step 3: Replace `api/routes/lemmatize.py`**

```python
"""The single lemmatize endpoint (spec section 4.1)."""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Request

from api.errors import ApiError
from api.schemas import LemmatizeRequest, normalize_pos

router = APIRouter()


@router.post("/v1/lemmatize")
def lemmatize(payload: LemmatizeRequest, request: Request) -> dict:
    request_id = f"req_{uuid.uuid4().hex[:20]}"
    request.state.request_id = request_id

    registry = request.app.state.registry
    entry = registry.get(payload.lang)
    if entry is None:
        raise ApiError(
            "UNKNOWN_LANGUAGE",
            400,
            f"unsupported language {payload.lang!r}",
            {"supported": [e.lang for e in registry.all()]},
        )
    if entry.status != "ok" or entry.backend is None:
        raise ApiError(
            "LANGUAGE_UNAVAILABLE",
            503,
            f"backend for {payload.lang!r} failed to initialize",
            {"reason": entry.reason},
        )

    backend = entry.backend

    unknown = set(payload.options) - set(backend.option_specs())
    if unknown:
        raise ApiError(
            "UNKNOWN_OPTION",
            400,
            "unknown option(s) for this language",
            {"unknown": sorted(unknown), "allowed": sorted(backend.option_specs())},
        )

    token_count = len(payload.tokens) if payload.tokens is not None else None
    try:
        pos_list = normalize_pos(payload.pos, token_count)
    except ValueError as exc:
        raise ApiError("INVALID_REQUEST", 400, str(exc)) from exc

    if backend.capabilities.pos_required and pos_list is None:
        raise ApiError(
            "INVALID_REQUEST",
            400,
            f"language {payload.lang!r} requires 'pos'",
        )

    started = time.perf_counter()
    try:
        items = backend.lemmatize(
            text=payload.text,
            tokens=payload.tokens,
            pos=pos_list,
            options=payload.options,
        )
    except ValueError as exc:
        raise ApiError("INVALID_REQUEST", 400, str(exc)) from exc
    elapsed_ms = (time.perf_counter() - started) * 1000

    if payload.tokens is not None and not backend.capabilities.tokenizes:
        segmented_by = "input"
    else:
        segmented_by = "backend"

    warnings = [
        {"code": "UNRESOLVED", "surface": item.surface}
        for item in items
        if item.prov == "identity"
    ]

    has_offsets = any(i.start is not None for i in items)

    return {
        "request_id": request_id,
        "offset_unit": "unicode_code_point" if has_offsets else None,
        "lang": payload.lang,
        "backend": {"name": backend.name, "version": backend.version},
        "segmented_by": segmented_by,
        "capabilities": backend.capabilities.to_json(),
        "items": [item.to_json() for item in items],
        "warnings": warnings,
        "elapsed_ms": round(elapsed_ms, 2),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_api_lemmatize.py -v`
Expected: 13 passed
- [ ] **Step 5: Commit**

```bash
git add api/routes/lemmatize.py tests/test_api_lemmatize.py
git commit -m "feat: add POST /v1/lemmatize with capability-aware responses"
```

---

## Task 12b: Character offsets

**Files:**
- Test: `tests/test_offsets.py`

Offsets were already threaded through `LemmaItem`, the tokenizer and all five
adapters in the tasks above, so this task only pins the contract.

**Why `offset_unit` exists:** Python and both the Japanese and Korean analysers
count **code points**. JavaScript indexes **UTF-16 code units**. They agree for
every BMP character and diverge the moment the text contains an emoji, a rare
CJK ideograph above U+FFFF, or a mathematical alphanumeric. A console that fed
these offsets straight into `String.prototype.slice` would mis-highlight
silently rather than throw, so the unit is stated in the response and the
console converts (Plan 3 adds and tests that helper).

- [ ] **Step 1: Write the tests**

```python
# tests/test_offsets.py
"""Character offsets (spec open item 2).

`start`/`end` are CODE POINT offsets into the request's `text`. They are omitted
when the caller supplied `tokens`, because there is no source string to point
into. `offset_unit` at the top level says which unit is in use.
"""
import pytest


def _body(client, payload):
    return client.post("/v1/lemmatize", json=payload).json()


def test_offsets_present_when_text_is_tokenized(real_client):
    body = _body(real_client, {"lang": "de", "text": "Hier sind Häuser."})
    assert body["offset_unit"] == "unicode_code_point"
    for item in body["items"]:
        assert "start" in item and "end" in item


def test_offsets_slice_back_to_the_surface(real_client):
    text = "Hier sind Häuser."
    body = _body(real_client, {"lang": "de", "text": text})
    for item in body["items"]:
        assert text[item["start"]:item["end"]] == item["surface"]


def test_offsets_absent_for_token_input(real_client):
    body = _body(real_client, {"lang": "de", "tokens": ["Häuser"]})
    assert body["offset_unit"] is None
    assert "start" not in body["items"][0]


@pytest.mark.parametrize("lang,text", [
    ("ru", "Он шёл домой."),
    ("ja", "東京都へ行きました"),
    ("ko", "먹었습니다"),
])
def test_offsets_are_ordered_and_within_bounds(real_client, lang, text):
    body = _body(real_client, {"lang": lang, "text": text})
    assert body["offset_unit"] == "unicode_code_point"
    previous_end = 0
    for item in body["items"]:
        assert 0 <= item["start"] <= item["end"] <= len(text)
        assert item["start"] >= previous_end or item["start"] == item["end"] - 1
        previous_end = item["end"]


def test_japanese_offsets_slice_exactly(real_client):
    text = "東京都へ行きました"
    body = _body(real_client, {"lang": "ja", "text": text})
    for item in body["items"]:
        assert text[item["start"]:item["end"]] == item["surface"]


def test_korean_offsets_are_spans_not_surfaces(real_client):
    """A contracted form is decomposed, so several morphemes share one span.

    갔 is analysed as 가 + 었, both spanning the single character. Offsets still
    point at the right place in the original text; `surface` is the morpheme,
    not the substring. Consumers must not assume text[start:end] == surface.
    """
    text = "갔다"
    body = _body(real_client, {"lang": "ko", "text": text})
    verb = [i for i in body["items"] if i["pos"] == "VV"]
    assert verb, "expected a verb stem"
    assert (verb[0]["start"], verb[0]["end"]) == (0, 1)
    assert text[0:1] == "갔"
    assert verb[0]["surface"] != text[0:1]


def test_offsets_survive_non_bmp_text(real_client):
    """Code-point offsets must not be confused with UTF-16 indices."""
    text = "𝕏東京"
    body = _body(real_client, {"lang": "ja", "text": text})
    tokyo = next(i for i in body["items"] if i["surface"] == "東京")
    assert (tokyo["start"], tokyo["end"]) == (1, 3)
    assert text[1:3] == "東京"
```

- [ ] **Step 2: Run the tests**

Run: `uv run pytest tests/test_offsets.py -v`
Expected: 9 passed

> **Verified against the real analysers before this plan was published:**
> SudachiPy returns `begin()`/`end()` that slice exactly (`東京都` -> `(0,3)`).
> Kiwi returns `start`/`len` that are valid text spans but **do not** slice back
> to `form` for contracted verbs, because 갔 decomposes into 가+었 sharing
> `[0:1]`. `test_korean_offsets_are_spans_not_surfaces` encodes that; do not
> "fix" it by asserting equality.

- [ ] **Step 3: Update the response contract test in Task 12**

The existing `test_response_carries_backend_identity_and_capabilities` should also
confirm the new top-level key is present:

```python
def test_response_states_the_offset_unit(real_client):
    body = real_client.post(
        "/v1/lemmatize", json={"lang": "de", "text": "Häuser"}
    ).json()
    assert body["offset_unit"] == "unicode_code_point"


def test_response_offset_unit_is_null_for_tokens(real_client):
    body = real_client.post(
        "/v1/lemmatize", json={"lang": "de", "tokens": ["Häuser"]}
    ).json()
    assert body["offset_unit"] is None
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_offsets.py tests/test_api_lemmatize.py
git commit -m "test: pin character-offset contract and offset_unit for all 7 languages"
```

---

## Task 13: POS nullability contract

**Files:**
- Test: `tests/test_api_pos_semantics.py`

This task is tests-only. It pins the contract that decision 3 made: `pos` is **always present as a key**, and is `null` for languages that cannot produce it. Without this, a later refactor could silently drop the key and break clients.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_pos_semantics.py
import pytest


def _items(client, payload):
    return client.post("/v1/lemmatize", json=payload).json()["items"]


def test_pos_key_always_present_even_when_null(real_client):
    items = _items(real_client, {"lang": "de", "tokens": ["Häuser"]})
    assert all("pos" in i for i in items)
    assert items[0]["pos"] is None


@pytest.mark.parametrize("lang,tokens", [
    ("de", ["Häuser"]),
    ("fr", ["mangées"]),
    ("es", ["corriendo"]),
])
def test_lookup_languages_report_null_pos(real_client, lang, tokens):
    items = _items(real_client, {"lang": lang, "tokens": tokens})
    assert items[0]["pos"] is None


@pytest.mark.parametrize("lang,text", [
    ("ru", "шёл"),
    ("ja", "食べました"),
    ("ko", "먹었습니다"),
])
def test_analyser_languages_report_non_null_pos(real_client, lang, text):
    items = _items(real_client, {"lang": lang, "text": text})
    assert any(i["pos"] is not None for i in items)


def test_prov_is_always_present(real_client):
    items = _items(real_client, {"lang": "de", "tokens": ["Häuser"]})
    assert all(i["prov"] in {"dict", "rule", "model", "identity", "candidates"} for i in items)


def test_identity_items_appear_in_warnings(real_client):
    body = real_client.post(
        "/v1/lemmatize", json={"lang": "de", "tokens": ["Xylophonwort"]}
    ).json()
    assert any(w["surface"] == "Xylophonwort" for w in body["warnings"])
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_api_pos_semantics.py -v`
Expected: 8 passed

> These should pass already from Task 12's implementation. If any fails, the contract is broken — fix the route, not the test.

- [ ] **Step 3: Commit**

```bash
git add tests/test_api_pos_semantics.py
git commit -m "test: pin pos nullability contract across all 7 languages"
```

---

## Task 14: Golden cross-language suite

**Files:**
- Test: `tests/test_golden.py`

The seven cases from the spec, asserting the behaviour that actually distinguishes the two backend families.

- [ ] **Step 1: Write the test**

```python
# tests/test_golden.py
"""Cross-language golden cases from the design spec section 10."""

import pytest

CASES = [
    # lang, payload, expected lemma, expected pos-ness
    ("en", {"tokens": ["was"], "pos": ["VERB"]}, "be", "present-or-null"),
    ("de", {"tokens": ["Häuser"]}, "Haus", "null"),
    ("fr", {"tokens": ["mangées"]}, "manger", "null"),
    ("es", {"tokens": ["corriendo"]}, "correr", "null"),
    ("ru", {"text": "шёл"}, "идти", "present"),
    ("ja", {"text": "食べました"}, "食べる", "present"),
    ("ko", {"text": "먹었습니다"}, "먹다", "present"),
]


@pytest.mark.parametrize("lang,payload,expected_lemma,_posness", CASES)
def test_golden_lemma(real_client, lang, payload, expected_lemma, _posness):
    body = real_client.post("/v1/lemmatize", json={"lang": lang, **payload}).json()
    lemmas = [i["lemma"] for i in body["items"]]
    assert expected_lemma in lemmas, f"{lang}: {expected_lemma} not in {lemmas}"


@pytest.mark.parametrize("lang,payload,_lemma,posness", CASES)
def test_golden_pos_contract(real_client, lang, payload, _lemma, posness):
    body = real_client.post("/v1/lemmatize", json={"lang": lang, **payload}).json()
    items = body["items"]
    assert all("pos" in i for i in items)
    if posness == "null":
        assert all(i["pos"] is None for i in items)
    elif posness == "present":
        assert any(i["pos"] is not None for i in items)


def test_all_seven_languages_are_healthy(real_client):
    body = real_client.get("/v1/health").json()
    unavailable = {
        lang: info for lang, info in body["backends"].items()
        if info["status"] != "ok"
    }
    assert unavailable == {}, f"unavailable backends: {unavailable}"
```

- [ ] **Step 2: Run the full suite**

Run: `uv run pytest -v`
Expected: all tests pass; `ja`/`ko` cases are the slowest on first run.

- [ ] **Step 3: Run the lint gate**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: no errors. If formatting differs, run `uv run ruff format .` and re-run.

- [ ] **Step 4: Verify the app actually serves**

Run:
```bash
uv run uvicorn api.main:app --port 8000 &
sleep 12
curl -s localhost:8000/v1/health | head -c 400; echo
curl -s -X POST localhost:8000/v1/lemmatize \
  -H 'content-type: application/json' \
  -d '{"lang":"ja","text":"食べました"}' | head -c 600; echo
kill %1
```
Expected: health shows all seven `"status":"ok"`; the lemmatize response contains `"lemma": "食べる"` and `"segmented_by": "backend"`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_golden.py
git commit -m "test: add golden cross-language suite for all 7 languages"
```

---

## Task 15: Document the M1+M2 boundary

**Files:**
- Create: `api/README.md`

- [ ] **Step 1: Write `api/README.md`**

```markdown
# lemma-api (M1+M2)

Multilingual lemmatization HTTP API. **No authentication yet** — see
`docs/superpowers/plans/` for the auth plan.

## Run

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"
uv run uvicorn api.main:app --reload --port 8000
```

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/v1/health` | per-backend readiness |
| GET | `/v1/languages` | capability matrix + per-language options |
| POST | `/v1/lemmatize` | the only compute endpoint |

## Language backends

| lang | backend | pos | tokenizes |
|---|---|---|---|
| en | lemminflect | yes | no |
| de | simplemma (greedy=true) | no | no |
| fr | simplemma (greedy=false) | no | no |
| es | simplemma (greedy=false) | no | no |
| ru | pymorphy3 | yes | no |
| ja | sudachipy (dict=core) | yes | **yes** |
| ko | kiwipiepy | yes | **yes** |

`segmented_by` in the response tells you whether your tokens were honoured
(`"input"`) or the backend re-segmented the text (`"backend"`).

## Test

```bash
uv run pytest -m "not slow"   # fast: skips ja/ko dictionary loads
uv run pytest                 # full
```
```

- [ ] **Step 2: Commit**

```bash
git add api/README.md
git commit -m "docs: document M1+M2 API surface and backend matrix"
```

---

## Self-review

**Spec coverage for M1+M2:**

| Spec section | Covered by |
|---|---|
| §3.1 `Backend` protocol + `Capabilities` | Task 3, Task 1 |
| §3.2 all seven backend adapters | Tasks 5–9 |
| §3.3 startup degradation | Task 4, tested in Task 12 |
| §4.1 `/v1/lemmatize` + `segmented_by` | Task 12 |
| §4.2 `/v1/languages` + `pos_scheme` | Task 11 |
| §4.3 `/v1/health` | Task 11 |
| §4.4 error envelope | Task 2, wired in Task 11, exercised in Task 12 |
| §10 golden cases | Task 14 |
| §13 open item 1 (pos passthrough + `pos_scheme`) | Task 6, 7, 8, 9, 11 |

**Deliberately absent** (belongs to later plans): auth, rate limiting, SQLite, settings, audit, console, Docker.

**Deferred with a note:** §13 open item 2 asked for character offsets `start`/`end` in M1. This plan does **not** implement them. Adding them is additive (a new key per item), not a breaking change, so it does not need to be in M1, but it should land before the console renders highlight-on-hover.

**Type consistency check:** `LemmaItem.to_json()` → `to_json()` on `Capabilities` → both used by Task 11/12. `option_specs()` defined in `BaseBackend` (Task 3), implemented by simplemma (Task 5), sudachi (Task 8), default `{}` for others; consumed by Task 12's unknown-option check and Task 11's languages route. `normalize_pos(pos, token_count: int | None)` defined and tested in Task 10, called with `token_count=None` on the `text` path by Task 12. `build_registry(use_fakes=...)` defined in Task 11 `main.py`, used by `conftest.py` in the same task. `Capabilities` has seven fields everywhere: Task 1 (`types.py`), Task 6 (English), Task 11 (languages fallback dict and its test), Task 12 (response).

**Defects found during offline review of this document:**

1. `tests/conftest.py` carried a dead `FakeBackend` class. `api/main.py` defines its own `_FakeBackend`, so the fixture never used the local one. Removed.
2. `normalize_pos` raised `"scalar 'pos' is only valid for a single token, got 0"` for every `{"text": ..., "pos": "VERB"}` request, because `token_count` was hardcoded to `0` on the text path. Signature widened to `int | None`; a per-token list with `text` now fails with an explicit message instead of silently mismatching.
3. `test_unavailable_backend_returns_503` built a **real** registry — loading all seven dictionaries, ~60 s — and then reached into `registry._entries` to poke one row. Rewritten to build the fake registry and register a failing factory, which is fast *and* exercises `Registry.register`'s degradation path end to end.

**Defects found by executing the plan (see the Verification table at the top):** the four listed there — Pydantic's 422 envelope bypassing the unified error format, module-level backend imports crashing startup for all seven languages, English silently degrading to identity whenever no POS tag was supplied, and two tests that contradicted the request schema.
