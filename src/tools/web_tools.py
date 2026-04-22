from __future__ import annotations

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
        """Поиск в интернете через DuckDuckGo (без API-ключа). Возвращает список результатов."""
        query = str(args.get("query", "")).strip()
        if not query:
            raise ToolExecutionError("Параметр query не может быть пустым")
        max_results = min(int(str(args.get("max_results", 10))), 20)

        encoded = urllib.parse.urlencode({"q": query, "kl": "ru-ru"})
        candidates = [
            f"https://html.duckduckgo.com/html/?{encoded}",
            f"https://duckduckgo.com/html/?{encoded}",
        ]

        last_error: str = ""
        for attempt_url in candidates:
            try:
                _, raw = _fetch_raw(attempt_url, timeout=25)
                results = self._parse_ddg_results(raw, max_results)
                return {
                    "query": query,
                    "count": len(results),
                    "results": results,
                }
            except ToolExecutionError as e:
                last_error = str(e)
                continue

        raise ToolExecutionError(f"Веб-поиск недоступен: {last_error}. Попробуй fetch_url напрямую или уточни запрос.")

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
