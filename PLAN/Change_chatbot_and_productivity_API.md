# CHATBOT API — NHỮNG THAY ĐỔI CẦN CẬP NHẬT (Cho Frontend)

File này chỉ liệt kê những gì **MỚI hoặc CẦN SỬA** so với code frontend hiện tại (`chatbot (1).js`).
Những API đã hoạt động đúng (GET /chatbot, GET /chatbot/history, DELETE /chatbot, POST /chatbot/save/folder-tree) thì **KHÔNG** liệt kê lại.

---

## 1. SỬA: `POST /chatbot` — Thêm trường `project_id`

**Vị trí code:** Hàm `sendMessage()` ~ dòng 362

**Trước (cũ):**
```json
{ "message": "Tìm task ưu tiên cao" }
```

**Sau (mới):**
```json
{ "message": "Tìm task ưu tiên cao", "project_id": "uuid-project-đang-mở" }
```

- `project_id` là **optional** (có thể `null` hoặc không gửi).
- Nếu gửi kèm → Backend sẽ tự động áp dụng bộ lọc AI vào project đó mà Frontend không cần gọi thêm API filter.
- Nếu không gửi → Chatbot vẫn hoạt động bình thường như cũ.

**Code mẫu:**
```javascript
const postRes = await apiFetch(
    `${API}/chatbot`,
    { method: 'POST', body: JSON.stringify({ 
        message: text.trim(),
        project_id: window.CURRENT_PROJECT_ID || null  // ← THÊM
    }) },
    { onLoadStart: () => {}, onLoadEnd: () => {} }
);
```

---

## 2. MỚI: Xử lý response `type = "filter_applied"`

**Vị trí code:** Hàm `buildMessageEl()` ~ dòng 771

Đây là type hoàn toàn mới. Khi user chat kiểu "Tìm task ưu tiên cao", Backend sẽ:
1. Gọi Claude → Claude trả cấu hình bộ lọc.
2. Backend **TỰ ĐỘNG lưu** bộ lọc vào DB.
3. Trả về cho Frontend `type = "filter_applied"`.

**Cấu trúc `data` nhận được:**
```json
{
  "project_id": "uuid-of-project",
  "filters_count": 1,
  "logic": "and"
}
```

**Frontend KHÔNG CẦN gọi API `PUT /filter`.** Chỉ cần reload lại list task.

**Code mẫu — thêm vào cuối hàm `buildMessageEl()`:**
```javascript
// Sau khối if (isAI && (msg.type === 'folder_tree' || msg.type === 'roadmap') && msg.data)
if (isAI && msg.type === 'filter_applied' && msg.data) {
    const note = document.createElement('div');
    note.className = 'cb-filter-applied-note';
    note.textContent = `✅ Đã áp dụng ${msg.data.filters_count} điều kiện lọc`;
    wrapper.appendChild(note);
    // Reload task list
    document.dispatchEvent(new CustomEvent('reloadTasks'));
}
```

---

## 3. SỬA: `POST /chatbot/save/roadmap` — Thêm reload workspace

**Vị trí code:** Hàm `saveData()` ~ dòng 488

Backend giờ đây sẽ **tự động tạo ra các Folder/Project thật** trong DB khi lưu Roadmap. Frontend cần thêm 1 dòng dispatch event sau khi lưu thành công để thanh Sidebar (cây thư mục bên trái) tự refresh và hiển thị các folder mới.

**Code mẫu — thêm sau `utils.showSuccess(...)`:**
```javascript
utils.showSuccess(t('chatbot.msg_saved'));
// ← THÊM DÒNG NÀY
document.dispatchEvent(new CustomEvent('reloadWorkspaceItems'));
```

---

## Tóm tắt: Chỉ sửa 3 chỗ

| # | File | Hàm | Sửa gì |
|---|------|-----|--------|
| 1 | chatbot.js | `sendMessage()` | Thêm `project_id` vào body POST |
| 2 | chatbot.js | `buildMessageEl()` | Bắt `type === 'filter_applied'` → hiển thị note + reload tasks |
| 3 | chatbot.js | `saveData()` | Thêm `dispatchEvent('reloadWorkspaceItems')` sau lưu thành công |
