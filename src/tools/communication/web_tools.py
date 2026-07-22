from __future__ import annotations

import base64
import html
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from src.infra.errors import ToolExecutionError

_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
_MAX_CONTENT = 20000


def _strip_html(raw: str) -> str:
    """Извлекает читаемый текст из HTML: убирает скрипты/стили, теги, лишние пробелы."""
    # Удаляем <script> и <style> вместе с содержимым
    raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.DOTALL | re.IGNORECASE)
    # Убираем HTML-теги
    raw = re.sub(r"<[^>]+>", " ", raw)
    # Декодируем HTML-сущности (&amp; &lt; &nbsp; и т.д.)
    raw = html.unescape(raw)
    # Убираем повторяющиеся пробелы / переносы
    raw = re.sub(r"[ \t]+", " ", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()


def _fetch_raw(url: str, timeout: int = 20) -> tuple[int, str]:
    """Делает HTTP GET, возвращает (status_code, raw_text)."""
    headers = {"User-Agent": _USER_AGENT, "Accept-Language": "ru,en;q=0.9"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        raise ToolExecutionError(f"HTTP ошибка {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        raise ToolExecutionError(f"Ошибка URL: {e.reason}")
    except Exception as e:
        raise ToolExecutionError(f"Не удалось получить содержимое страницы: {e}")


def _normalize_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        if "." in url:
            return "https://" + url
        raise ToolExecutionError(f"Некорректный URL: {url}")
    return url


class WebTools:
    def __init__(self) -> None:
        pass

    def fetch_url(self, args: dict[str, Any]) -> dict[str, Any]:
        url = _normalize_url(str(args.get("url", "")))
        parse_text = str(args.get("parse_text", "true")).lower() not in {"false", "0", "no"}

        status, raw = _fetch_raw(url)

        if parse_text:
            content = _strip_html(raw)
        else:
            content = raw

        if len(content) > _MAX_CONTENT:
            content = content[:_MAX_CONTENT] + "\n\n... (контент обрезан)"

        return {
            "url": url,
            "status_code": status,
            "content": content,
            "parsed": parse_text,
        }

    def search_web(self, args: dict[str, Any]) -> dict[str, Any]:
        """Поиск в интернете без API-ключей и без оплаты: сначала DuckDuckGo,
        при блокировке (anti-bot капча) — автоматический fallback на Bing HTML.
        Оба провайдера — обычный HTML-скрейпинг, без регистрации и лимитов ключа."""
        query = str(args.get("query", "")).strip()
        if not query:
            raise ToolExecutionError("Параметр query не может быть пустым")
        max_results = min(int(str(args.get("max_results", 10))), 20)

        errors: list[str] = []

        try:
            results = self._search_duckduckgo(query, max_results)
            if results:
                return {"query": query, "count": len(results), "results": results, "provider": "duckduckgo"}
            errors.append("DuckDuckGo: 0 результатов")
        except ToolExecutionError as e:
            errors.append(f"DuckDuckGo: {e}")

        try:
            results = self._search_bing(query, max_results)
            if results:
                return {"query": query, "count": len(results), "results": results, "provider": "bing"}
            errors.append("Bing: 0 результатов")
        except ToolExecutionError as e:
            errors.append(f"Bing: {e}")

        raise ToolExecutionError(
            "Веб-поиск недоступен ни через один бесплатный провайдер ("
            + "; ".join(errors)
            + "). Попробуй fetch_url напрямую по конкретному сайту или уточни запрос."
        )

    def _search_duckduckgo(self, query: str, max_results: int) -> list[dict[str, str]]:
        encoded = urllib.parse.urlencode({"q": query, "kl": "ru-ru"})
        candidates = [
            f"https://html.duckduckgo.com/html/?{encoded}",
            f"https://duckduckgo.com/html/?{encoded}",
        ]
        last_error = ""
        for attempt_url in candidates:
            try:
                _, raw = _fetch_raw(attempt_url, timeout=25)
            except ToolExecutionError as e:
                last_error = str(e)
                continue
            if self._is_ddg_anti_bot_challenge(raw):
                last_error = "заблокировал запрос как автоматический (anti-bot капча)"
                continue
            return self._parse_ddg_results(raw, max_results)
        raise ToolExecutionError(last_error or "недоступен")

    def _search_bing(self, query: str, max_results: int) -> list[dict[str, str]]:
        encoded = urllib.parse.urlencode({"q": query, "setlang": "ru"})
        _, raw = _fetch_raw(f"https://www.bing.com/search?{encoded}", timeout=25)
        return self._parse_bing_results(raw, max_results)

    @staticmethod
    def _is_ddg_anti_bot_challenge(html_body: str) -> bool:
        """DuckDuckGo при подозрении на бота отдаёт HTTP 200/202 со страницей-капчей
        ("anomaly-modal") вместо результатов. Без этой проверки search_web молча
        возвращал бы count=0 — неотличимо от честного «ничего не найдено»."""
        return "anomaly-modal" in html_body or "challenge-form" in html_body

    def _parse_ddg_results(self, html_body: str, max_results: int) -> list[dict[str, str]]:
        """Парсит HTML-ответ DuckDuckGo и извлекает результаты поиска."""
        results: list[dict[str, str]] = []

        # DuckDuckGo HTML отдаёт результаты в <div class="result__body"> или аналогичных блоках
        # Ищем заголовки и ссылки через регулярки
        block_pattern = re.compile(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?'
            r'class="result__snippet"[^>]*>(.*?)</span>',
            re.DOTALL,
        )

        for match in block_pattern.finditer(html_body):
            raw_url = match.group(1)
            title = _strip_html(match.group(2))
            snippet = _strip_html(match.group(3))

            # DuckDuckGo иногда оборачивает URL в редирект
            if raw_url.startswith("//duckduckgo.com/l/?"):
                parsed = urllib.parse.urlparse("https:" + raw_url)
                qs = urllib.parse.parse_qs(parsed.query)
                raw_url = qs.get("uddg", [raw_url])[0]

            if title and raw_url.startswith("http"):
                results.append({"title": title, "url": raw_url, "snippet": snippet})
                if len(results) >= max_results:
                    break

        return results

    @staticmethod
    def _decode_bing_redirect(href: str) -> str:
        """Bing оборачивает органические ссылки в редирект bing.com/ck/a?...&u=a1<base64>.
        Реальный URL — base64url без паддинга, с префиксом 'a1', внутри параметра u."""
        if "bing.com/ck/a" not in href:
            return href
        match = re.search(r"[?&]u=(a1[A-Za-z0-9_\-]+)", href)
        if not match:
            return href
        encoded = match.group(1)[2:]  # отрезаем маркер версии 'a1'
        padded = encoded + "=" * (-len(encoded) % 4)
        try:
            return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
        except Exception:
            return href

    def _parse_bing_results(self, html_body: str, max_results: int) -> list[dict[str, str]]:
        """Парсит органическую выдачу Bing (без JS, обычный HTML-скрейпинг).
        Каждый результат — <li class="b_algo">...<h2><a href=...>Заголовок</a></h2>...<p class="b_lineclampN">сниппет</p>...</li>."""
        results: list[dict[str, str]] = []
        blocks = re.split(r'(?=<li class="b_algo")', html_body)
        for block in blocks:
            if not block.startswith('<li class="b_algo"'):
                continue
            h2_match = re.search(r"<h2[^>]*>(.*?)</h2>", block, re.DOTALL)
            if not h2_match:
                continue
            link_match = re.search(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', h2_match.group(1), re.DOTALL)
            if not link_match:
                continue
            url = self._decode_bing_redirect(html.unescape(link_match.group(1)))
            title = _strip_html(link_match.group(2))
            snippet_match = re.search(r'<p class="b_lineclamp[^"]*"[^>]*>(.*?)</p>', block, re.DOTALL)
            snippet = _strip_html(snippet_match.group(1)) if snippet_match else ""

            if title and url.startswith("http"):
                results.append({"title": title, "url": url, "snippet": snippet})
                if len(results) >= max_results:
                    break

        return results
