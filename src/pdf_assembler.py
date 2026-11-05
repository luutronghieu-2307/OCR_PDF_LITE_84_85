"""PDF assembly module using Pillow."""

import shutil
from pathlib import Path
from typing import List
from PIL import Image


def assemble_pdf(image_paths: List[Path], output_pdf: Path) -> Path:
    """Compile ordered list of PNG images into a single PDF document."""
    if not image_paths:
        raise ValueError("Cannot assemble PDF: image_paths list is empty.")

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    opened_images: List[Image.Image] = []

    try:
        print(f"[INFO] Compiling {len(image_paths)} pages into PDF: {output_pdf}")
        for path in image_paths:
            img = Image.open(path)
            # Ensure RGB color mode (prevents palette/alpha issues when saving as PDF)
            if img.mode in ("RGBA", "P"):
                rgb_img = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "RGBA":
                    rgb_img.paste(img, mask=img.split()[3])
                else:
                    rgb_img.paste(img.convert("RGB"))
                opened_images.append(rgb_img)
                img.close()
            else:
                opened_images.append(img.convert("RGB"))

        # Save first image with all subsequent images appended
        opened_images[0].save(
            str(output_pdf),
            "PDF",
            save_all=True,
            append_images=opened_images[1:],
            resolution=100.0,
        )
        print(f"[SUCCESS] PDF generated successfully: {output_pdf} ({output_pdf.stat().st_size} bytes)")
        return output_pdf
    finally:
        for img in opened_images:
            try:
                img.close()
            except Exception:
                pass


def cleanup_temp_dir(temp_dir: Path) -> None:
    """Remove temporary page images and scratch directory."""
    if temp_dir.exists():
        try:
            shutil.rmtree(temp_dir)
            print(f"[INFO] Cleaned temporary directory: {temp_dir}")
        except Exception as exc:
            print(f"[WARN] Failed to delete temp directory {temp_dir}: {exc}")
