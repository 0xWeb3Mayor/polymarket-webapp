import pytest
import sys
sys.path.insert(0, ".")
import parser as p


def test_parse_raw_condition_id():
    result = p.extract_condition_id("0xabc123def456")
    assert result == "0xabc123def456"


def test_parse_market_url():
    result = p.extract_condition_id(
        "https://polymarket.com/market/0xabc123def456"
    )
    assert result == "0xabc123def456"


def test_parse_event_url_with_hex_slug():
    result = p.extract_condition_id(
        "https://polymarket.com/event/bitcoin/0xabc123def456"
    )
    assert result == "0xabc123def456"


def test_parse_invalid_url():
    result = p.extract_condition_id("not-a-url")
    assert result is None


def test_parse_empty_string():
    result = p.extract_condition_id("")
    assert result is None
