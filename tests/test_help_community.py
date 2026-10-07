from pipeline.adapters.help_community import filter_cse_urls, is_allowed_thread_url


def test_cse_off_site_url_discard():
    urls = [
        "https://support.google.com/photos/thread/abc123/title",
        "https://reddit.com/r/googlephotos/foo",
        "http://support.google.com/photos/thread/abc123/",
    ]
    kept = filter_cse_urls(urls)
    assert len(kept) == 1
    assert is_allowed_thread_url(kept[0])
