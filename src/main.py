import sys
import time
from pathlib import Path
from typing import List

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.browser import create_chrome_driver
from src.config import ExtractorConfig, parse_args
from src.extractor import extract_page_image, preload_all_pages, wait_for_dom_stability
from src.menu import run_interactive_menu
from src.pdf_assembler import assemble_pdf, cleanup_temp_dir


def run_pipeline(config: ExtractorConfig) -> Path:
    """Execute the full extraction and assembly pipeline."""
    temp_dir = config.temp_dir or (config.output_path.parent / ".temp_pages")
    temp_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("🚀 Google Drive / Slide Viewer PDF Extractor")
    print(f"Target URL:  {config.url}")
    print(f"Output PDF:  {config.output_path}")
    print(f"HiDPI Scale: {config.scale_factor}x")
    print(f"Headless:    {config.headless}")
    print("=" * 60)

    driver = create_chrome_driver(config)
    image_paths: List[Path] = []

    try:
        print("[INFO] Navigating to target URL...")
        driver.get(config.url)

        # 1. Wait for page elements to render and stabilize
        pages = wait_for_dom_stability(
            driver=driver,
            primary_selector=config.selector,
            timeout=config.timeout,
        )

        total_pages = len(pages)
        print(f"[INFO] Detected {total_pages} pages in document.")

        # 2. Scroll through all pages to trigger lazy-load
        preload_all_pages(driver=driver, pages=pages)

        # 3. Extract each page
        print(f"[INFO] Extracting {total_pages} pages (lossless Canvas with Fallback)...")
        for i, page in enumerate(pages, start=1):
            img_path = extract_page_image(
                driver=driver,
                page=page,
                page_num=i,
                temp_dir=temp_dir,
                settle_time=config.settle_time,
            )
            image_paths.append(img_path)
            print(f"  [✓] Page {i:03d}/{total_pages:03d} -> {img_path.name}")

        # 4. Assemble PNG images into single PDF
        pdf_path = assemble_pdf(image_paths=image_paths, output_pdf=config.output_path)

        # 5. Optional: Run OCR & Convert to Formatted Thesis PDF
        if config.ocr:
            print("\n[INFO] Đang chạy OCR Tiếng Việt & Ký hiệu khoa học...")
            from src.ocr_engine import DocumentOcrEngine
            ocr_engine = DocumentOcrEngine(languages=["vi", "en"])
            md_doc = ocr_engine.ocr_pdf(pdf_path=pdf_path, output_dir=config.ocr_output)

            print("\n[INFO] Đang tự động định dạng và xuất file PDF chuẩn luận văn...")
            from src.md_to_pdf import markdown_to_pdf
            formatted_pdf = markdown_to_pdf(md_doc)
            print(f"[✓] Đã tạo PDF luận văn chuẩn: {formatted_pdf}")

        # 6. Clean up temporary directory if enabled
        if config.clean_temp:
            cleanup_temp_dir(temp_dir)
        else:
            print(f"[INFO] Temporary images preserved in: {temp_dir}")

        return pdf_path
    finally:
        driver.quit()
        print("[INFO] Closed browser instance.")


def main() -> None:
    """CLI execution entrypoint."""
    try:
        config = parse_args()
        if config and config.gui:
            from src.gui import launch_gui
            launch_gui()
            sys.exit(0)

        if not config:
            config = run_interactive_menu()
            if not config:
                sys.exit(0)

        start = time.time()
        output_file = run_pipeline(config)
        elapsed = time.time() - start
        print(f"\n🎉 Done in {elapsed:.1f}s! Saved to: {output_file}")
    except KeyboardInterrupt:
        print("\n[INFO] Process interrupted by user.", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(f"\n[ERROR] Extraction failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
