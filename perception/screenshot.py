"""Annotated screenshot capture for the perception layer.

Takes a page screenshot and draws numbered bounding boxes around the
interactive elements found by `perception.dom_parser`, so the reasoning
layer can visually ground its decisions against the same element ids used
in the text-based state representation.
"""

import base64
import io

from PIL import Image, ImageDraw, ImageFont
from playwright.async_api import Page

from agent.types import Element

_BOX_COLORS = ["red", "blue", "green", "orange", "purple"]
_BOX_OUTLINE_WIDTH = 2
_LABEL_Y_OFFSET = 10


async def capture_annotated_screenshot(page: Page, elements: list[Element]) -> str:
    """Capture the current viewport and overlay numbered boxes on `elements`.

    Each element with a valid (non-empty) bbox gets a colored rectangle and
    its `id` drawn as a label, cycling through `_BOX_COLORS`. Elements with
    no bbox or a zero/negative width or height are skipped.

    Returns the annotated screenshot as a base64-encoded PNG string.
    """
    raw_png = await page.screenshot(full_page=False)
    image = Image.open(io.BytesIO(raw_png)).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()

    for i, el in enumerate(elements):
        bbox = el.bbox
        if not bbox:
            continue
        x, y = bbox.get("x", 0), bbox.get("y", 0)
        width, height = bbox.get("width", 0), bbox.get("height", 0)
        if width <= 0 or height <= 0:
            continue

        color = _BOX_COLORS[i % len(_BOX_COLORS)]
        draw.rectangle(
            [x, y, x + width, y + height], outline=color, width=_BOX_OUTLINE_WIDTH
        )
        draw.text((x, max(0, y - _LABEL_Y_OFFSET)), el.id, fill=color, font=font)

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def save_screenshot(b64: str, path: str) -> None:
    """Decode a base64 PNG string and write it to `path`."""
    raw = base64.b64decode(b64)
    with open(path, "wb") as f:
        f.write(raw)


if __name__ == "__main__":
    import asyncio

    from playwright.async_api import async_playwright

    from perception.dom_parser import extract_interactive_elements

    async def _demo():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto("https://example.com")
            els = await extract_interactive_elements(page)
            b64 = await capture_annotated_screenshot(page, els)
            save_screenshot(b64, "/tmp/demo_screenshot.png")
            await browser.close()

    asyncio.run(_demo())
