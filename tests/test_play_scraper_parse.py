from pipeline.adapters.play_parser import parse_scraper_inner_data


def test_parse_scraper_row_shape():
    data = [
        [
            [
                "rev-1",
                ["user", None, None, None],
                4,
                None,
                "cannot find old photos in search",
                None,
                [6],
                None,
            ]
        ],
        [None, "token-abc"],
    ]
    result = parse_scraper_inner_data(data, "en-us")
    assert len(result.reviews) == 1
    assert result.reviews[0].review_id == "rev-1"
    assert "find" in result.reviews[0].text
    assert result.continuation_token == "token-abc"
