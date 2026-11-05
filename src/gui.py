"""Modern and simple PyQt6 desktop graphical user interface."""

import ctypes
import os
import sys
from pathlib import Path
from typing import Optional

# Preload local libxcb-cursor if present to prevent Qt xcb plugin loading failures
_local_cursor = Path(__file__).resolve().parent.parent / "libs" / "libxcb-cursor.so.0"
if _local_cursor.exists():
    try:
        ctypes.CDLL(str(_local_cursor))
    except Exception:
        pass

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QFont
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
    QSpinBox, QTextEdit, QVBoxLayout, QWidget,
)

from src.config import ExtractorConfig
from src.main import run_pipeline


class StreamRedirector(QObject):
    """Redirect stdout to a Qt signal for thread-safe UI logging."""
    text_written = pyqtSignal(str)

    def write(self, text: str) -> None:
        if text.strip():
            self.text_written.emit(text.strip())

    def flush(self) -> None:
        pass


class ExtractionWorker(QThread):
    """Background worker thread to run extraction without blocking UI."""
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, config: ExtractorConfig, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.config = config

    def run(self) -> None:
        redirector = StreamRedirector()
        redirector.text_written.connect(self.log_signal.emit)
        old_stdout = sys.stdout
        sys.stdout = redirector
        try:
            pdf_path = run_pipeline(self.config)
            self.finished_signal.emit(True, str(pdf_path))
        except Exception as exc:
            self.finished_signal.emit(False, str(exc))
        finally:
            sys.stdout = old_stdout


class OcrWorker(QThread):
    """Background worker thread to run Pix2Text OCR without blocking UI."""
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, pdf_path: Path, output_dir: Optional[Path] = None, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.output_dir = output_dir

    def run(self) -> None:
        redirector = StreamRedirector()
        redirector.text_written.connect(self.log_signal.emit)
        old_stdout = sys.stdout
        sys.stdout = redirector
        try:
            from src.ocr_engine import DocumentOcrEngine
            engine = DocumentOcrEngine(languages=["en", "vi"])
            res_path = engine.ocr_pdf(self.pdf_path, output_dir=self.output_dir)
            self.finished_signal.emit(True, str(res_path))
        except Exception as exc:
            self.finished_signal.emit(False, str(exc))
        finally:
            sys.stdout = old_stdout


