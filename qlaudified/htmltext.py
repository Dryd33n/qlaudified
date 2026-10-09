"""Main text of an HTML page for the re-fetch (CAP-3): reading-order blocks, no navigation."""

from html.parser import HTMLParser

MAX_PARAGRAPHS = 200

SKIP = {"script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg", "button",
        "template", "iframe", "select"}
BLOCKS = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "td", "th", "pre", "blockquote", "dd",
          "dt", "figcaption", "caption", "div", "section", "article", "main", "tr", "br"}
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
VOID = {"br", "img", "hr", "input", "meta", "link", "source", "wbr", "area", "col", "embed"}


class _MainText(HTMLParser):
    """Text blocks in reading order, skipping navigation and scripts; ``<main>`` or ``<article>``
    content only, when the page has either."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str, bool]] = []  # (text, inside main/article)
        self.skip_depth = 0
        self.main_depth = 0
        self.saw_main = False
        self.current: list[str] = []
        self.title = ""
        self._in_title = False

    def _flush(self) -> None:
        text = " ".join("".join(self.current).split())
        if text:
            self.blocks.append((text, self.main_depth > 0))
        self.current = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "title":
            self._in_title = True
        if tag in SKIP and tag not in VOID:
            self.skip_depth += 1
        if tag in ("main", "article"):
            self.main_depth += 1
            self.saw_main = True
        if tag in BLOCKS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in BLOCKS:
            self._flush()
        if tag in SKIP and self.skip_depth:
            self.skip_depth -= 1
        if tag in ("main", "article") and self.main_depth:
            self.main_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif not self.skip_depth:
            self.current.append(data)


def main_text(html: str) -> list[str]:
    """The page's paragraphs: main/article content if present, short fragments dropped."""
    parser = _MainText()
    parser.feed(html)
    parser.close()
    parser._flush()
    blocks = [t for t, in_main in parser.blocks if in_main or not parser.saw_main]
    out = []
    for block in blocks:
        if len(block) >= 25 or block.endswith((".", "!", "?", ":")):
            out.append(block)
    return list(dict.fromkeys(out))[:MAX_PARAGRAPHS]
