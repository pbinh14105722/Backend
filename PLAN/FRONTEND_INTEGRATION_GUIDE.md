# TÀI LIỆU HƯỚNG DẪN TÍCH HỢP AI CHATBOT (DÀNH CHO FRONTEND)

Tài liệu này mô tả các thay đổi cần thiết trong logic Frontend để đồng bộ với hệ thống Backend đã được tối ưu hóa (Smart Filtering, Auto-Roadmap, Lazy Loading).

---

## 1. Cập nhật API Chat (`POST /chatbot`)

### Gửi thêm Project ID
Khi user gửi tin nhắn, Frontend cần đính kèm `project_id` của dự án hiện tại để AI có thể tự động áp dụng bộ lọc (Filter) ngay lập tức.

**Thay đổi trong hàm gửi tin nhắn:**
```javascript
// Body gửi lên Backend
{
  "message": "...",
  "project_id": window.CURRENT_PROJECT_ID || null // Gửi ID của dự án đang mở
}
```

### Xử lý type `filter_applied`
Khi AI trả về type này, có nghĩa là Backend đã tự động lưu cấu hình lọc vào Database cho dự án đó. Frontend chỉ cần tải lại danh sách Task.

**Logic trong hàm render tin nhắn:**
```javascript
if (msg.type === 'filter_applied') {
    // Hiển thị thông báo nhỏ: "Đã tự động áp dụng bộ lọc AI"
    // Kích hoạt reload task list
    document.dispatchEvent(new CustomEvent('reloadTasks'));
}
```

---

## 2. Lưu Roadmap & Cập nhật Workspace

API `POST /chatbot/save/roadmap` hiện tại đã thay đổi định dạng trả về để hỗ trợ cập nhật UI sidebar ngay lập tức.

### Định dạng dữ liệu trả về mới:
Backend trả về một **Mảng phẳng (Array)** các Item chuẩn `ItemResponse`.

```json
[
  {
    "id": "uuid-thật-1",
    "name": "Thư mục mới",
    "type": "FOLDER",
    "ai_id": "f1", // Dùng để map với node cũ trên UI roadmap nếu cần
    ... (các trường chuẩn ItemResponse)
  }
]
```

### Nhiệm vụ Frontend:
Khi nhận được mảng này sau khi lưu thành công:
1. Gộp (merge/push) các item này vào danh sách items hiện tại của Workspace.
2. Hoặc đơn giản nhất: Kích hoạt `reloadWorkspaceItems` event.

```javascript
const response = await fetch('/chatbot/save/roadmap', { ... });
const newItems = await response.json();

if (Array.isArray(newItems) && newItems.length > 0) {
    // Backend báo đã tạo thêm Folder/Project thật
    document.dispatchEvent(new CustomEvent('reloadWorkspaceItems'));
}
```

---

## 3. Tính năng Chia nhỏ công việc (Smart Breakdown)

Đây là tính năng mới để AI tự động xé nhỏ 1 task lớn thành các task con.

### API: `POST /chatbot/breakdown`
- **Request Body:** `{ "task_id": "uuid-của-task" }`
- **Logic UI:** 
  - Thêm một icon "Cây đũa phép" (🪄) cạnh tên task lớn.
  - Khi click, gọi API này.
  - Khi thành công, gọi `document.dispatchEvent(new CustomEvent('reloadTasks'))`.

---

## 4. Danh sách các Event cần Handle/Dispatch

| Tên Event | Tác dụng |
| :--- | :--- |
| `reloadTasks` | Yêu cầu UI tải lại danh sách tasks của dự án hiện tại. |
| `reloadWorkspaceItems` | Yêu cầu UI tải lại danh sách Folder/Project ở thanh Sidebar. |

---

## Ghi chú về Dữ liệu:
- Tất cả các item mới tạo (từ Roadmap hoặc Folder Tree) đều được Backend gán ID thật (UUID). 
- Các trường `priority`, `color`, `position` đã được Backend xử lý chuẩn hóa, Frontend không cần validate lại.
