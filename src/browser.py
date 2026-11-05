"""Browser management module for launching HiDPI Chrome instances."""

import sys
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from src.config import ExtractorConfig


def create_chrome_driver(config: ExtractorConfig) -> webdriver.Chrome:
    """Initialize and configure a Chrome WebDriver instance with HiDPI settings."""
    options = Options()

    # Resolution and HiDPI render options
    options.add_argument("--window-size=1920,1080")
    options.add_argument(f"--force-device-scale-factor={config.scale_factor}")
    options.add_argument(f"--high-dpi-support={config.scale_factor}")

    # Headless mode toggle
    if config.headless:
        options.add_argument("--headless=new")

    # Sandbox and performance flags
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-blink-features=AutomationControlled")

    # Anti-bot user-agent mask
    user_agent = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    )
    options.add_argument(f"--user-agent={user_agent}")

    # Support authenticated Chrome profile if provided
    if config.user_data_dir:
        options.add_argument(f"--user-data-dir={config.user_data_dir}")

    # Silent logging
    options.add_argument("--log-level=3")

    try:
        driver = webdriver.Chrome(options=options)
        return driver
    except Exception as exc:
        print(f"[ERROR] Failed to start Chrome WebDriver: {exc}", file=sys.stderr)
        raise
