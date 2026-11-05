# Google Drive & Web Viewer PDF / Slide Extractor

Công cụ tự động hóa trích xuất toàn bộ slide / trang tài liệu PDF từ trình xem web (đặc biệt là Google Drive Viewer bị tắt tính năng tải xuống/in ấn) với độ phân giải cao và đóng gói thành 1 file PDF hoàn chỉnh.

---

## 🌟 Tính năng nổi bật

1. **Trích xuất ảnh gốc qua HTML5 Canvas:** Trực tiếp trích xuất bitmap gốc (`naturalWidth`, `naturalHeight`) do máy chủ gửi về, đạt độ nét 100%, không bị vỡ chữ và không dính viền giao diện (scrollbar, header).
2. **Cơ chế Fallback an toàn:** Tự động fallback sang chụp ảnh element nếu Canvas bị tainted bởi CORS.
3. **Giải quyết triệt để Lazy-Loading:** Tự động cuộn mồi (preload) qua toàn bộ tài liệu để kích hoạt tải ảnh trước khi trích xuất.
4. **HiDPI Render 2x:** Cấu hình Chrome với `--force-device-scale-factor=2` cho mật độ điểm ảnh sắc nét.
5. **Giao diện 1 nút bấm tự động toàn bộ chu trình:** Gộp mọi thao tác thành 1 nút duy nhất ("BẮT ĐẦU TẢI VÀ TẠO PDF TỰ ĐỘNG"), tự động tải slide -> OCR -> Đóng gói PDF luận văn chuẩn.
6. **🔬 Quy trình OCR Hybrid 5 lớp chuyên sâu cho Tiếng Việt & Ký hiệu Sinh/Y/Toán:**
   - **Layer 0 - LLM Difficulty Filter (Offline Qwen2.5-0.5B):** Lọc và phân loại nghiêm ngặt: các từ bình thường, câu văn tiếng Việt/tiếng Anh thông thường ở mức dễ thì **tuyệt đối không đụng vào**. Chỉ những từ/cụm ký hiệu được LLM gắn cờ là **mức siêu khó / dị thường** (mã gen, plasmid, công thức, ký tự lai tạp `1`, `/`, `I`, `l`) mới được cấp quyền xử lý.
   - **Layer 1 - Visual Hypothesis Permutations:** Sinh toàn bộ các giả thuyết hoán vị cho từ siêu khó (`1`, `/`, `I`, `l`, `|`) và so khớp độ tin cậy trực quan bằng font Unicode chuẩn (**DejaVu Sans / Arial Unicode MS**) kèm padding 3px.
   - **Layer 2 - Initial Baseline Lock (Bước 3):** Nếu độ tin cậy ban đầu của từ gốc ở Bước 3 cao hơn hoặc bằng các hoán vị sau thì giữ nguyên mặc định bản gốc, chống sửa nhầm.
   - **Layer 3 - Deep Academic Context:** Nhận dạng chính xác danh pháp gen, vector plasmid (`pJET1.2`, `pETDuet-1`, `slGmMKS2-X1`, `X1/X2/X3`).
   - **Layer 4 - Đơn vị đo & Nhiệt độ:** Tự động chuẩn hóa `µg/µl`, `U/µl`, `°C`, đầu mút DNA `3'`, `5'`.
   - **Layer 5 - Universal URL Restorer:** Tự động phục hồi toàn diện mọi liên kết web bị nhầm `//` thành `ll` và mất dấu chấm `.`.
7. **📄 Xuất PDF Chuẩn Định Dạng Luận Văn A4:** Chuyển đổi Markdown sau OCR thành PDF với font Times New Roman / Liberation Serif 13pt, căn đều hai bên (justified), thụt đầu dòng 1.25cm, giãn dòng 1.5, căn lề 25-20-25-20mm.

---

## 🚀 Cài đặt & Khởi chạy nhanh (1 Lệnh)

Chỉ cần chạy `./run.sh`, script sẽ tự động tạo virtualenv `.venv`, cài đặt thư viện và hỗ trợ các chế độ chạy:

```bash
# Cách 1: Mở Menu tương tác dòng lệnh (Hỗ trợ tải PDF và OCR trực tiếp)
./run.sh

# Cách 2: Khởi chạy trực tiếp Giao diện đồ họa (PyQt6 GUI)
./run.sh --gui

# Cách 3: Tải PDF và tự động OCR ra Markdown luôn
./run.sh "<GOOGLE_DRIVE_VIEWER_URL>" -o my_slides.pdf --ocr
```

---

## 🛠️ Tùy chọn dòng lệnh (CLI Options)

| Tham số | Mặc định | Mô tả |
| :--- | :--- | :--- |
| `url` | *(bắt buộc)* | Đường link Google Drive Viewer hoặc Web Viewer |
| `-o`, `--output` | `output.pdf` | Đường dẫn file PDF kết quả |
| `--scale` | `2` | Tỉ lệ scale điểm ảnh HiDPI (2x, 3x) |
| `--selector` | `div.ndfHFb-c4YZDc-cYSp0e-DARUcf-PLDbbf` | CSS selector của container trang |
| `--no-headless` | `False` | Bật cửa sổ trình duyệt (hữu ích khi cần xem trực tiếp) |
| `--settle` | `1.0` | Thời gian chờ (giây) để ảnh giải mã sau khi cuộn tới |
| `--timeout` | `30.0` | Thời gian tối đa (giây) chờ DOM trang nạp |
| `--user-data-dir` | `None` | Đường dẫn profile Chrome (dùng khi tài liệu yêu cầu đăng nhập) |
| `--keep-temp` | `False` | Giữ lại các ảnh PNG từng trang trong thư mục `.temp_pages` |
| `--ocr` | `False` | Bật OCR từng trang bằng Pix2Text sau khi đóng gói PDF |
| `--ocr-output` | `None` | Thư mục lưu kết quả OCR Markdown |

### Ví dụ sử dụng:

1. **Trích xuất cơ bản (Headless):**
   ```bash
   ./run.sh "https://drive.google.com/file/d/xxxx/view" -o presentation.pdf
   ```

2. **Mở cửa sổ Chrome trực quan (No Headless):**
   ```bash
   ./run.sh "https://drive.google.com/file/d/xxxx/view" --no-headless -o presentation.pdf
   ```

3. **Chạy với tài liệu riêng tư (dùng profile Chrome đã đăng nhập):**
   ```bash
   ./run.sh "https://drive.google.com/file/d/xxxx/view" --user-data-dir ~/.config/google-chrome/Default -o private.pdf
   ```

4. **Giữ lại các file ảnh tạm để biên tập riêng:**
   ```bash
   ./run.sh "https://drive.google.com/file/d/xxxx/view" --keep-temp -o slides.pdf
   ```

---

## 🧪 Chạy Test

Kiểm thử tự động logic lắp ráp PDF và giả lập trích xuất web viewer:

```bash
source .venv/bin/activate
python3 -m unittest discover test
```
