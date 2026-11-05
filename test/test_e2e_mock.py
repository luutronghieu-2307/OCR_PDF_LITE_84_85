"""End-to-end test with a mock Google Drive Viewer page."""

import unittest
from pathlib import Path
from src.config import ExtractorConfig
from src.main import run_pipeline


class TestE2EMock(unittest.TestCase):
    """End-to-end integration test simulating Google Drive viewer HTML."""

    def setUp(self) -> None:
        self.test_dir = Path(__file__).parent / ".test_e2e_scratch"
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.html_file = self.test_dir / "mock_viewer.html"
        self.output_pdf = self.test_dir / "mock_output.pdf"

        # Create mock HTML page mimicking Google Drive Viewer structure
        # Embed a 1x1 or 100x100 transparent/colored PNG data URI
        sample_png = (
            "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAGQAAABkCAYAAABw4pVUAAA"
            "AJUlEQVR42u3BAQ0AAADCoPdPbQ8HFAAAAAAAAAAAAAAAAADwZ0nOAAGq5f5mAAAAAElFTkSuQmCC"
        )
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head><title>Mock Viewer</title></head>
        <body>
            <div class="ndfHFb-c4YZDc-cYSp0e-DARUcf-PLDbbf">
                <img src="{sample_png}" style="width:200px;height:200px;" />
            </div>
            <div class="ndfHFb-c4YZDc-cYSp0e-DARUcf-PLDbbf">
                <img src="{sample_png}" style="width:200px;height:200px;" />
            </div>
        </body>
        </html>
        """
        self.html_file.write_text(html_content, encoding="utf-8")

    def tearDown(self) -> None:
        if self.test_dir.exists():
            import shutil
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_mock_pipeline_extraction(self) -> None:
        config = ExtractorConfig(
            url=f"file://{self.html_file.resolve()}",
            output_path=self.output_pdf,
            selector="div.ndfHFb-c4YZDc-cYSp0e-DARUcf-PLDbbf",
            headless=True,
            scale_factor=2,
            settle_time=0.2,
            timeout=5.0,
            clean_temp=True,
            temp_dir=self.test_dir / ".temp_pages",
        )

        result_path = run_pipeline(config)

        self.assertTrue(result_path.exists())
        self.assertGreater(result_path.stat().st_size, 0)
        with open(result_path, "rb") as f:
            self.assertEqual(f.read(5), b"%PDF-")


if __name__ == "__main__":
    unittest.main()
