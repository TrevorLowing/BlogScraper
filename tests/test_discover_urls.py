from blog_scraper.discover import list_page_url


def test_list_page_urls():
    base = "https://www.example.com"
    path = "/list/w/xmzb"
    assert list_page_url(base, path, None) == "https://www.example.com/list/w/xmzb"
    assert list_page_url(base, path, 1) == "https://www.example.com/list/w/xmzb"
    assert "?page=" in list_page_url(base, path, 3)
