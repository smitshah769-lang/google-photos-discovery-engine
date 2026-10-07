from pathlib import Path

from pipeline.adapters.play_parser import (
    PlayParseError,
    parse_batchexecute_response,
    should_stop_pagination,
    unwrap_batchexecute_body,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_unwrap_batchexecute_prefix():
    raw = (FIXTURES / "play_batchexecute.txt").read_text()
    outer = unwrap_batchexecute_body(raw)
    assert isinstance(outer, list)


def test_parse_reviews_from_fixture():
    raw = (FIXTURES / "play_batchexecute.txt").read_text()
    result = parse_batchexecute_response(raw, "en-us")
    assert len(result.reviews) == 2
    assert result.reviews[0].review_id == "gp-review-1"


def test_continuation_token_loop_stops():
    seen: set[str] = set()
    assert should_stop_pagination(seen, None, None) is True
    assert should_stop_pagination(seen, "t1", "t1") is True
    seen.add("t1")
    assert should_stop_pagination(seen, "t1", "t1") is True


def test_html_interstitial_fails():
    try:
        unwrap_batchexecute_body("<html>CAPTCHA</html>")
        assert False
    except PlayParseError:
        pass
