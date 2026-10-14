import base64
import io

import pytest
from PIL import Image

from perception.dom_parser import extract_interactive_elements
from perception.screenshot import capture_annotated_screenshot, save_screenshot


@pytest.mark.asyncio
async def test_capture_annotated_screenshot_returns_valid_base64_png(browser_page, static_server):
    # Arrange
    await browser_page.goto(f"{static_server}/sample_page.html")
    elements = await extract_interactive_elements(browser_page)

    # Act
    b64 = await capture_annotated_screenshot(browser_page, elements)

    # Assert
    raw = base64.b64decode(b64)
    img = Image.open(io.BytesIO(raw))
    assert img.format == "PNG"
    assert img.width > 0 and img.height > 0


@pytest.mark.asyncio
async def test_save_screenshot_writes_png_file(browser_page, static_server, tmp_path):
    # Arrange
    await browser_page.goto(f"{static_server}/sample_page.html")
    elements = await extract_interactive_elements(browser_page)
    b64 = await capture_annotated_screenshot(browser_page, elements)
    out_path = tmp_path / "step_0.png"

    # Act
    save_screenshot(b64, str(out_path))

    # Assert
    assert out_path.exists()
    assert out_path.stat().st_size > 0


@pytest.mark.asyncio
async def test_capture_annotated_screenshot_matches_real_viewport_size(browser_page, static_server):
    # Arrange: browser_page uses a 1280x800 viewport (see conftest.py).
    await browser_page.goto(f"{static_server}/sample_page.html")
    elements = await extract_interactive_elements(browser_page)

    # Act
    b64 = await capture_annotated_screenshot(browser_page, elements)

    # Assert: a real capture, not a placeholder canvas.
    img = Image.open(io.BytesIO(base64.b64decode(b64)))
    assert (img.width, img.height) == (1280, 800)
