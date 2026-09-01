"""Regression checks for public project documentation."""

from __future__ import annotations

import re
import struct
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_MARKDOWN = [
    ROOT / "README.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "SECURITY.md",
    *sorted((ROOT / "docs").rglob("*.md")),
]
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
HTML_ASSET = re.compile(r"<(?:img|a)\b[^>]+(?:src|href)=[\"']([^\"']+)[\"']", re.I)
SCREENSHOTS = (
    "dashboard.jpg",
    "manual-entry.jpg",
    "targets.jpg",
    "analytics.jpg",
    "login.jpg",
    "api-documentation.jpg",
)


def local_targets(document: Path) -> list[Path]:
    """Return local files referenced by Markdown or inline HTML."""
    content = document.read_text(encoding="utf-8")
    raw_links = MARKDOWN_LINK.findall(content) + HTML_ASSET.findall(content)
    targets: list[Path] = []

    for raw_link in raw_links:
        link = raw_link.strip().strip("<>")
        parsed = urlsplit(link)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        targets.append((document.parent / unquote(parsed.path)).resolve())

    return targets


def jpeg_dimensions(data: bytes) -> tuple[int, int]:
    """Read JPEG width and height without adding an imaging dependency."""
    start_of_frame = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    offset = 2

    while offset + 9 <= len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue

        marker = data[offset + 1]
        offset += 2
        if marker in {0xD8, 0xD9}:
            continue

        segment_length = struct.unpack(">H", data[offset : offset + 2])[0]
        if marker in start_of_frame:
            height, width = struct.unpack(">HH", data[offset + 3 : offset + 7])
            return width, height
        offset += segment_length

    raise ValueError("JPEG start-of-frame marker not found")


class DocumentationTests(unittest.TestCase):
    def test_public_document_links_resolve(self) -> None:
        missing: list[str] = []
        for document in PUBLIC_MARKDOWN:
            for target in local_targets(document):
                if not target.exists():
                    missing.append(f"{document.relative_to(ROOT)} -> {target}")

        self.assertFalse(missing, "Broken documentation links:\n" + "\n".join(missing))

    def test_product_screenshots_are_valid_high_resolution_jpegs(self) -> None:
        image_dir = ROOT / "docs" / "images"
        for filename in SCREENSHOTS:
            with self.subTest(filename=filename):
                data = (image_dir / filename).read_bytes()
                self.assertEqual(data[:2], b"\xff\xd8")
                width, height = jpeg_dimensions(data)
                self.assertGreaterEqual(width, 1200)
                self.assertGreaterEqual(height, 675)


if __name__ == "__main__":
    unittest.main()
