"""DOM stability waiting, preloading, and high-res image extraction logic."""

import base64
import time
from pathlib import Path
from typing import List, Optional
from selenium import webdriver
from selenium.webdriver.remote.webelement import WebElement


FALLBACK_SELECTORS = [
    "div.ndfHFb-c4YZDc-cYSp0e-DARUcf-PLDbbf",
    "div.drive-viewer-page",
    "div[role='region'][aria-label*='Page']",
    "div[data-page-number]",
]


def wait_for_dom_stability(
    driver: webdriver.Chrome,
    primary_selector: str,
    timeout: float = 30.0,
) -> List[WebElement]:
    """Wait for page containers to appear and page count to stabilize for at least 0.5s."""
    start_time = time.monotonic()
    last_count = -1
    stable_since = start_time
    candidate_selectors = [primary_selector] + [
        s for s in FALLBACK_SELECTORS if s != primary_selector
    ]

    active_selector = primary_selector

    while time.monotonic() - start_time < timeout:
        pages: List[WebElement] = []
        for selector in candidate_selectors:
            elements = driver.find_elements("css selector", selector)
            if elements:
                pages = elements
                active_selector = selector
                break

        current_count = len(pages)
        now = time.monotonic()

        if current_count != last_count:
            last_count = current_count
            stable_since = now
        elif current_count > 0 and (now - stable_since >= 0.5):
            print(f"[INFO] Found {current_count} pages using selector: {active_selector}")
            return pages

        time.sleep(0.2)

    if last_count > 0:
        print(f"[WARN] Stabilize timeout reached. Proceeding with {last_count} detected pages.")
        return driver.find_elements("css selector", active_selector)

    raise TimeoutError(
        f"Unable to detect slide/PDF pages within {timeout}s using selectors: {candidate_selectors}"
    )


def preload_all_pages(driver: webdriver.Chrome, pages: List[WebElement]) -> None:
    """Scroll through all pages sequentially to trigger lazy loading of image assets."""
    total = len(pages)
    print(f"[INFO] Preloading {total} pages to trigger lazy-load...")

    for idx, page in enumerate(pages, start=1):
        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});",
                page,
            )
            # Brief polling for image complete
            driver.execute_script(
                """
                const parent = arguments[0].parentElement || arguments[0];
                return Array.from(parent.querySelectorAll('img'))
                    .every((img) => img.complete && img.naturalWidth > 0);
                """,
                page,
            )
            if idx % 10 == 0 or idx == total:
                print(f"[INFO] Preloaded {idx}/{total} pages")
        except Exception as exc:
            print(f"[WARN] Could not preload page {idx}: {exc}")

    # Reset view to the top/first page
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'start', behavior: 'instant'});",
            pages[0],
        )
        time.sleep(0.5)
    except Exception:
        pass


def extract_page_image(
    driver: webdriver.Chrome,
    page: WebElement,
    page_num: int,
    temp_dir: Path,
    settle_time: float = 1.0,
) -> Path:
    """Extract page image via HTML5 Canvas (lossless naturalWidth/Height) or fallback screenshot."""
    img_path = temp_dir / f"page_{page_num:04d}.png"

    # Scroll page into center
    driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});",
        page,
    )
    if settle_time > 0:
        time.sleep(settle_time)

    # Attempt Canvas extraction
    js_extract = """
        const page = arguments[0];
        const parent = page.parentElement || page;
        const img = parent.querySelector('img') || page.querySelector('img');
        if (!img || !img.complete || img.naturalWidth <= 0) return null;

        try {
            const canvas = document.createElement('canvas');
            canvas.width = img.naturalWidth;
            canvas.height = img.naturalHeight;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(img, 0, 0);
            return canvas.toDataURL('image/png');
        } catch (err) {
            // Likely canvas tainted by CORS
            return null;
        }
    """

    data_url: Optional[str] = None
    try:
        data_url = driver.execute_script(js_extract, page)
    except Exception:
        data_url = None

    if data_url and "," in data_url:
        try:
            base64_data = data_url.split(",", 1)[1]
            img_path.write_bytes(base64.b64decode(base64_data))
        except Exception:
            data_url = None

    # Fallback to element screenshot if Canvas method returned null or failed
    if not data_url or not img_path.exists() or img_path.stat().st_size == 0:
        page.screenshot(str(img_path))

    if not img_path.exists() or img_path.stat().st_size == 0:
        raise RuntimeError(f"Failed to capture valid image for page {page_num}")

    return img_path
