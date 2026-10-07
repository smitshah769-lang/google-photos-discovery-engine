from pipeline.adapters.reddit import _parse_arctic_payload


def test_rejects_unknown_q_style_errors():
    try:
        _parse_arctic_payload({"data": None, "error": "Unknown query parameter: 'q'"})
        assert False
    except Exception as exc:
        assert "q" in str(exc)


def test_parses_data_array():
    rows = _parse_arctic_payload({"data": [{"id": "abc", "title": "t"}]})
    assert len(rows) == 1
    assert rows[0]["id"] == "abc"
