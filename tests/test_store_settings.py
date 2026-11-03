import pytest

from api.db import init_db
from api.settings.registry import EDITABLE, validate
from api.store import audit, settings


@pytest.fixture
def url(tmp_path):
    u = f"sqlite:///{tmp_path / 't.db'}"
    init_db(u)
    return u


def test_defaults_are_returned_when_nothing_is_stored(url):
    merged = settings.effective(url)
    assert merged["langs.de.greedy"] is True
    assert merged["langs.fr.greedy"] is False
    assert merged["ratelimit.default_rpm"] == 600


def test_write_then_read_a_whitelisted_key(url):
    settings.set_value(url, "langs.de.greedy", False, actor="admin")
    assert settings.effective(url)["langs.de.greedy"] is False


def test_unknown_key_is_rejected(url):
    with pytest.raises(KeyError, match="not editable"):
        settings.set_value(url, "db.dsn", "x", actor="admin")


def test_out_of_range_value_is_rejected(url):
    with pytest.raises(ValueError):
        settings.set_value(url, "ratelimit.default_rpm", 0, actor="admin")


def test_enum_value_is_validated(url):
    with pytest.raises(ValueError):
        settings.set_value(url, "langs.ja.split_mode", "Z", actor="admin")
    settings.set_value(url, "langs.ja.split_mode", "A", actor="admin")
    assert settings.effective(url)["langs.ja.split_mode"] == "A"


def test_write_creates_an_audit_row(url):
    settings.set_value(url, "langs.de.greedy", False, actor="alice")
    rows = audit.list_entries(url)
    assert len(rows) == 1
    assert rows[0]["actor"] == "alice"
    assert rows[0]["target"] == "langs.de.greedy"
    assert rows[0]["before_json"] == "true"
    assert rows[0]["after_json"] == "false"


def test_hot_flag_is_exposed_for_every_entry():
    for name, spec in EDITABLE.items():
        assert isinstance(spec.hot, bool), name


def test_validate_rejects_bool_as_int():
    """True is an int in Python; a rpm of True must not slip through."""
    with pytest.raises(ValueError):
        validate("ratelimit.default_rpm", True)
