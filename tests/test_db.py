from api.db import init_db, session


def test_init_db_creates_all_tables(tmp_path):
    db = tmp_path / "t.db"
    init_db(f"sqlite:///{db}")
    with session(f"sqlite:///{db}") as conn:
        names = {
            r[0]
            for r in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert {"api_keys", "settings", "audit_log", "request_log"} <= names


def test_init_db_is_idempotent(tmp_path):
    url = f"sqlite:///{tmp_path / 't.db'}"
    init_db(url)
    init_db(url)  # must not raise


def test_foreign_keys_and_wal_are_enabled(tmp_path):
    url = f"sqlite:///{tmp_path / 't.db'}"
    init_db(url)
    with session(url) as conn:
        assert conn.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
