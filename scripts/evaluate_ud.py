"""Evaluate each backend's lemmatization accuracy on UD test treebanks.

For every gold token in the treebank we ask the backend for a lemma and
compare, per language, in the way that matches the backend's contract:

- en, de, fr, es, ru: the backend consumes gold UD tokens directly
  (`tokens=`), so alignment is 1:1. English additionally receives the gold
  UPOS tag, which it uses to disambiguate.
- ja, ko: the backend re-segmentizes (`text=`), so we compare gold tokens
  against predicted morphemes by character span. Both GSD treebanks segment
  close to what the analysers produce, so span lookup is normally exact;
  where the segmentations disagree the token is counted as 'unaligned' and
  excluded from accuracy rather than scored wrong.

Usage:
    uv run python -m scripts.evaluate_ud                 # all languages
    uv run python -m scripts.evaluate_ud --langs ja ko   # subset
    uv run python -m scripts.evaluate_ud --json          # machine-readable
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import conllu

from api.main import build_registry

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "ud"

# Content words only: UD lemmatizes function words too, but judging a
# lemmatizer on punctuation and determiners says nothing about morphology.
CONTENT_POS = {"NOUN", "VERB", "ADJ", "ADV", "PROPN", "NUM"}

TREEBANKS = {
    "en": "en_ewt-ud-test.conllu",
    "de": "de_gsd-ud-test.conllu",
    "fr": "fr_gsd-ud-test.conllu",
    "es": "es_gsd-ud-test.conllu",
    "ru": "ru_gsd-ud-test.conllu",
    "ja": "ja_gsd-ud-test.conllu",
    "ko": "ko_gsd-ud-test.conllu",
}

# Backends that must receive `text` because they retokenize.
RETOKENIZING = {"ja", "ko"}


@dataclass
class Score:
    total: int = 0
    correct: int = 0
    unaligned: int = 0
    skipped_pos: int = 0
    by_pos: dict[str, list[int]] = field(default_factory=dict)  # upos -> [total, correct]
    misses: list[tuple[str, str, str]] = field(default_factory=list)  # (surface, gold, pred)

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    def record(self, upos: str, ok: bool, surface: str, gold: str, pred: str) -> None:
        self.total += 1
        self.correct += ok
        slot = self.by_pos.setdefault(upos, [0, 0])
        slot[0] += 1
        slot[1] += ok
        if not ok and len(self.misses) < 20:
            self.misses.append((surface, gold, pred))


def norm(s: str | None) -> str:
    return (s or "").strip().lower()


def evaluate_tokens_mode(backend, sentences) -> Score:
    """en/de/fr/es/ru: hand gold tokens to the backend, compare 1:1."""
    score = Score()
    for sent in sentences:
        words = [t for t in sent if isinstance(t["id"], int)]
        surfaces = [w["form"] for w in words]
        poses = [w["upos"] for w in words]
        golds = [w["lemma"] for w in words]

        # lemminflect prints "Invalid upos type" for tags outside its tagset
        # (function words); only content-word tags are worth passing.
        if backend.lang == "en":
            pos_arg = [p if p in {"NOUN", "VERB", "ADJ", "ADV", "PROPN"} else None for p in poses]
        else:
            pos_arg = None
        items = backend.lemmatize(text=None, tokens=surfaces, pos=pos_arg, options={})
        if len(items) != len(words):  # defensive; these backends never retokenize
            raise RuntimeError(f"{backend.lang}: item count mismatch")

        for w, gold, item, upos in zip(surfaces, golds, items, poses, strict=True):
            if upos not in CONTENT_POS:
                score.skipped_pos += 1
                continue
            score.record(upos, norm(item.lemma) == norm(gold), w, gold, item.lemma)
    return score


def evaluate_text_mode(backend, sentences) -> Score:
    """ja/ko: send raw text, align gold tokens to predicted morphemes by span.

    Korean UD lemmas are composite (`수석+연구원+은`: the lemmas of the
    morphemes inside the token, joined by '+'), so we collect all predicted
    morphemes whose span lies inside the gold token's span and join their
    lemmas the same way. Japanese UD lemmas are often kanji where Sudachi
    emits the dictionary's canonical (kana) form, so exact lemma equality is
    also counted as a soft match when the morpheme surfaces cover the gold
    surface exactly (same segmentation, script-only difference).
    """
    score = Score()
    for sent in sentences:
        words = [t for t in sent if isinstance(t["id"], int)]
        text = sent.metadata.get("text")
        if text is None:  # reconstruct an approximation if metadata is missing
            text = "".join(w["form"] for w in words)

        items = backend.lemmatize(text=text, tokens=None, pos=None, options={})
        spans = [it for it in items if it.start is not None and it.end is not None]

        cursor = 0
        for w in words:
            upos = w["upos"]
            # Gold forms exclude spaces; the UD text includes them. Advance
            # past whitespace, then match the form at the cursor.
            while cursor < len(text) and text[cursor].isspace():
                cursor += 1
            start, end = cursor, cursor + len(w["form"])
            cursor = end
            if text[start:end] != w["form"]:
                # text and tokenisation disagree (normalisation); skip token
                score.unaligned += 1
                continue
            if upos not in CONTENT_POS:
                score.skipped_pos += 1
                continue

            covering = sorted(
                (it for it in spans if it.start >= start and it.end <= end),
                key=lambda i: i.start,
            )
            # The morphemes must tile the gold span exactly; partial or
            # overflowing coverage means the segmentations disagree.
            tiled = "".join(it.surface for it in covering)
            if not covering or tiled != w["form"]:
                score.unaligned += 1
                continue

            pred = (
                "+".join(it.lemma for it in covering)
                if backend.lang == "ko"
                else "".join(it.lemma for it in covering)
            )
            gold = w["lemma"]
            ok = norm(pred) == norm(gold)
            if not ok and backend.lang == "ja":
                # Script difference: UD writes the lemma in kanji (居る) where
                # Sudachi's dictionary_form is kana (いる). Compare katakana
                # readings of both lemma strings.
                pred_reading = "".join(it.reading or it.surface for it in covering)
                gold_items = backend.lemmatize(text=gold, tokens=None, pos=None, options={})
                gold_reading = "".join(g.reading or g.surface for g in gold_items)
                ok = bool(pred_reading) and pred_reading == gold_reading
            if not ok and backend.lang == "ko" and "+" in gold:
                # UD gold uses raw stem (있) while Kiwi returns dictionary
                # form (있다); accept when the first morphemes match modulo
                # the trailing 다/하다.
                gold_parts = gold.split("+")
                pred_parts = pred.split("+")
                if len(gold_parts) == len(pred_parts):
                    ok = all(
                        norm(g) == norm(p)
                        or (g in p and p.endswith("다"))
                        or (p in g and g.endswith("다"))
                        for g, p in zip(gold_parts, pred_parts, strict=True)
                    )
            score.record(upos, ok, w["form"], gold, pred)
    return score


def evaluate_lang(lang: str, registry) -> Score:
    path = DATA_DIR / TREEBANKS[lang]
    with path.open(encoding="utf-8") as fh:
        sentences = conllu.parse(fh.read())
    backend = registry.get(lang).backend
    if lang in RETOKENIZING:
        return evaluate_text_mode(backend, sentences)
    return evaluate_tokens_mode(backend, sentences)


def print_report(results: dict[str, Score]) -> None:
    print(f"\n{'lang':<5} {'accuracy':>9} {'correct':>8} {'total':>7} {'unaligned':>10}")
    print("-" * 44)
    for lang, s in results.items():
        print(f"{lang:<5} {s.accuracy:>9.2%} {s.correct:>8} {s.total:>7} {s.unaligned:>10}")
    print()
    for lang, s in results.items():
        print(f"== {lang} ==")
        for upos, (total, correct) in sorted(s.by_pos.items()):
            print(f"   {upos:<6} {correct / total:>7.2%}  ({correct}/{total})")
        if s.misses:
            print("   sample misses (surface -> gold != pred):")
            for surface, gold, pred in s.misses[:10]:
                print(f"     {surface} -> {gold} != {pred}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--langs", nargs="+", default=list(TREEBANKS), choices=list(TREEBANKS))
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a report")
    args = parser.parse_args()

    missing = [lang for lang in args.langs if not (DATA_DIR / TREEBANKS[lang]).exists()]
    if missing:
        print(f"missing treebanks for {missing}; run scripts/download_ud.sh first", file=sys.stderr)
        return 2

    registry = build_registry()
    results: dict[str, Score] = {}
    for lang in args.langs:
        entry = registry.get(lang)
        if entry is None or entry.status != "ok":
            reason = entry.reason if entry else "unknown"
            print(f"{lang}: backend unavailable ({reason})", file=sys.stderr)
            continue
        results[lang] = evaluate_lang(lang, registry)

    if args.json:
        payload = {
            lang: {
                "accuracy": round(s.accuracy, 4),
                "correct": s.correct,
                "total": s.total,
                "unaligned": s.unaligned,
                "by_pos": {
                    p: {"accuracy": round(c / t, 4), "total": t} for p, (t, c) in s.by_pos.items()
                },
            }
            for lang, s in results.items()
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_report(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
