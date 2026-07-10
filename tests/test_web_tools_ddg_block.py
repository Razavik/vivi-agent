from __future__ import annotations

import pytest

from src.infra.errors import ToolExecutionError
from src.tools.web_tools import WebTools


class TestDdgAntiBotDetection:
    """DuckDuckGo при подозрении на бота отдаёт HTTP 200/202 со страницей-капчей
    ("anomaly-modal") вместо результатов поиска. Без детекции search_web молча
    возвращал бы {"count": 0, "results": []} — неотличимо от честного «ничего не
    найдено», из-за чего веб-агент выглядел «не работающим» без объяснения причины."""

    def test_detects_anomaly_modal_page(self) -> None:
        blocked_html = '<div id="anomaly-modal" class="anomaly-modal__box">captcha</div>'
        assert WebTools._is_ddg_anti_bot_challenge(blocked_html) is True

    def test_detects_challenge_form(self) -> None:
        blocked_html = '<form class="challenge-form">solve me</form>'
        assert WebTools._is_ddg_anti_bot_challenge(blocked_html) is True

    def test_normal_results_page_not_flagged(self) -> None:
        normal_html = '<div class="result__body"><a class="result__a" href="https://example.com">Example</a></div>'
        assert WebTools._is_ddg_anti_bot_challenge(normal_html) is False


_DDG_RESULT_HTML = (
    '<div class="result__body">'
    '<a class="result__a" href="https://example.com">Example Title</a>'
    '<span class="result__snippet">Some snippet text</span>'
    "</div>"
)

_DDG_BLOCKED_HTML = '<div id="anomaly-modal">captcha</div>'

_BING_RESULT_HTML = (
    '<li class="b_algo">'
    '<h2><a href="https://www.python.org/">Welcome to Python.org</a></h2>'
    '<p class="b_lineclamp2">Official Python site.</p>'
    "</li>"
)


class TestSearchWebFallback:
    """search_web пробует DuckDuckGo, а при блокировке/пустой выдаче автоматически
    переключается на Bing HTML — оба бесплатны и не требуют API-ключа."""

    def test_uses_duckduckgo_when_available(self, monkeypatch) -> None:
        import src.tools.web_tools as web_tools_module

        calls: list[str] = []

        def fake_fetch(url: str, timeout: int = 20):
            calls.append(url)
            return 200, _DDG_RESULT_HTML

        monkeypatch.setattr(web_tools_module, "_fetch_raw", fake_fetch)
        result = WebTools().search_web({"query": "python"})

        assert result["provider"] == "duckduckgo"
        assert result["count"] == 1
        assert all("duckduckgo" in u for u in calls), "Bing не должен вызываться, если DDG уже дал результаты"

    def test_falls_back_to_bing_when_ddg_blocked(self, monkeypatch) -> None:
        import src.tools.web_tools as web_tools_module

        def fake_fetch(url: str, timeout: int = 20):
            if "duckduckgo" in url:
                return 200, _DDG_BLOCKED_HTML
            return 200, _BING_RESULT_HTML

        monkeypatch.setattr(web_tools_module, "_fetch_raw", fake_fetch)
        result = WebTools().search_web({"query": "python"})

        assert result["provider"] == "bing"
        assert result["count"] == 1
        assert result["results"][0]["url"] == "https://www.python.org/"

    def test_falls_back_to_bing_when_ddg_raises(self, monkeypatch) -> None:
        import src.tools.web_tools as web_tools_module

        def fake_fetch(url: str, timeout: int = 20):
            if "duckduckgo" in url:
                raise ToolExecutionError("сеть недоступна")
            return 200, _BING_RESULT_HTML

        monkeypatch.setattr(web_tools_module, "_fetch_raw", fake_fetch)
        result = WebTools().search_web({"query": "python"})

        assert result["provider"] == "bing"

    def test_raises_clear_error_when_both_providers_fail(self, monkeypatch) -> None:
        import src.tools.web_tools as web_tools_module

        monkeypatch.setattr(
            web_tools_module, "_fetch_raw", lambda url, timeout=20: (200, _DDG_BLOCKED_HTML)
        )
        with pytest.raises(ToolExecutionError, match="DuckDuckGo|Bing"):
            WebTools().search_web({"query": "python"})


class TestBingParser:
    def test_parses_organic_results(self) -> None:
        results = WebTools()._parse_bing_results(_BING_RESULT_HTML, max_results=10)
        assert len(results) == 1
        assert results[0]["title"] == "Welcome to Python.org"
        assert results[0]["url"] == "https://www.python.org/"
        assert results[0]["snippet"] == "Official Python site."

    def test_respects_max_results(self) -> None:
        html_body = _BING_RESULT_HTML * 5
        results = WebTools()._parse_bing_results(html_body, max_results=2)
        assert len(results) == 2

    def test_decodes_ck_redirect_url(self) -> None:
        import base64

        real_url = "https://example.com/page?x=1"
        encoded = base64.urlsafe_b64decode  # noqa: F841 (sanity import check)
        b64 = base64.urlsafe_b64encode(real_url.encode()).decode().rstrip("=")
        href = f"https://www.bing.com/ck/a?!&amp;p=xyz&u=a1{b64}&ntb=1"
        decoded = WebTools._decode_bing_redirect(href.replace("&amp;", "&"))
        assert decoded == real_url

    def test_direct_href_passthrough(self) -> None:
        assert WebTools._decode_bing_redirect("https://example.com/") == "https://example.com/"

    def test_no_results_on_empty_page(self) -> None:
        assert WebTools()._parse_bing_results("<html><body>no results</body></html>", max_results=10) == []
