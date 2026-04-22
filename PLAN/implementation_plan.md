# Smart Filtering (Natural Language Filtering) Implementation

Bổ sung tính năng Lọc Dữ Liệu bằng ngôn ngữ tự nhiên cho Chatbot. Tính năng này cho phép người dùng nhập yêu cầu bằng văn bản (ví dụ: "Tìm cho tôi các task quan trọng tuần này") và Chatbot sẽ tự động chuyển đổi thành cấu hình JSON bộ lọc tương ứng để giao diện áp dụng.

## User Review Required

> [!IMPORTANT]
> - Chatbot sẽ trả về `type = "filter"` cùng với cấu hình JSON (logic, filters). **Frontend của bạn cần bắt được type này** để tự động gọi API `PUT /project/{projectId}/filter` (hoặc update state local) áp dụng bộ lọc lên dự án người dùng đang xem.
> - Tính năng này cực kỳ tiết kiệm token vì AI chỉ cần đọc Schema của bộ lọc, không cần đọc toàn bộ danh sách Task.

## Cập nhật Đề xuất

### 1. `chatbot.py`

#### [MODIFY] `chatbot.py`
- **Mở rộng System Prompt:** Thêm một mục hướng dẫn mới cho Claude:
  - `DÙNG type = "filter" KHI:` User yêu cầu tìm kiếm, lọc task, sắp xếp (ví dụ: "Hiển thị task quan trọng", "Các việc trễ hạn").
  - `Output Format:` JSON chứa `logic` (and/or) và `filters` array (dựa theo chuẩn cấu trúc trong `filter.py` và `schemas.py`).
  - Hướng dẫn chi tiết các field hợp lệ (name, priority, start_date, due_date, time_spent, create_date) và các operator hợp lệ (eq, contains, in, between, v.v.).
- **Validation Rules:** Thêm "filter" vào danh sách các type hợp lệ trong code validate response của Python. Kiểm tra cấu trúc data có chứa key `logic` và `filters` hay không.

### 2. `schemas.py`

#### [MODIFY] `schemas.py`
- Cập nhật mô tả (docstring/comments) trong `ChatMessageResponse` để phản ánh thêm loại type mới `"filter"`.

## Verification Plan

### Automated Tests
- Kiểm tra trực tiếp qua API `POST /chatbot` bằng cách gửi request: `{"message": "Tìm cho tôi các task ưu tiên cao"}`.
- Chờ phản hồi xem `type` có đúng bằng `"filter"` và `data` có chứa mảng bộ lọc `priority in [high]` hay không.

### Manual Verification
- Bạn cần update frontend để khi nhận được tin nhắn AI có `type="filter"`, giao diện tự động bật bảng Filter và áp dụng những thông số mà AI vừa trả về.
