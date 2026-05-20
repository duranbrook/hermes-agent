import json
import os
import pytest
from unittest.mock import MagicMock, patch


def test_parts_lookup_returns_part_when_api_succeeds():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "part_number": "33901-S84-A01",
        "part_name": "Brake Caliper – Front",
        "category": "Brakes",
        "confidence": 0.75,
        "vehicle": {"make": "Honda", "model": "Civic", "year": "2021", "trim": "Sport"},
        "source": "db",
    }
    mock_response.raise_for_status = lambda: None

    with patch.dict(os.environ, {"PARTS_API_URL": "http://test.internal"}):
        with patch("tools.parts_lookup.httpx.post", return_value=mock_response):
            from tools.parts_lookup import parts_lookup
            result_str = parts_lookup("front brake caliper single piston", "1HGBH41JXMN109186")

    result = json.loads(result_str)
    assert result["part_number"] == "33901-S84-A01"
    assert result["source"] == "db"


def test_parts_lookup_returns_not_found_when_api_returns_not_found():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "part_number": None,
        "part_name": None,
        "category": None,
        "confidence": None,
        "vehicle": {"make": "Unknown", "model": "Unknown", "year": "Unknown", "trim": ""},
        "source": "not_found",
    }
    mock_response.raise_for_status = lambda: None

    with patch.dict(os.environ, {"PARTS_API_URL": "http://test.internal"}):
        with patch("tools.parts_lookup.httpx.post", return_value=mock_response):
            from tools.parts_lookup import parts_lookup
            result_str = parts_lookup("mystery widget", "BADVIN")

    result = json.loads(result_str)
    assert result["source"] == "not_found"
    assert result["part_number"] is None


def test_parts_lookup_returns_error_when_api_unreachable():
    import httpx as real_httpx
    with patch.dict(os.environ, {"PARTS_API_URL": "http://test.internal"}):
        with patch("tools.parts_lookup.httpx.post", side_effect=real_httpx.ConnectError("refused")):
            from tools.parts_lookup import parts_lookup
            result_str = parts_lookup("brake caliper", "1HGBH41JXMN109186")

    result = json.loads(result_str)
    assert "error" in result


def test_parts_lookup_requires_part_description():
    with patch.dict(os.environ, {"PARTS_API_URL": "http://test.internal"}):
        from tools.parts_lookup import parts_lookup
        result_str = parts_lookup("", "1HGBH41JXMN109186")
    result = json.loads(result_str)
    assert "error" in result
