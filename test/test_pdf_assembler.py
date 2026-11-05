"""Unit tests for PDF assembly and image conversion."""

import unittest
from pathlib import Path
from PIL import Image

from src.pdf_assembler import assemble_pdf, cleanup_temp_dir


class TestPdfAssembler(unittest.TestCase):
    """Test suite for PDF generation from extracted images."""

    def setUp(self) -> None:
        self.test_dir = Path(__file__).parent / ".test_scratch"
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.output_pdf = self.test_dir / "test_result.pdf"

    def tearDown(self) -> None:
        cleanup_temp_dir(self.test_dir)

    def test_assemble_pdf_success(self) -> None:
        # Create 3 synthetic test images
        image_paths = []
        for i in range(1, 4):
            img_path = self.test_dir / f"page_{i:04d}.png"
            color = (50 * i, 70 * i, 90 * i)
            img = Image.new("RGB", (400, 300), color=color)
            img.save(img_path)
            img.close()
            image_paths.append(img_path)

        # Assemble into PDF
        result_path = assemble_pdf(image_paths, self.output_pdf)

        self.assertTrue(result_path.exists())
        self.assertGreater(result_path.stat().st_size, 0)

        # Verify PDF header
        with open(result_path, "rb") as f:
            header = f.read(5)
            self.assertEqual(header, b"%PDF-")


if __name__ == "__main__":
    unittest.main()
