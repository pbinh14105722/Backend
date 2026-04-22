# BẢN MÔ TẢ CÔNG VIỆC CHO FRONTEND: TÍCH HỢP API LẤY USER ID

Tài liệu này cung cấp các thông tin cần thiết để Frontend tích hợp chức năng lấy `user_id` và xử lý các trạng thái lỗi liên quan.

---

## 1. Thông tin API (Endpoint)

- **Method:** `GET`
- **URL:** `/user-id` (Ví dụ: `http://localhost:8000/user-id`)
- **Headers yêu cầu:** 
  - `Authorization: Bearer <access_token>`

---

## 2. Kết quả trả về (Responses)

Frontend cần xử lý 4 trạng thái (Status Code) sau đây:

### ✅ 2.1. Thành công (Status: `200 OK`)
Khi gửi đúng token hợp lệ, hệ thống trả về đúng `user_id`.
```json
{
  "user_id": 1
}
```
**Frontend Task:** Trích xuất trường `user_id` và lưu vào state (như Redux, Context) để sử dụng cho các luồng xử lý khác.

### ❌ 2.2. Lỗi chưa xác thực / Sai Token (Status: `401 Unauthorized`)
Xảy ra khi Frontend quên gửi Header Authorization, token bị sai, hoặc token đã hết hạn.
```json
{
  "detail": "Không thể xác thực thông tin"
}
```
**Frontend Task:** Hiển thị thông báo (Toast) yêu cầu đăng nhập lại, tiến hành xóa token cũ trong bộ nhớ và chuyển hướng (redirect) người dùng về màn hình Login.

### ❌ 2.3. Lỗi không tìm thấy dữ liệu (Status: `404 Not Found`)
Xảy ra khi token gửi lên vẫn hợp lệ nhưng tài khoản đó đã bị xóa khỏi hệ thống.
```json
{
  "detail": "Không tìm thấy thông tin người dùng"
}
```
**Frontend Task:** Thông báo lỗi tài khoản không còn tồn tại, xóa state đăng nhập và đẩy người dùng về trang chủ hoặc màn hình Login.

### ❌ 2.4. Lỗi máy chủ (Status: `500 Internal Server Error`)
Xảy ra khi Backend gặp lỗi hệ thống bất ngờ (Database sập, lỗi code,...).
```json
{
  "detail": "Lỗi máy chủ khi lấy user_id: <chi_tiết_lỗi>"
}
```
**Frontend Task:** Bắt lỗi (Catch) và hiển thị thông báo thân thiện (VD: "Hệ thống đang bảo trì, vui lòng thử lại sau"). Không làm sập ứng dụng.

---

## 3. Checklist công việc dành cho Frontend

- [ ] Cấu hình Axios/Fetch để gọi API `GET /user-id` kèm Bearer Token.
- [ ] Xử lý thành công: Lưu `user_id` vào state quản lý cục bộ.
- [ ] Xử lý mã lỗi `401`: Code logic tự động đăng xuất và đá văng về trang Login.
- [ ] Xử lý mã lỗi `404` và `500`: Hiển thị thông báo lỗi (Toast/Alert) cho người dùng biết.
- [ ] Test lại API bằng Postman/Swagger UI (có sẵn ở `/docs`) trước khi ghép code chính thức.
