"""Configuration and CLI argument parser for PDF/Slide extractor."""

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ExtractorConfig:
    """Holds configuration parameters for the extraction process."""

    url: str
    output_path: Path
    selector: str = "div.ndfHFb-c4YZDc-cYSp0e-DARUcf-PLDbbf"
    headless: bool = True
    scale_factor: int = 2
    settle_time: float = 1.0
    timeout: float = 30.0
    user_data_dir: Optional[str] = None
    clean_temp: bool = True
    temp_dir: Optional[Path] = None
    gui: bool = False
    ocr: bool = False
    ocr_output: Optional[Path] = None


def parse_args() -> Optional[ExtractorConfig]:
    """Parse command line arguments and return an ExtractorConfig instance or None if no url."""
    parser = argparse.ArgumentParser(
        description="Extract slides/PDF from Google Drive and web viewers with high resolution (HiDPI Canvas)."
    )
    parser.add_argument(
        "url",
        nargs="?",
        type=str,
        default=None,
        help="Target URL of the viewer (optional, interactive menu will open if omitted)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="output.pdf",
        help="Path to the output PDF file (default: output.pdf)",
    )
    parser.add_argument(
        "--selector",
        type=str,
        default="div.ndfHFb-c4YZDc-cYSp0e-DARUcf-PLDbbf",
        help="CSS selector for page element container in the viewer",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Disable headless mode to display the Chrome browser window",
    )
    parser.add_argument(
        "--scale",
        type=int,
        default=2,
        help="Device pixel scale factor for HiDPI rendering (default: 2)",
    )
    parser.add_argument(
        "--settle",
        type=float,
        default=1.0,
        help="Settle wait time in seconds for image decode per page (default: 1.0)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Timeout in seconds to wait for DOM elements to load (default: 30.0)",
    )
    parser.add_argument(
        "--user-data-dir",
        type=str,
        default=None,
        help="Path to Chrome profile directory for authenticated sessions",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep extracted temporary page PNG files instead of deleting them",
    )
    parser.add_argument(
        "--temp-dir",
        type=str,
        default=None,
        help="Custom directory to store temporary image files",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch the desktop graphical user interface (PyQt6 GUI)",
    )
    parser.add_argument(
        "--ocr",
        action="store_true",
        help="Run Pix2Text OCR on the resulting PDF pages to extract LaTeX math & text",
    )
    parser.add_argument(
        "--ocr-output",
        type=str,
        default=None,
        help="Directory to save OCR markdown and page results",
    )

    args = parser.parse_args()

    if args.gui:
        return ExtractorConfig(
            url="",
            output_path=Path("output.pdf").resolve(),
            gui=True,
        )

    if not args.url:
        return None

    output_path = Path(args.output).resolve()
    temp_dir = Path(args.temp_dir).resolve() if args.temp_dir else output_path.parent / ".temp_pages"
    ocr_out = Path(args.ocr_output).resolve() if args.ocr_output else None

    return ExtractorConfig(
        url=args.url,
        output_path=output_path,
        selector=args.selector,
        headless=not args.no_headless,
        scale_factor=args.scale,
        settle_time=args.settle,
        timeout=args.timeout,
        user_data_dir=args.user_data_dir,
        clean_temp=not args.keep_temp,
        temp_dir=temp_dir,
        ocr=args.ocr,
        ocr_output=ocr_out,
    )
