import pytest

from api.errors import ApiError


def test_api_error_carries_code_status_and_message():
    err = ApiError("UNKNOWN_OPTION", 400, "unknown option(s)", {"unknown": ["nope"]})
    assert err.code == "UNKNOWN_OPTION"
    assert err.status == 400
    assert err.message == "unknown option(s)"
    assert err.details == {"unknown": ["nope"]}


def test_api_error_details_default_to_empty_dict():
    err = ApiError("INTERNAL", 500, "boom")
    assert err.details == {}


def test_api_error_is_an_exception():
    with pytest.raises(ApiError):
        raise ApiError("INTERNAL", 500, "boom")
