# multi-lang-lemmatization

**English** | [简体中文](README.zh-CN.md)

A lemmatization HTTP service covering **7 languages** — a FastAPI backend plus a
Next.js admin console, running fully offline in a single image.

Each language uses the analyser that actually fits it, instead of one library
forced to cover everything:

| Language | Backend | Emits POS | Accepts POS | Re-tokenizes | Request options |
|---|---|:---:|:---:|:---:|---|
| `en` English | [lemminflect](https://github.com/bjascob/LemmInflect) | — | ✅ | — | — |
| `de` German | [simplemma](https://github.com/adbar/simplemma) | — | — | — | `greedy` (default `true`) |
| `fr` French | simplemma | — | — | — | `greedy` (default `false`) |
| `es` Spanish | simplemma | — | — | — | `greedy` (default `false`) |
| `ru` Russian | [pymorphy3](https://github.com/pymorphy2/pymorphy3) | ✅ | — | — | — |
| `ja` Japanese | [SudachiPy](https://github.com/WorksApplications/SudachiPy) (core dict) | ✅ | — | ✅ | `split_mode`: `A`/`B`/`C` |
| `ko` Korean | [kiwipiepy](https://github.com/bab2min/kiwipiepy) | ✅ | — | ✅ | — |

> **Why these backends.** Japanese and Korean are agglutinative: a "lemma" is a
> by-product of morphological analysis, so segmentation has to come first.
> English, German, French, Spanish and Russian are fusional — dictionary lookup
> plus rules gets you there. The full survey is in
> [`docs/lemmatization-survey.md`](docs/lemmatization-survey.md).

## Quick start

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"
uv run uvicorn api.main:app --reload --port 8000
```

Try it:

```bash
curl -s localhost:8000/v1/lemmatize \
  -H 'content-type: application/json' \
  -d '{"lang": "ja", "text": "私は東京へ行きました"}'
```

```json
{
  "lang": "ja",
  "segmented_by": "backend",
  "offset_unit": "unicode_code_point",
  "items": [
    {"surface": "行き", "lemma": "行く", "pos": "動詞,...", "start": 5, "end": 7}
  ]
}
```

## API

| Method | Path | Description |
|---|---|---|
| GET | `/v1/health` | Readiness per language backend |
| GET | `/v1/languages` | Capability matrix plus per-language options |
| POST | `/v1/lemmatize` | The only compute endpoint |
| POST/GET/… | `/admin/*` | API keys, settings, audit log, request log (admin session required) |

### `POST /v1/lemmatize`

Send exactly one of `text` or `tokens`.

```json
{
  "lang": "en",
  "tokens": ["was", "left"],
  "pos": ["VERB", "VERB"],
  "options": {}
}
```

Every returned item carries `surface`, `lemma`, `pos`, `prov`, `start` and
`end`; Japanese additionally returns `reading`. `prov` tells you how the lemma
was produced (`dict`, `rule`, `model`, `identity`, `candidates`), which matters
if you want to weigh a real dictionary hit differently from a passthrough.

**Three semantics every client must know:**

1. **Offsets are code point offsets** into the request's `text`, and are omitted
   when you send `tokens` (there is no source string to point into). Python
   counts code points; JavaScript strings index UTF-16 code units. They agree
   inside the BMP and diverge for emoji and ideographs above U+FFFF, where
   `text.slice(start, end)` silently returns the wrong span.
2. **`surface` is not always `text[start:end]`.** Korean contracted forms
   decompose: `갔` becomes `가/VV` + `었/EP`, both over `[0:1]`. The span is
   correct; `surface` is the morpheme, not the substring.
3. **`pos` and `pos_accepted` are different questions.** `pos` means the backend
   *emits* a tag (ru, ja, ko); `pos_accepted` means it *uses* one you send (en).
   English changes its answer based on POS — `left` + `VERB` → `leave`,
   `left` + `NOUN` → `left` — but never returns a tag.

## Repository layout

```
api/        FastAPI service (backends/ holds the 7 language adapters)
console/    Next.js admin console (keys, language matrix, logs, settings)
deploy/     Docker Compose deployment (api + console)
tests/      pytest suite, including cross-language golden cases
scripts/    UD treebank download and accuracy evaluation
docs/       Survey and design spec
```

## Tests

```bash
uv run pytest -m "not slow"   # fast: skips ja/ko dictionary loads
uv run pytest                 # full: 230 cases, including the 7-language golden set
uv run ruff check . && uv run ruff format --check .
```

The suite has two layers. `tests/backends/` holds per-language adapter tests
(morphology, offset contract, option overrides). `tests/test_golden.py` runs
cross-language golden cases through the real API (`was`→`be`, `Häuser`→`Haus`,
`食べました`→`食べる`, `먹었습니다`→`먹다`, …).

## Accuracy evaluation

Those golden cases are smoke tests, not a measurement. For real numbers, the
project ships an evaluation harness against the official Universal Dependencies
test treebanks:

```bash
./scripts/download_ud.sh                        # fetch UD test sets into data/ud/
uv run python -m scripts.evaluate_ud            # 7-language report
uv run python -m scripts.evaluate_ud --json     # machine-readable
uv run python -m scripts.evaluate_ud --langs ja ko
```

Latest results, scoring content words only (NOUN/VERB/ADJ/ADV/PROPN/NUM):

| Language | Backend | Accuracy | Tokens scored | Notes |
|---|---|-------:|---:|---|
| en | lemminflect | **95.83%** | 12,324 | Given gold UPOS for disambiguation |
| de | simplemma | **95.46%** | 7,999 | `greedy=true` |
| fr | simplemma | **94.45%** | 4,507 | `greedy=false` |
| es | simplemma | **93.66%** | 5,550 | `greedy=false` |
| ru | pymorphy3 | **93.25%** | 6,784 | OpenCorpora dictionary |
| ja | sudachipy | **88.89%** | 5,554 | UD writes kanji lemmas; compared after normalising to katakana readings |
| ko | kiwipiepy | **94.02%** | 7,946 | UD composite lemmas (`있+다`) aligned against Kiwi dictionary forms (`있다+다`) |

Gold tokens whose segmentation disagrees with the analyser (801 for Japanese,
1,687 for Korean) are reported as `unaligned` and excluded from the denominator
rather than scored wrong — comparing them would measure segmentation, not
lemmatization.

## Deployment

See [`deploy/README.md`](deploy/README.md). The essentials: run every command
from `deploy/`, keep `.env` next to `docker-compose.yml`, and generate all three
secrets (`LEMMA_MASTER_KEY`, `LEMMA_SERVICE_TOKEN`, the admin passphrase hash)
with the provided CLI instead of inventing values.

```bash
cd deploy && cp .env.example .env
# …generate the secrets…
docker compose up -d --build
```

The console is at http://localhost:3000, the API at http://localhost:8000.

## Documentation

- [`docs/lemmatization-survey.md`](docs/lemmatization-survey.md) — open-source
  survey across the 7 languages, and the basis for backend selection
- [`docs/superpowers/specs/2026-10-29-multilingual-lemmatization-design.md`](docs/superpowers/specs/2026-10-29-multilingual-lemmatization-design.md) — design spec
- [`api/README.md`](api/README.md) — API details (POS semantics, offset contract)
- [`deploy/README.md`](deploy/README.md) — operations manual

## License

[MIT](LICENSE)
