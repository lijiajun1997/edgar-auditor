import re

from bs4 import BeautifulSoup
from markdownify import markdownify as md

SEC_HTML_CLEANUP = [
    (re.compile(r"\n{3,}"), "\n\n"),
    (re.compile(r"^\s+", re.MULTILINE), ""),
    (re.compile(r"[ \t]+$", re.MULTILINE), ""),
]


def convert_html_to_md(html_content: str) -> str:
    soup = BeautifulSoup(html_content, "lxml")

    for tag in soup(["script", "style", "link"]):
        tag.decompose()

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        md_lines: list[str] = []
        for i, row in enumerate(rows):
            cells = row.find_all(["td", "th"])
            line = "| " + " | ".join(c.get_text(strip=True) for c in cells) + " |"
            md_lines.append(line)
            if i == 0:
                md_lines.append("| " + " | ".join("---" for _ in cells) + " |")
        table.replace_with("\n".join(md_lines) + "\n")

    text: str = md(str(soup), heading_style="ATX", strip=["img"])

    for pattern, repl in SEC_HTML_CLEANUP:
        text = pattern.sub(repl, text)

    return text.strip() + "\n"
