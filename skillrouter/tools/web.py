"""Web search + page fetch. Gives local models access to live information
by pulling text before the prompt goes to the model."""
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser


USER_AGENT = "Mozilla/5.0 (compatible; skillrouter/0.3)"
TIMEOUT = 10
MAX_PAGE_CHARS = 4000
MAX_TOTAL_CHARS = 12000


def _http_get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


class _TextExtractor(HTMLParser):
    SKIP_TAGS = {"script", "style", "noscript", "svg", "header", "footer", "nav", "form"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS and self.skip_depth > 0:
            self.skip_depth -= 1

    def handle_data(self, data):
        if self.skip_depth == 0:
            s = data.strip()
            if s:
                self.parts.append(s)


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    text = " ".join(parser.parts)
    return re.sub(r"\s+", " ", text).strip()


def search(query: str, n: int = 3) -> list[dict]:
    """DuckDuckGo HTML search. Returns [{title, url, snippet}]."""
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    try:
        html = _http_get(url)
    except Exception as e:
        return [{"title": "search error", "url": "", "snippet": str(e)}]

    results = []
    pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>'
        r'.*?<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    for match in pattern.finditer(html):
        raw_url, title_html, snippet_html = match.groups()

        if raw_url.startswith("//duckduckgo.com/l/"):
            parsed = urllib.parse.urlparse("https:" + raw_url)
            params = urllib.parse.parse_qs(parsed.query)
            uddg = params.get("uddg", [""])[0]
            if uddg:
                raw_url = urllib.parse.unquote(uddg)

        results.append({
            "title": re.sub(r"<[^>]+>", "", title_html).strip(),
            "url": raw_url,
            "snippet": re.sub(r"<[^>]+>", "", snippet_html).strip(),
        })
        if len(results) >= n:
            break
    return results


def fetch(url: str, max_chars: int = MAX_PAGE_CHARS) -> str:
    try:
        html = _http_get(url)
    except Exception as e:
        return f"[fetch error: {e}]"
    text = _html_to_text(html)
    if len(text) > max_chars:
        text = text[:max_chars] + "..."
    return text


def search_and_fetch(query: str, n: int = 3) -> str:
    """Search + fetch top results. Returns formatted context block for prompt injection."""
    results = search(query, n=n)
    if not results:
        return f"[no web results for: {query}]"

    blocks = [f"WEB SEARCH RESULTS FOR: {query}\n"]
    total = 0
    for i, r in enumerate(results, 1):
        blocks.append(f"\n[{i}] {r['title']}\n{r['url']}\n{r['snippet']}")
        if r["url"] and r["url"].startswith("http"):
            page = fetch(r["url"])
            blocks.append(f"--- page excerpt ---\n{page}")
        total = sum(len(b) for b in blocks)
        if total > MAX_TOTAL_CHARS:
            blocks.append("\n[truncated]")
            break
    return "\n".join(blocks)
