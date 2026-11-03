# Lemma API — operations

## First run

All commands below run in **`deploy/`**. Compose reads `.env` from the directory
holding `docker-compose.yml`, so a `.env` placed at the repo root is silently
ignored — and the resulting error names a missing variable, not the wrong path.

```bash
cd deploy
cp .env.example .env

# Generate the three required values; do not invent them.
echo "LEMMA_MASTER_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')" >> .env
echo "LEMMA_SERVICE_TOKEN=svc-$(python3 -c 'import secrets; print(secrets.token_hex(16))')" >> .env
# Compose interpolates '$' and argon2 hashes are full of them, so generate the
# escaped line rather than pasting a raw hash:
python -m api.cli env-line 'your passphrase' >> .env

docker compose up -d --build
docker compose exec api python -m api.cli create-key --name console-demo --allow-hmac
```

Put the printed `key_id.secret` into `LEMMA_DEMO_KEY` in `.env`, then:

```bash
docker compose up -d console
```

Open http://localhost:3000 and sign in with the passphrase.

`.env.example` documents every variable, including the ones the image sets
itself and that must not be overridden.

## Secrets you must not lose

| Variable | If lost |
|---|---|
| `LEMMA_MASTER_KEY` | Every stored API secret becomes unverifiable. All keys must be reissued. |
| `LEMMA_SERVICE_TOKEN` | Console cannot reach the API. Rotate it in both services together. |
| `LEMMA_ADMIN_PASSPHRASE_HASH` | No admin access. Regenerate and restart `api`. |

> **The `$` trap.** Docker Compose interpolates `$` inside `.env`, and an argon2
> hash looks like `$argon2id$v=19$m=65536,t=3,p=4$salt$hash`. Written literally
> it silently becomes `=19=65536,t=3,p=4` and *every* login fails with "wrong
> passphrase" — which reads like a credentials problem, not a config one.
> Always generate the line with `python -m api.cli env-line '<passphrase>'`,
> which doubles the `$` for you. The API also refuses to start if the value does
> not begin with `$argon2`, so this cannot reach production silently.

**Back up `LEMMA_MASTER_KEY` outside this host.** It is not in the database, and without it the encrypted secrets in `lemming.db` are unrecoverable by design.

## Backups

The whole state is one SQLite file:

```bash
docker compose exec api sqlite3 /data/lemming.db ".backup /data/backup.db"
docker compose cp api:/data/backup.db ./lemming-$(date +%F).db
```

Run this before every upgrade. Restore by replacing the file while the stack is stopped.

## Rotating an API key

Console → Keys → `rotate`. The old secret keeps working for 24 hours so callers can switch without downtime; responses carry `X-Secret-Rotated: true` during that window.

If `LEMMA_MASTER_KEY` is compromised, rotation alone is insufficient: every key must be reissued, because the attacker can decrypt `secret_enc`.

## Memory: the number that actually bites

Every `api` worker is its own process and loads **all seven** backends.
Measured inside the running container (`/proc/<pid>/status VmRSS`):

| process | steady state |
|---|---|
| worker A | 447 MB |
| worker B | 569 MB |
| parent | 26 MB |
| **`LEMMA_WORKERS=2` total** | **~1.0 GB** |

Peak during startup is higher (~820 MB for a single process) because the
dictionaries are decompressed while loading. Size the host against the peak,
not the steady state, or the container will be OOM-killed during boot.

Backends by weight, per worker: `ko` (kiwipiepy) ~357 MB, `ja` (sudachipy +
core dict) ~82 MB, `ru` ~36 MB, `en` ~16 MB, `de`/`fr`/`es` ~7 MB each.

`LEMMA_WORKERS` defaults to **2**. Raising it multiplies the above: 4 workers
is roughly 2 GB steady / ~3.3 GB peak. Dropping `ko` is the single biggest
lever if you need to shrink this.

## Rate limiting and single-instance assumptions

The nonce cache and rate-limit buckets are **in-process**. Running more than one `api` replica breaks HMAC replay protection (a nonce consumed on replica A is unknown to B). Scale `--workers` only; do not scale replicas without moving both caches to a shared store.

## Health

`GET /v1/health` needs no credentials and reports per-backend readiness. A backend can be `unavailable` while the service is otherwise healthy — check Settings → Diagnostics for the reason.

## Logs

```bash
docker compose logs -f api console
```

Audit entries (key and settings changes) live in the database, not stdout. View them at `/logs`.