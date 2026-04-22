# API Specification: Manask Roadmap Generation

## Thông tin chung

- **Phiên bản**: 1.0 · 2025
- **Scope**: `GET /chatbot` (type=roadmap) · `POST /chatbot/save/roadmap` · render preview
- **Auth**: Bearer JWT — header `Authorization: Bearer <access_token>`
- **Content-Type**: application/json · UTF-8
- **Base URL**: <https://backend-u1p2.onrender.com/>

## 1. Tổng quan

AI sinh roadmap dựa trên item chưa tồn tại trong database (roadmap mới hoàn toàn). Toàn bộ thông tin hiển thị — tên, loại, màu, tên folder cha — được nhúng trực tiếp vào từng node thay vì tham chiếu qua id. Preview hiển thị ngay khi AI trả về; lưu xuống DB khi người dùng nhấn nút Lưu.

## 2. Data Model — type = "roadmap"

### 2.1 data object (root)

| Field | Kiểu | Nullable | Mô tả |
|---|---|---|---|
| title | string | Không | Tiêu đề hiển thị trong chat UI. AI tự sinh. VD: "E-Commerce Roadmap" |
| id | string | Không | AI-generated id — backend bỏ qua, tự sinh id thật khi lưu |
| name | string | Không | Tên bản ghi — backend dùng làm tên khi lưu vào DB |
| nodes | object | Không | Map các node. Key là nid (string), value là Node object. {} nếu rỗng |
| edges | Edge[] | Không | Danh sách cạnh. [] nếu rỗng |
| nCnt | integer ≥ 0 | Không | Bộ đếm node. AI tự sinh, backend lưu nguyên |
| panX | number | Không | Vị trí pan ngang (px). Mặc định: 0 |
| panY | number | Không | Vị trí pan dọc (px). Mặc định: 0 |
| zoom | number 0.15–4.0| Không | Mức zoom. Mặc định: 1.0 |

### 2.2 Node object

Mỗi entry trong `nodes` có dạng `"nid": { x, y, item }`. Node không có field `item_id` — item được nhúng trực tiếp.

| Field | Kiểu | Nullable | Mô tả |
|---|---|---|---|
| x | number | Không | Toạ độ X (px). Không giới hạn, có thể âm. Không dùng Math.max(0, ...) |
| y | number | Không | Toạ độ Y (px). Không giới hạn, có thể âm |
| item.id | string | Không | AI-generated id. Backend bỏ qua khi lưu |
| item.name | string | Không | Tên hiển thị trên node |
| item.type | "FOLDER" hoặc "PROJECT" | Không | Chỉ 2 loại. TASK không có node trên roadmap |
| item.color| string hex | Không | Màu icon. Phải là 1 trong 20 giá trị hợp lệ (xem mục 2.4) |
| item.parent_name | string | Có | Tên folder cha. Hiển thị dòng `↳ parent_name` dưới tên node. null nếu ở cấp gốc |

> ⚠️ **Lưu ý**: `item.parent_name` thay cho `parent_id`. Vì item chưa tồn tại trong DB khi AI sinh roadmap, frontend không thể lookup `parent_id`. Nhúng trực tiếp tên cha để preview hiển thị đúng mà không cần round-trip.

### 2.3 Edge object

| Field | Kiểu | Nullable | Mô tả |
|---|---|---|---|
| from | string | Không | nid của node nguồn |
| to | string | Không | nid của node đích |
| fromPort | "top" │ "bottom" │ "left" │ "right" | Không | Cổng kết nối tại node nguồn |
| toPort | "top" │ "bottom" │ "left" │ "right" | Không | Cổng kết nối tại node đích |
| etype | "none" │ "one" │ "two" | Không | Kiểu mũi tên. "one" = một chiều (mặc định) |
| style | "solid" │ "dashed" │ "dotted" │ "faded" | Không | Kiểu đường nối. "solid" là mặc định |
| label | string | Không | Nhãn trên cạnh. "" nếu không có nhãn |

### 2.4 Giá trị hợp lệ của item.color (20 màu)

`#a0aec0` · `#818cf8` · `#4fd1ed` · `#f6ad55` · `#b83280` · `#f687b3` · `#faf089` · `#9ae6b4` · `#fc8181` · `#a78bfa` · `#22d3ee` · `#6ee7b7` · `#8b5cf6` · `#3b82f6` · `#ec4899` · `#f87171` · `#94a3b8` · `#b7948c` · `#5eead4` · `#4a5568`

