"""Small HWPX text extractor.

HWPX files are ZIP archives that contain XML sections. The extractor keeps a
light footprint so GitHub Actions can read Korean press-release attachments
without a heavyweight office document dependency.
"""
from __future__ import annotations

import io
import re
import zipfile
from html import unescape
from xml.etree import ElementTree


def clean_hwpx_text(value: str) -> str:
    value = unescape(value or "")
    value = re.sub(r"\r", "\n", value)
    value = re.sub(r"\u00a0", " ", value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n[ \t]+", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _section_sort_key(name: str) -> tuple[int, str]:
    match = re.search(r"section(\d+)\.xml$", name)
    if match:
        return int(match.group(1)), name
    return 9999, name


def _paragraph_text(xml_text: str) -> list[str]:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        parts = re.findall(r"<hp:t[^>]*>(.*?)</hp:t>", xml_text, flags=re.DOTALL)
        return [clean_hwpx_text(re.sub(r"<[^>]+>", " ", part)) for part in parts]

    paragraphs: list[str] = []
    for elem in root.iter():
        if not elem.tag.endswith("}p") and not elem.tag.endswith(":p") and elem.tag != "p":
            continue
        chunks: list[str] = []
        for child in elem.iter():
            tag = child.tag.rsplit("}", 1)[-1].rsplit(":", 1)[-1]
            if tag == "t" and child.text:
                chunks.append(child.text)
        paragraph = clean_hwpx_text("".join(chunks))
        if paragraph:
            paragraphs.append(paragraph)
    return paragraphs


def extract_hwpx_text_bytes(data: bytes) -> str:
    if data[:2] != b"PK":
        return ""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return extract_hwpx_text_zip(zf)
    except zipfile.BadZipFile:
        return ""


def extract_hwpx_text_zip(zf: zipfile.ZipFile) -> str:
    names = zf.namelist()
    preview_names = [
        name for name in ("Preview/PrvText.txt", "preview/PrvText.txt") if name in names
    ]
    for name in preview_names:
        raw = zf.read(name).decode("utf-8", errors="replace")
        text = clean_hwpx_text(re.sub(r"<[^>]*>", " ", raw))
        if len(text) > 300:
            return text

    section_names = sorted(
        [name for name in names if re.match(r"Contents/section\d+\.xml$", name)],
        key=_section_sort_key,
    )
    paragraphs: list[str] = []
    for name in section_names:
        xml_text = zf.read(name).decode("utf-8", errors="replace")
        paragraphs.extend(_paragraph_text(xml_text))

    return clean_hwpx_text("\n".join(paragraphs))
