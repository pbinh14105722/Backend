# DANH SÁCH CÔNG VIỆC FRONTEND (TỔNG HỢP)

Dưới đây là các đầu việc cần thực hiện để hoàn thiện tích hợp AI Chatbot v2.

## 1. Chatbot & Smart Filtering
- [ ] **Gửi Context**: Trong hàm `sendMessage`, thêm `project_id` vào body request.
- [ ] **Phản hồi tự động**: Trong `buildMessageEl`, nếu `type === 'filter_applied'`, thực hiện:
    - Hiển thị note thông báo.
    - `document.dispatchEvent(new CustomEvent('reloadTasks'))`.

## 2. Roadmap & Workspace Sync
- [ ] **Lưu Roadmap**: Cập nhật hàm xử lý nút Save:
    - Nhận response là một `Array` các Items.
    - Nếu mảng không rỗng, gọi `document.dispatchEvent(new CustomEvent('reloadWorkspaceItems'))`.
- [ ] **Lưu Folder Tree**: Đảm bảo đồng bộ Sidebar tương tự như Roadmap.

## 3. Smart Task Breakdown (🪄)
- [ ] **Giao diện**: Thêm nút "Magic Wand" (🪄) vào component Task Item.
- [ ] **API**: Gọi `POST /chatbot/breakdown` với body `{ "task_id": "..." }`.
- [ ] **Cập nhật**: Gọi `reloadTasks` sau khi AI xé nhỏ việc thành công.

## 4. Các API cần lưu ý
- `POST /chatbot`: Chat và tự động lọc.
- `POST /chatbot/save/roadmap`: Lưu lộ trình và tạo Project/Folder thật (Trả về Array ItemResponse).
- `POST /chatbot/breakdown`: Chia nhỏ task lớn (Mới).
- `POST /chatbot/save/folder-tree`: Lưu cấu trúc Folder Tree (Trả về thông báo thành công).

---
*Ghi chú: Backend đã xử lý toàn bộ logic phức tạp về Database và chuẩn hóa dữ liệu. Frontend chỉ cần tập trung vào việc gửi đúng ID và trigger lại các sự kiện Reload UI.*