Backend validate và fallback về `#a0aec0` nếu giá trị sai.

## 3. GET /chatbot — Response roadmap

### 3.1 Response khi type = "roadmap"

| Field | Kiểu | Mô tả |
|---|---|---|
| message | string | Câu trả lời văn bản của AI |
| type | "roadmap" | Loại dữ liệu kèm theo |
| data | object | Roadmap data object — xem mục 2.1 |

### 3.2 Cách frontend render preview

- Đọc `data.nodes` (dict), với mỗi entry lấy `item.name`, `item.type`, `item.color` để vẽ node (badge + icon + tên).
- Nếu `item.parent_name` khác null → hiển thị dòng `↳ parent_name` dưới tên node.
- Không lookup `_items`, không cần `GET /items` cho roadmap mới.

## 4. POST /chatbot/save/roadmap

### 4.1 Mô tả

| Thuộc tính | Giá trị |
|---|---|
| Method | POST |
| Endpoint | `/chatbot/save/roadmap` |
| Trigger | Người dùng nhấn nút Lưu trên preview trigger hoặc trong preview panel |
| Request Body | Chính là data object từ AI response — không transform |
| HTTP Success | 201 Created |
| HTTP Error | 400 schema sai · 401 token hết hạn · 422 color ngoài 20 giá trị · 500 lỗi server |

### 4.2 Backend xử lý (4 bước)

1. Bỏ qua `id` trong request. Tự sinh id thật cho roadmap.
2. Dùng `name` làm tên bản ghi trong DB.
3. Với mỗi node: tạo FOLDER/PROJECT thật từ `item.name`, `item.type`, `item.color`. Bỏ qua `item.id` và `item.parent_name`.
4. Validate color — nếu sai, fallback về `#a0aec0`.

### 4.3 Response Body (201 Created)

Trả về roadmap đã lưu (với id thật) và `created_items` — danh sách FOLDER/PROJECT vừa tạo, mỗi item có: `id`, `name`, `type`, `color`, `parent_id` (UUID thật), `position`, `expanded`.

### 4.4 Frontend sau khi nhận response

Push từng item trong response.`created_items` vào `_items`. Sidebar cập nhật ngay, không cần reload trang.

## 5. Bảng tổng hợp ràng buộc

| Field | Kiểu & Ràng buộc | Ghi chú |
|---|---|---|
| data.title | string, không rỗng | AI tự sinh |
| data.id | string | Backend bỏ qua, tự sinh UUID thật |
| data.name | string, không rỗng | Backend dùng làm tên bản ghi |
| data.nodes | object (dict) | {} nếu không có node |
| data.edges | Edge[] | [] nếu không có cạnh |
| data.zoom | number, 0.15–4.0 | AI mặc định 1.0 |
| Node.x / Node.y | number, không giới hạn | Có thể âm |
| item.type | "FOLDER" hoặc "PROJECT" | TASK không xuất hiện |
| item.color | 1 trong 20 giá trị hex | Fallback `#a0aec0` nếu sai |
| item.parent_name | string hoặc null | Chỉ dùng cho preview, không build hierarchy DB |
| Edge.fromPort / toPort | "top" │ "bottom" │ "left" │ "right" | 4 giá trị cố định |
| Edge.etype | "none" │ "one" │ "two" | Kiểu mũi tên |
| Edge.style | "solid" │ "dashed" │ "dotted" │ "faded" | Kiểu đường |
| Edge.label | string | Cho phép "" |

## 6. Lưu ý triển khai

**Frontend:**

- Khi nhận AI response có `type = "roadmap"`: hiển thị preview trigger + render canvas từ `data.nodes`.
- `Node.x` và `Node.y` có thể âm — không clamp về 0.
- Sau khi save thành công: push `created_items` vào `_items`.

**Backend:**

- `item.id` trong nodes là AI-generated — bỏ qua, tự sinh UUID thật.
- `item.parent_name` chỉ dùng cho preview, không dùng để build parent-child hierarchy trong DB.
- Trả về `created_items` với `parent_id` là UUID thật (insert FOLDER trước, PROJECT sau).
