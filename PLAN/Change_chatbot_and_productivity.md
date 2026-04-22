# TASK FRONTEND: Tích hợp Smart Filtering & Roadmap Auto-Creation

Tài liệu này mô tả **TẤT CẢ** những gì Frontend cần sửa để tương thích với Backend mới nhất.
Backend đã gánh phần lớn logic rồi, Frontend chỉ cần làm những việc rất nhỏ dưới đây.

---

## 1. Smart Filtering — Frontend gần như KHÔNG CẦN LÀM GÌ

### Backend đã làm gì?
Khi user chat kiểu "Tìm task ưu tiên cao", Backend sẽ:
1. Gửi câu hỏi cho Claude → Claude trả về cấu hình lọc JSON.
2. Backend **tự động ghi** cấu hình lọc đó vào bảng `FilterSettings` trong DB.
3. Backend trả về cho Frontend response có `type = "filter_applied"` (không phải `"filter"` nữa).

### Frontend chỉ cần làm 2 việc:

#### Việc 1: Gửi kèm `project_id` khi chat
Khi gọi `POST /chatbot`, thêm trường `project_id` vào body (ID của dự án user đang mở):
```javascript
// TRƯỚC (cũ)
{ "message": "Tìm task ưu tiên cao" }

// SAU (mới) — thêm project_id
{ "message": "Tìm task ưu tiên cao", "project_id": "uuid-of-current-project" }
```
Nếu user chưa mở project nào thì gửi `project_id: null` hoặc không gửi cũng được, Backend sẽ bỏ qua bước auto-apply.

**Vị trí sửa trong `chatbot (1).js`** — Hàm `sendMessage()` khoảng dòng 362:
```javascript
// Sửa lại payload POST
const postRes = await apiFetch(
    `${API}/chatbot`,
    { method: 'POST', body: JSON.stringify({ 
        message: text.trim(),
        project_id: window.CURRENT_PROJECT_ID || null  // ← THÊM DÒNG NÀY
    }) },
    { onLoadStart: () => {}, onLoadEnd: () => {} }
);
```

#### Việc 2: Xử lý response `type = "filter_applied"`
Trong hàm `buildMessageEl()` (khoảng dòng 771), thêm 1 nhánh IF nhỏ:
```javascript
if (isAI && msg.type === 'filter_applied') {
    // Backend đã tự động áp dụng bộ lọc rồi!
    // Frontend chỉ cần reload lại danh sách task
    document.dispatchEvent(new CustomEvent('reloadTasks'));
}
```
Hoặc nếu muốn UI đẹp hơn, hiển thị thêm 1 dòng thông báo nhỏ dưới tin nhắn AI:
```javascript
if (isAI && msg.type === 'filter_applied' && msg.data) {
    const note = document.createElement('div');
    note.className = 'cb-filter-applied-note';
    note.textContent = `✅ Đã áp dụng ${msg.data.filters_count} điều kiện lọc`;
    wrapper.appendChild(note);
    // Trigger reload task list
    document.dispatchEvent(new CustomEvent('reloadTasks'));
}
```

**Vậy là xong cho Smart Filtering!** Không cần gọi thêm API `PUT /filter` gì cả.

---

## 2. Roadmap Auto-Creation — Frontend chỉ cần RELOAD

### Backend đã làm gì?
Khi user bấm "Lưu Roadmap", Backend sẽ:
1. Duyệt qua tất cả nodes trong Roadmap.
2. Tự động tạo ra các Folder/Project thật trong bảng `items`.
3. Lưu Roadmap với các ID thật (đã mapping từ ID ảo).

### Frontend chỉ cần làm 1 việc:
Sau khi lưu thành công (hàm `saveData()` khoảng dòng 488), thêm 1 dòng dispatch event:
```javascript
// Hàm saveData() — sau dòng utils.showSuccess(...)
utils.showSuccess(t('chatbot.msg_saved'));
// ← THÊM DÒNG NÀY: Kích hoạt reload cây thư mục bên trái
document.dispatchEvent(new CustomEvent('reloadWorkspaceItems'));
```

**Vậy là xong cho Roadmap!**

---

## 3. Tóm tắt: Frontend chỉ sửa 3 dòng code

| # | Vị trí | Nội dung sửa |
|---|--------|-------------|
| 1 | `sendMessage()` dòng ~362 | Thêm `project_id` vào body POST |
| 2 | `buildMessageEl()` dòng ~771 | Bắt `type === 'filter_applied'` → `dispatchEvent('reloadTasks')` |
| 3 | `saveData()` dòng ~488 | Thêm `dispatchEvent('reloadWorkspaceItems')` |
