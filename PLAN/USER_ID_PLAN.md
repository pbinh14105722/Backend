# Phương án cung cấp `user_id` cho Frontend

Dưới đây là 3 phương án để Frontend có thể lấy được `user_id` từ Backend. Frontend có thể xem xét và chọn phương án thuận tiện nhất cho luồng xử lý hiện tại của ứng dụng.

---

## Phương án 1: Sử dụng API có sẵn (`GET /account`)
Backend hiện tại đã có sẵn một API trả về thông tin tài khoản, trong đó đã bao gồm `id`.

- **Endpoint**: `GET /account`
- **Headers**: `Authorization: Bearer <access_token>`
- **Response trả về**:
```json
{
  "id": 1,
  "username": "Nguyen Van A",
  "email": "nva@example.com"
}
```
**Ưu điểm**: Không cần Backend phải sửa code hay deploy lại. Frontend chỉ cần gọi API này sau khi đăng nhập thành công.

---

## Phương án 2: Trả về `user_id` ngay khi Đăng nhập / Đăng ký
Thay vì phải gọi thêm 1 API GET, Backend sẽ đính kèm luôn `user_id` vào cục dữ liệu trả về khi người dùng gọi API `/login` hoặc `/signup`.

- **Endpoint**: `POST /login` hoặc `POST /signup`
- **Response sẽ được sửa thành**:
```json
{
  "message": "Đăng nhập thành công!",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI...",
  "token_type": "bearer",
  "user_id": 1  // <--- Backend sẽ thêm trường này
}
```
**Ưu điểm**: Frontend tiết kiệm được 1 lần gọi API (chỉ cần gọi login là lấy được cả token lẫn id). Đây là phương án phổ biến nhất.

---

## Phương án 3: Tạo một API GET riêng biệt chỉ trả về ID
Nếu Frontend chỉ muốn một API cực nhẹ, chỉ trả về đúng `user_id` để dùng ở các component khác nhau.

- **Endpoint (Đề xuất)**: `GET /user-id`
- **Headers**: `Authorization: Bearer <access_token>`
- **Response sẽ được thiết kế**:
```json
{
  "user_id": 1
}
```
**Ưu điểm**: Response nhỏ gọn, rõ ràng đúng trọng tâm mục đích.

---

## Kết luận

- Nếu muốn nhanh gọn và tối ưu số lượng request mạng: **Hãy chọn Phương án 2**.
- Nếu Frontend cần lấy lại thông tin user khi tải lại trang (F5): **Hãy kết hợp dùng Phương án 1**.

Vui lòng báo lại cho Backend phương án bạn chọn để chúng tôi tiến hành cập nhật code (nếu chọn cách 2 hoặc 3)!
