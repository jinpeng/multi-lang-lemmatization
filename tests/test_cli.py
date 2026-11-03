from api.cli import main

MASTER = b"0" * 32


def test_create_key_prints_secret_once(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LEMMA_MASTER_KEY", MASTER.hex())
    monkeypatch.setenv("LEMMA_DB_PATH", str(tmp_path / "t.db"))
    assert main(["create-key", "--name", "bootstrap"]) == 0
    out = capsys.readouterr().out
    assert "lk_" in out
    assert "ls_" in out
    assert "shown once" in out


def test_hash_passphrase_prints_argon2_hash(tmp_path, capsys):
    assert main(["hash-passphrase", "secret123"]) == 0
    out = capsys.readouterr().out.strip()
    assert out.startswith("$argon2")
