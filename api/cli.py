"""Bootstrap helpers, run before the API has any keys.

python -m api.cli create-key --name bootstrap
python -m api.cli hash-passphrase 'my passphrase'
"""

from __future__ import annotations

import argparse
import os
import sys

from api.auth.admin import hash_passphrase
from api.db import default_url, init_db
from api.store import keys


def _master_key() -> bytes:
    raw = os.environ.get("LEMMA_MASTER_KEY", "")
    if not raw:
        print("LEMMA_MASTER_KEY is not set", file=sys.stderr)
        raise SystemExit(2)
    return bytes.fromhex(raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="api.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-key", help="create an API key")
    create.add_argument("--name", required=True)
    create.add_argument("--allow-hmac", action="store_true")
    create.add_argument("--langs", default="")

    hp = sub.add_parser("hash-passphrase", help="hash an admin passphrase")
    hp.add_argument("passphrase")

    el = sub.add_parser("env-line", help="print a ready-to-paste .env line for a passphrase")
    el.add_argument("passphrase")

    args = parser.parse_args(argv)

    if args.command == "hash-passphrase":
        print(hash_passphrase(args.passphrase))
        return 0

    if args.command == "env-line":
        # Docker Compose interpolates '$' in .env values, and an argon2 hash is
        # full of them. Doubling is the documented escape; doing it here means
        # an operator cannot get it wrong by hand.
        hashed = hash_passphrase(args.passphrase)
        print(f"LEMMA_ADMIN_PASSPHRASE_HASH={hashed.replace('$', '$$')}")
        return 0

    url = default_url()
    init_db(url)
    langs = [x for x in args.langs.split(",") if x]
    created = keys.create(
        url,
        name=args.name,
        created_by="cli",
        master_key=_master_key(),
        allow_hmac=args.allow_hmac,
        langs=langs,
    )
    print(f"key_id     : {created.key_id}")
    print(f"secret     : {created.secret}")
    print(f"fingerprint: {created.secret_fingerprint}")
    print("\nThe secret is shown once and cannot be recovered. Store it now.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
