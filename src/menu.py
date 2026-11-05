"""Interactive terminal menu for user-friendly extraction configuration."""

import sys
from pathlib import Path
from typing import Optional
from src.config import ExtractorConfig


def prompt_text(prompt: str, default: str = "") -> str:
    """Prompt user for input with an optional default value."""
    if default:
        raw = input(f"{prompt} [{default}]: ").strip()
        return raw if raw else default
    while True:
        raw = input(f"{prompt}: ").strip()
        if raw:
            return raw
        print("[!] Không được để trống. Vui lòng nhập lại.")


def run_interactive_menu() -> Optional[ExtractorConfig]:
    """Display interactive menu and return an ExtractorConfig instance or None to exit."""
    print("\n" + "=" * 60)
    print("      📄 CÔNG CỤ TRÍCH XUẤT SLIDE / PDF GOOGLE DRIVE")
    print("=" * 60)
    print(" [1] ⚡ Trích xuất PDF từ URL (Nhanh, Chạy ngầm Headless)")
    print(" [2] 🖥️  Trích xuất PDF + Mở cửa sổ Chrome trực quan")
    print(" [3] 🔑 Trích xuất tài liệu riêng tư (Profile Chrome cá nhân)")
    print(" [4] 🧪 Chạy thử nghiệm Demo nội bộ (Sample demo)")
    print(" [5] 🎨 Khởi chạy Giao diện đồ họa (PyQt6 GUI)")
    print(" [6] 🔬 OCR PDF sang Markdown (Tiếng Việt + Ký hiệu khoa học)")
    print(" [7] 📑 Chuyển Markdown sang PDF chuẩn thể thức Luận văn")
    print(" [0] ❌ Thoát")
    print("=" * 60)

    while True:
        choice = input("👉 Nhập lựa chọn của bạn [0-7]: ").strip()
        if choice in ("0", "1", "2", "3", "4", "5", "6", "7"):
            break
        print("[!] Lựa chọn không hợp lệ, vui lòng chọn từ 0 đến 7.")

    if choice == "0":
        print("Tạm biệt!")
        return None

    if choice == "5":
        from src.gui import launch_gui
        launch_gui()
        return None

    project_root = Path(__file__).resolve().parent.parent

    # Option 6: OCR PDF to Markdown
    if choice == "6":
        pdf_input = prompt_text("Nhập đường dẫn file PDF cần OCR", "p1")
        pdf_path = Path(pdf_input).resolve()
        from src.ocr_engine import DocumentOcrEngine
        engine = DocumentOcrEngine(languages=["vi", "en"])
        engine.ocr_pdf(pdf_path=pdf_path)
        sys.exit(0)

    # Option 7: Convert Markdown to Formatted PDF
    if choice == "7":
        md_input = prompt_text("Nhập đường dẫn file Markdown", "p1_ocr_result/full_document.md")
        md_path = Path(md_input).resolve()
        from src.md_to_pdf import markdown_to_pdf
        out_pdf = markdown_to_pdf(md_path)
        print(f"🎉 Hoàn tất! File PDF định dạng luận văn đã lưu tại: {out_pdf}")
        sys.exit(0)

    # Option 4: Internal demo sample
    if choice == "4":
        sample_path = project_root / "test" / "sample_demo.html"
        url = f"file://{sample_path.resolve()}"
        out_name = prompt_text("Tên file PDF xuất ra", "demo_output.pdf")
        return ExtractorConfig(
            url=url,
            output_path=project_root / out_name,
            headless=True,
            scale_factor=2,
            settle_time=0.5,
        )

    # Option 1, 2, 3: Need user URL
    url = prompt_text("🔗 Nhập URL của Google Drive hoặc Web Viewer")
    out_name = prompt_text("📁 Tên file PDF lưu kết quả", "output.pdf")
    output_path = Path(out_name).resolve()

    user_data_dir: Optional[str] = None
    headless = True

    if choice == "2":
        headless = False
    elif choice == "3":
        default_profile = str(Path.home() / ".config" / "google-chrome")
        user_data_dir = prompt_text(
            "Đường dẫn thư mục Chrome Profile", default_profile
        )

    return ExtractorConfig(
        url=url,
        output_path=output_path,
        headless=headless,
        scale_factor=2,
        settle_time=1.0,
        user_data_dir=user_data_dir,
        ocr=True,
    )
