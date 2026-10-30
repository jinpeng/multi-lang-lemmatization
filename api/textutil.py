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