class MainWindow(QMainWindow):
    """Main application window using PyQt6."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Google Drive Slide / PDF Extractor & Math OCR")
        self.resize(680, 620)
        self.setMinimumSize(600, 550)

        self.worker: Optional[ExtractionWorker] = None
        self.ocr_worker: Optional[OcrWorker] = None
        self._init_menu()
        self._init_ui()
        self._apply_styles()

    def _init_menu(self) -> None:
        menubar = self.menuBar()

        # Chức năng menu
        func_menu = menubar.addMenu("Chức năng")
        act_download = QAction("📥 Tải PDF từ URL", self)
        act_download.triggered.connect(self._clear_url)
        func_menu.addAction(act_download)

        act_ocr = QAction("🔬 OCR PDF có sẵn (Pix2Text)...", self)
        act_ocr.triggered.connect(self._ocr_existing_pdf)
        func_menu.addAction(act_ocr)

        act_demo = QAction("🧪 Nạp link Demo mẫu", self)
        act_demo.triggered.connect(self._fill_demo)
        func_menu.addAction(act_demo)

        func_menu.addSeparator()
        act_exit = QAction("❌ Thoát", self)
        act_exit.triggered.connect(self.close)
        func_menu.addAction(act_exit)

        # Trợ giúp menu
        help_menu = menubar.addMenu("Trợ giúp")
        act_about = QAction("ℹ️ Giới thiệu", self)
        act_about.triggered.connect(lambda: QMessageBox.information(
            self, "Giới thiệu", "Công cụ trích xuất slide / PDF và OCR công thức toán học tối ưu bằng Pix2Text."
        ))
        help_menu.addAction(act_about)

    def _init_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(12)

        header = QLabel("Trích Xuất PDF & OCR Công Thức Toán Học (Pix2Text)")
        header.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        layout.addWidget(header)

        # URL Input Group
        url_group = QGroupBox("🔗 Đường dẫn tài liệu (URL)")
        url_layout = QVBoxLayout(url_group)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Dán liên kết Google Drive hoặc Web Viewer vào đây...")
        url_layout.addWidget(self.url_input)
        layout.addWidget(url_group)

        # Output Path Group
        out_group = QGroupBox("📁 Nơi lưu file PDF kết quả")
        out_layout = QHBoxLayout(out_group)
        self.out_input = QLineEdit(str(Path.cwd() / "output.pdf"))
        btn_browse = QPushButton("Chọn nơi lưu...")
        btn_browse.clicked.connect(self._browse_output)
        out_layout.addWidget(self.out_input, stretch=1)
        out_layout.addWidget(btn_browse)
        layout.addWidget(out_group)

        # Options Row
        opt_layout = QHBoxLayout()
        self.cb_headless = QCheckBox("Chạy ngầm (Headless)")
        self.cb_headless.setChecked(True)
        opt_layout.addWidget(self.cb_headless)

        self.cb_ocr = QCheckBox("Tự động OCR Tiếng Việt & Ký hiệu khoa học")
        self.cb_ocr.setChecked(True)
        opt_layout.addWidget(self.cb_ocr)

        opt_layout.addSpacing(12)
        opt_layout.addWidget(QLabel("Độ nét HiDPI:"))
        self.spin_scale = QSpinBox()
        self.spin_scale.setRange(1, 4)
        self.spin_scale.setValue(2)
        opt_layout.addWidget(self.spin_scale)
        opt_layout.addStretch()
        layout.addLayout(opt_layout)

        # Single All-in-One Action Button (No Rocket Icon)
        self.btn_download = QPushButton("BẮT ĐẦU TẢI VÀ TẠO PDF TỰ ĐỘNG")
        self.btn_download.setFixedHeight(46)
        self.btn_download.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.btn_download.setStyleSheet("background-color: #2563eb; color: #ffffff; border-radius: 6px;")
        self.btn_download.clicked.connect(self._start_download)
        layout.addWidget(self.btn_download)

        # Real-time Log Box
        log_group = QGroupBox("Nhật ký tiến trình")
        log_layout = QVBoxLayout(log_group)
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFont(QFont("Monospace", 9))
        log_layout.addWidget(self.log_box)
        layout.addWidget(log_group, stretch=1)

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QWidget { background-color: #1e1e2e; color: #e2e8f0; font-family: sans-serif; }
            QMainWindow, QMenuBar { background-color: #181825; color: #cbd5e1; }
            QMenu { background-color: #1e1e2e; color: #e2e8f0; border: 1px solid #313244; }
            QMenu::item:selected { background-color: #2563eb; color: #ffffff; }
            QGroupBox { font-weight: bold; border: 1px solid #313244; border-radius: 8px; margin-top: 8px; padding-top: 10px; color: #60a5fa; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QLabel { color: #f8fafc; }
            QLineEdit, QSpinBox { background-color: #27273a; border: 1px solid #45475a; border-radius: 6px; padding: 6px 8px; color: #ffffff; }
            QLineEdit:focus, QSpinBox:focus { border: 1px solid #3b82f6; }
            QCheckBox { color: #cbd5e1; }
            QPushButton { background-color: #2563eb; color: #ffffff; border: none; border-radius: 6px; padding: 8px 14px; font-weight: bold; }
            QPushButton:hover { background-color: #1d4ed8; }
            QPushButton:disabled { background-color: #475569; color: #94a3b8; }
            QTextEdit { background-color: #11111b; color: #cbd5e1; border: 1px solid #313244; border-radius: 6px; }
        """)

    def _clear_url(self) -> None:
        self.url_input.clear()
        self.log_box.append("Sẵn sàng nhập URL mới để tải.")

    def _fill_demo(self) -> None:
        demo_path = Path(__file__).resolve().parent.parent / "test" / "sample_demo.html"
        self.url_input.setText(f"file://{demo_path.resolve()}")
        self.out_input.setText(str(Path.cwd() / "demo_output.pdf"))
        self.log_box.append("Đã nạp file demo mẫu vào ô URL.")

    def _browse_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Chọn nơi lưu PDF", str(self.out_input.text()), "PDF Files (*.pdf);;All Files (*)"
        )
        if path:
            self.out_input.setText(path)

    def _start_download(self) -> None:
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Thiếu URL", "Vui lòng nhập đường link Google Drive hoặc Web Viewer!")
            return

        out_path = Path(self.out_input.text().strip()).resolve()

        config = ExtractorConfig(
            url=url,
            output_path=out_path,
            headless=self.cb_headless.isChecked(),
            scale_factor=self.spin_scale.value(),
            settle_time=1.0,
            ocr=self.cb_ocr.isChecked(),
        )

        self.btn_download.setEnabled(False)
        self.log_box.append("=" * 45)
        self.log_box.append(f"Bắt đầu tải từ: {url}")
        self.log_box.append(f"Lưu vào: {out_path}")
        if self.cb_ocr.isChecked():
            self.log_box.append("⚡ Bật quy trình Tự động: Tải Slide -> OCR Tiếng Việt & Ký hiệu khoa học -> Đóng gói PDF luận văn.")

        self.worker = ExtractionWorker(config, self)
        self.worker.log_signal.connect(self.log_box.append)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.start()

    def _ocr_existing_pdf(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Chọn file PDF cần trích xuất OCR", str(Path.cwd()), "PDF Files (*.pdf);;All Files (*)"
        )
        if not file_path:
            return

        pdf_path = Path(file_path).resolve()
        self.btn_download.setEnabled(False)
        self.log_box.append("=" * 45)
        self.log_box.append(f"🔬 Bắt đầu OCR tài liệu: {pdf_path.name}")

        self.ocr_worker = OcrWorker(pdf_path=pdf_path, parent=self)
        self.ocr_worker.log_signal.connect(self.log_box.append)
        self.ocr_worker.finished_signal.connect(self._on_ocr_finished)
        self.ocr_worker.start()

    def _on_finished(self, success: bool, message: str) -> None:
        self.btn_download.setEnabled(True)
        if success:
            self.log_box.append(f"\n🎉 Hoàn tất quy trình thành công! Đã lưu: {message}")
            QMessageBox.information(self, "Thành công", f"Đã xuất file PDF thành công:\n{message}")
        else:
            self.log_box.append(f"\n[ERROR] Tiến trình thất bại: {message}")
            QMessageBox.critical(self, "Lỗi", f"Không thể hoàn thành tiến trình:\n{message}")

    def _on_ocr_finished(self, success: bool, message: str) -> None:
        self.btn_download.setEnabled(True)
        if success:
            self.log_box.append(f"\n🎉 OCR hoàn tất! Tệp Markdown tổng hợp:\n{message}")
            QMessageBox.information(self, "OCR Thành công", f"Đã trích xuất nội dung và công thức thành công:\n{message}")
        else:
            self.log_box.append(f"\n[ERROR] OCR thất bại: {message}")
            QMessageBox.critical(self, "Lỗi OCR", f"Không thể OCR tài liệu:\n{message}")

    def _convert_md_to_pdf(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Chọn file Markdown cần xuất PDF", str(Path.cwd()), "Markdown Files (*.md);;All Files (*)"
        )
        if not file_path:
            return

        md_path = Path(file_path).resolve()
        self.log_box.append("=" * 45)
        self.log_box.append(f"📑 Bắt đầu định dạng luận văn và xuất PDF từ: {md_path.name}")
        try:
            from src.md_to_pdf import markdown_to_pdf
            out_pdf = markdown_to_pdf(md_path)
            self.log_box.append(f"🎉 Xuất PDF chuẩn thể thức thành công!\nĐã lưu: {out_pdf}")
            QMessageBox.information(self, "Thành công", f"Đã xuất file PDF chuẩn thể thức luận văn:\n{out_pdf}")
        except Exception as exc:
            self.log_box.append(f"[ERROR] Lỗi xuất PDF: {exc}")
            QMessageBox.critical(self, "Lỗi", f"Không thể xuất file PDF: {exc}")


def launch_gui() -> None:
    """Entry point to launch PyQt6 graphical interface."""
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    launch_gui()
