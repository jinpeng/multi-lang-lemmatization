#!/usr/bin/env bash
# Download UD test treebanks used by scripts/evaluate_ud.py into data/ud/.
set -euo pipefail
cd "$(dirname "$0")/../data/ud"

base=https://raw.githubusercontent.com/UniversalDependencies
fetch() { # repo file
  curl -fsSL --retry 3 -o "$2.conllu" "$base/$1/master/$2.conllu"
  echo "$2: $(wc -l < "$2.conllu" | tr -d ' ') lines"
}

fetch UD_English-EWT   en_ewt-ud-test
fetch UD_German-GSD    de_gsd-ud-test
fetch UD_French-GSD    fr_gsd-ud-test
fetch UD_Spanish-GSD   es_gsd-ud-test
fetch UD_Russian-GSD   ru_gsd-ud-test
fetch UD_Japanese-GSD  ja_gsd-ud-test
fetch UD_Korean-GSD    ko_gsd-ud-test
