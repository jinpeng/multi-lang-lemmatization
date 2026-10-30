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
| en | lemminflect | accepts, emits none | no |
| de | simplemma (greedy=true) | no | no |
| fr | simplemma (greedy=false) | no | no |
| es | simplemma (greedy=false) | no | no |
| ru | pymorphy3 | yes | no |
| ja | sudachipy (dict=core) | yes | **yes** |
| ko | kiwipiepy | yes | **yes** |

`segmented_by` in the response tells you whether your tokens were honoured
(`"input"`) or the backend re-segmented the text (`"backend"`).

### `pos` vs `pos_accepted`

They are different questions and the difference is load-bearing:

- `pos` — the backend **produces** a tag (ru, ja, ko)
- `pos_accepted` — the backend **uses** a tag you send (en)

English accepts `upos` and changes its answer based on it (`left` + `VERB` →
`leave`; `left` + `NOUN` → `left`) but never returns a tag. Collapsing the two
into one flag would tell clients that English ignores POS, and they would lose
accuracy on every ambiguous word.

## Character offsets

Items carry `start`/`end`. They are **code point** offsets into the request's
`text`, and are omitted when the caller sent `tokens` (no source string to point
into). `offset_unit` states the unit at the top level.

Two things consumers must know:

1. **JavaScript needs a conversion.** Python and both analysers count code
   points; JS strings index UTF-16 code units. They agree inside the BMP and
   diverge for emoji or ideographs above U+FFFF, where `text.slice(start, end)`
   silently returns the wrong span.
2. **`surface` is not always `text[start:end]`.** Korean contracted forms
   decompose: 갔 becomes 가/VV + 었/EP, both over `[0:1]`. The span is correct;
   `surface` is the morpheme, not the substring.

## Test

```bash
uv run pytest -m "not slow"   # fast: skips ja/ko dictionary loads
uv run pytest                 # full
uv run ruff check . && uv run ruff format --check .
```
