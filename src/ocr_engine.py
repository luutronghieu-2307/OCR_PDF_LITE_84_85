"""High-Accuracy Document OCR Engine.
Optimized for Vietnamese & English academic / scientific documents,
formulas, scientific notations, temperatures (°C), concentrations, and units (µl, µg).
"""

import os
import re
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional, Union

import cv2
import numpy as np

# Suppress PyTorch & tokenizers noise
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

try:
    import pymupdf  # PyMuPDF
except ImportError:
    import fitz as pymupdf

import easyocr


class DocumentOcrEngine:
    """Document OCR Engine with specialized support for Vietnamese diacritics
    and scientific / mathematical symbols.
    """

    def __init__(
        self,
        languages: Optional[List[str]] = None,
        gpu: bool = False,
    ) -> None:
        if languages is None:
            languages = ["vi", "en"]

        self.languages = languages
        self.gpu = gpu

        print(f"[OCR] Initializing Vietnamese Scientific OCR Model (Languages: {languages}, GPU: {gpu})...")
        self.reader = easyocr.Reader(self.languages, gpu=self.gpu)
        from src.search_refiner import SearchAugmentedRefiner
        self.refiner = SearchAugmentedRefiner(enable_web=True)
        print("[OCR] Model loaded successfully.")

    def normalize_scientific_text(
        self,
        text: str,
        crop_img: Optional[np.ndarray] = None,
        initial_conf: Optional[float] = None,
    ) -> str:
        """Apply Search-Augmented & Visual Hypothesis Refinement without hardcoded regex rules."""
        if not text:
            return ""

        text = self.refiner.refine_text(text, crop_img=crop_img, initial_conf=initial_conf)
        text = re.sub(r"[ ]{2,}", " ", text)
        return text.strip()

    @staticmethod
    def crop_margin_with_inversion(image: np.ndarray, padding_ratio: float = 0.10) -> np.ndarray:
        """Cut excessive margin padding using OpenCV:
        1. Invert colors: Black (text) -> White, White (background) -> Black.
        2. Detect bounding box of foreground text.
        3. Add 10% of text block height to all 4 sides to avoid clipping edge characters.
        """
        if image is None or image.size == 0:
            return image

        h, w = image.shape[:2]
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()

        # Step 1: Invert colors (White background -> 0, Black text -> 255)
        inverted = cv2.bitwise_not(gray)

        # Threshold to isolate clear text strokes
        _, thresh = cv2.threshold(inverted, 35, 255, cv2.THRESH_BINARY)

        # Step 2: Find text bounding box
        pts = cv2.findNonZero(thresh)
        if pts is None:
            return image

        bx, by, bw, bh = cv2.boundingRect(pts)

        # Check if detected box is meaningful (avoid tiny artifacts)
        if bw < w * 0.15 or bh < h * 0.15:
            return image

        # Step 3: Add 10% of text block height to all 4 sides
        pad = int(padding_ratio * bh)
        x1 = max(0, bx - pad)
        y1 = max(0, by - pad)
        x2 = min(w, bx + bw + pad)
        y2 = min(h, by + bh + pad)

        return image[y1:y2, x1:x2]

    def ocr_page(self, image_data: Union[str, Path, bytes, np.ndarray]) -> str:
        """Run OCR on a page image and return clean paragraph-formatted markdown.
        Uses OpenCV color inversion & 10% padding margin cropping at Step 1,
        followed by EasyOCR native paragraph grouping to preserve sentence cohesion.
        """
        if isinstance(image_data, (str, Path)):
            img_input = cv2.imread(str(image_data))
        elif isinstance(image_data, bytes):
            nparr = np.frombuffer(image_data, np.uint8)
            img_input = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        else:
            img_input = image_data

        if img_input is None:
            return ""

        # Step 1: OpenCV Preprocessing - Invert colors & auto-crop margins with 10% padding
        img_cropped = self.crop_margin_with_inversion(img_input, padding_ratio=0.10)

        # Step 2: Use paragraph mode to guarantee natural reading order and 100% sentence integrity
        raw_paragraphs = self.reader.readtext(img_cropped, detail=0, paragraph=True)

        cleaned_paragraphs = []
        for para in raw_paragraphs:
            cleaned = self.normalize_scientific_text(para)
            if cleaned:
                # Format section headers nicely in Markdown based on structural numbering/casing
                if re.match(r"^\d+\.\d+", cleaned):
                    cleaned_paragraphs.append(f"\n### {cleaned}\n")
                elif cleaned.isupper() and len(cleaned) < 60:
                    cleaned_paragraphs.append(f"\n## {cleaned}\n")
                else:
                    cleaned_paragraphs.append(cleaned)

        result_text = "\n\n".join(cleaned_paragraphs)
        result_text = re.sub(r"\n{3,}", "\n\n", result_text)
        return result_text.strip()

    def ocr_pdf(
        self,
        pdf_path: Union[str, Path],
        output_dir: Optional[Union[str, Path]] = None,
        page_numbers: Optional[List[int]] = None,
        dpi: int = 200,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Path:
        """Process all pages of the given PDF and output Markdown results."""
        pdf_path = Path(pdf_path).resolve()
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file does not exist: {pdf_path}")

        if output_dir is None:
            output_dir = pdf_path.parent / f"{pdf_path.stem}_ocr_result"
        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        pages_dir = output_dir / "pages"
        pages_dir.mkdir(exist_ok=True)

        doc = pymupdf.open(str(pdf_path))
        total_doc_pages = len(doc)
        target_pages = page_numbers if page_numbers is not None else list(range(total_doc_pages))
        total_tasks = len(target_pages)

        print("=" * 60)
        print("📖 OCR TÀI LIỆU TIẾNG VIỆT & KÝ HIỆU KHOA HỌC")
        print(f"File PDF:        {pdf_path.name} ({total_doc_pages} trang)")
        print(f"Số trang xử lý:  {total_tasks} trang")
        print(f"Thư mục kết quả: {output_dir}")
        print("=" * 60)

        all_page_texts: List[str] = []
        start_time = time.time()

        for idx, page_num in enumerate(target_pages, start=1):
            page_label = page_num + 1
            print(f"[{idx:02d}/{total_tasks:02d}] 🔍 Đang OCR Trang {page_label}...")

            page = doc[page_num]
            # Fast & lossless extraction: if page is a scanned image, use raw image
            page_images = page.get_images()
            if page_images:
                xref = page_images[0][0]
                img_data = doc.extract_image(xref)["image"]
            else:
                pix = page.get_pixmap(dpi=dpi)
                img_data = pix.tobytes("png")

            # OCR process
            page_md = self.ocr_page(img_data)

            # Save individual page markdown
            page_file = pages_dir / f"page_{page_label:03d}.md"
            page_file.write_text(f"# TRANG {page_label}\n\n{page_md}\n", encoding="utf-8")

            all_page_texts.append(f"<!-- Page {page_label} -->\n\n## Trang {page_label}\n\n{page_md}\n")

            if progress_callback:
                progress_callback(idx, total_tasks, page_md[:120])

            print(f"  [✓] Hoàn thành trang {page_label} -> {page_file.name}")

        # Save consolidated markdown
        consolidated_file = output_dir / "full_document.md"
        consolidated_content = (
            f"# KẾT QUẢ OCR TÀI LIỆU: {pdf_path.stem}\n"
            f"> Trích xuất chuẩn Tiếng Việt & Ký hiệu khoa học (Đơn vị, nhiệt độ, nồng độ, số mũ)\n\n"
            f"---\n\n"
            + "\n\n---\n\n".join(all_page_texts)
        )
        consolidated_file.write_text(consolidated_content, encoding="utf-8")

        elapsed = time.time() - start_time
        print("=" * 60)
        print(f"🎉 HOÀN TẤT OCR {total_tasks} TRANG TRONG {elapsed:.1f}s!")
        print(f"📁 Tệp tổng hợp: {consolidated_file}")
        print("=" * 60)

        return consolidated_file
