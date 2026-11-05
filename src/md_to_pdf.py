"""Module converting OCR Markdown files into clean, beautifully formatted academic PDFs matching the original thesis format.
Uses Chrome Headless Print-to-PDF with Times New Roman / Noto Serif styling.
"""

import subprocess
from pathlib import Path
from typing import Optional, Union

import markdown


ACADEMIC_CSS = """
@page {
    size: A4;
    margin: 25mm 20mm 20mm 25mm; /* Chuẩn căn lề Luận văn: Trên 2.5cm, Dưới 2cm, Trái 2.5cm, Phải 2cm */
    @bottom-right {
        content: counter(page);
    }
}

body {
    font-family: "Times New Roman", "Liberation Serif", "Noto Serif", serif;
    font-size: 13pt;
    line-height: 1.5;
    color: #111111;
    text-align: justify;
    margin: 0;
    padding: 0;
}

h1, h2, h3, h4 {
    font-family: "Times New Roman", "Liberation Serif", "Noto Serif", serif;
    color: #000000;
    font-weight: bold;
    text-align: left;
    page-break-after: avoid;
}

h1 {
    font-size: 16pt;
    text-align: center;
    text-transform: uppercase;
    margin-top: 24pt;
    margin-bottom: 16pt;
}

h2 {
    font-size: 14pt;
    margin-top: 18pt;
    margin-bottom: 10pt;
}

h3 {
    font-size: 13pt;
    margin-top: 14pt;
    margin-bottom: 8pt;
}

p {
    margin-top: 0;
    margin-bottom: 8pt;
    text-indent: 1.25cm; /* Thụt đầu dòng 1.25cm chuẩn luận văn */
}

/* Các đoạn danh sách hoặc đề mục không thụt lề */
ul, ol {
    margin-top: 4pt;
    margin-bottom: 8pt;
    padding-left: 1.5cm;
}

li {
    margin-bottom: 4pt;
}

blockquote {
    border-left: 3px solid #cbd5e1;
    padding-left: 12px;
    margin-left: 0;
    color: #475569;
    font-style: italic;
}

.page-break {
    page-break-before: always;
}

.header-meta {
    font-size: 10pt;
    color: #64748b;
    border-bottom: 1px solid #e2e8f0;
    padding-bottom: 4px;
    margin-bottom: 18pt;
    text-align: right;
}
"""


def markdown_to_pdf(
    md_path: Union[str, Path],
    output_pdf: Optional[Union[str, Path]] = None,
) -> Path:
    """Convert an OCR Markdown document to an A4 academic formatted PDF.
    
    Args:
        md_path: Path to the input Markdown file.
        output_pdf: Destination path for the PDF. Defaults to <md_name>_formatted.pdf.
        
    Returns:
        Path to the generated PDF.
    """
    md_path = Path(md_path).resolve()
    if not md_path.exists():
        raise FileNotFoundError(f"Markdown file does not exist: {md_path}")

    if output_pdf is None:
        output_pdf = md_path.parent / f"{md_path.stem}_formatted.pdf"
    output_pdf = Path(output_pdf).resolve()

    md_content = md_path.read_text(encoding="utf-8")

    # Replace page divider comments with printable page breaks
    formatted_md = md_content.replace("<!-- Page ", '<div class="page-break"></div>\n<!-- Page ')

    # Convert Markdown to HTML
    html_body = markdown.markdown(
        formatted_md,
        extensions=["extra", "tables", "sane_lists"],
    )

    full_html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>{md_path.stem}</title>
    <style>
{ACADEMIC_CSS}
    </style>
</head>
<body>
{html_body}
</body>
</html>
"""

    temp_html_path = md_path.parent / f".temp_{md_path.stem}.html"
    temp_html_path.write_text(full_html, encoding="utf-8")

    cmd = [
        "google-chrome",
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--no-pdf-header-footer",
        f"--print-to-pdf={output_pdf}",
        f"file://{temp_html_path}",
    ]

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        print(f"[✓] Đã xuất PDF định dạng luận văn thành công: {output_pdf}")
    finally:
        if temp_html_path.exists():
            temp_html_path.unlink()

    return output_pdf
