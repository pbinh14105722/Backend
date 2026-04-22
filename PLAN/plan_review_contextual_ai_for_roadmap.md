# 🔍 Đánh giá Kế hoạch "Contextual AI" — Sửa Roadmap trực tiếp & @Mention

## Verdict: ⭐⭐⭐⭐ (4/5) — Kế hoạch xuất sắc, cần tinh chỉnh một số chi tiết kỹ thuật

---

## ✅ Điểm mạnh

### 1. Kiến trúc Diff (Delta Update) — Quyết định thiết kế đúng đắn
Đây là điểm sáng nhất của bản kế hoạch. Thay vì bắt AI trả về toàn bộ roadmap (có thể hàng chục node), bạn chỉ yêu cầu AI trả về **thay đổi** (`add_nodes`, `update_nodes`, `delete_nodes`, ...).

**Lý do đúng:**
- Tiết kiệm token AI (giảm ~60-80% output so với trả lại toàn bộ)
- Giảm rủi ro AI "ảo giác" — output nhỏ hơn = ít chỗ sai hơn
- Frontend chỉ cần patch DOM cục bộ, không cần rebuild toàn bộ canvas

### 2. Tách rõ 2 luồng (Context-First vs Command-First)
Việc phân tách rõ ràng giữa:
- **Luồng 1 (AI Bar trên roadmap):** User đang nhìn canvas, muốn sửa *ngay tại chỗ*
- **Luồng 2 (@Mention trong chatbot):** User đang chat, muốn *gọi tên* roadmap cụ thể

...cho thấy bạn hiểu rõ UX context của từng màn hình. Đây không phải 2 tính năng riêng biệt, mà là **2 điểm chạm** cho cùng 1 tính năng — rất mature.

### 3. Preview + Undo trước khi commit
Backup state → apply diff → preview → confirm/cancel là workflow chuẩn cho destructive operations. Đây là điều mà nhiều sản phẩm AI bỏ qua.

### 4. Non-breaking changes
Kế hoạch không đụng vào DB schema, không sửa drag-and-drop logic hiện có. Đây là nguyên tắc an toàn đúng đắn khi thêm tính năng lớn.

---

## ⚠️ Các vấn đề cần giải quyết

### Vấn đề 1: Payload Context — Roadmap lớn có thể vượt token limit

> [!WARNING]  
> Đây là rủi ro kỹ thuật lớn nhất và bản plan đề cập nhưng chưa đưa ra giải pháp triệt để.

**Thực tế:** Roadmap 20 node, mỗi node có `x`, `y`, `item` object → JSON có thể dài **3,000–5,000 tokens** chỉ riêng phần context. Cộng thêm system prompt hiện tại của bạn đã khá dài (~2,500 tokens), tổng input có thể chạm **8,000–10,000 tokens** — vẫn trong limit của Claude Sonnet nhưng sẽ **tăng chi phí API đáng kể** và giảm chất lượng reasoning.

**Giải pháp đề xuất:**
```
Gửi roadmap context dưới dạng COMPACT:
- Chỉ gửi: node_id, name, type, parent_id (bỏ x, y, color)
- AI chỉ cần biết CẤU TRÚC, không cần biết LAYOUT
- Frontend tự xử lý layout khi apply diff (tính x, y mới)
```

### Vấn đề 2: Cấu trúc Diff JSON — Thiếu định nghĩa chi tiết cho `update_nodes`

Bản plan liệt kê 5 action types nhưng chưa định nghĩa rõ schema cho từng loại:

```json
// update_nodes cần format nào?
// Option A: Partial update (chỉ field thay đổi)
{"update_nodes": {"n2": {"name": "Tên mới"}}}

// Option B: Full replacement
{"update_nodes": {"n2": {"x": 400, "y": 250, "item": {...full item...}}}}
```

**Khuyến nghị:** Dùng **Option A (Partial update)** — nhất quán với triết lý Diff và tiết kiệm token hơn. Nhưng cần phải define rõ trong prompt spec.

### Vấn đề 3: Node ID conflict khi `add_nodes`

Khi AI thêm node mới, nó sẽ generate ID giả (ví dụ `"n6"`). Nhưng:
- Roadmap hiện tại đã có `nCnt = 5`, nên node mới phải là `n6`
- AI không biết `nCnt` hiện tại trừ khi Frontend gửi kèm

**Giải pháp:** Frontend **bắt buộc** phải gửi `nCnt` trong context. Hoặc backend tự re-index node ID sau khi nhận diff.

### Vấn đề 4: Edge integrity sau khi `delete_nodes`

Nếu AI xóa node `n3`, nhưng có edge `n2 → n3` và `n3 → n5`, thì:
- Edge liên quan **phải tự động bị xóa** hoặc AI phải kèm `delete_edges` tương ứng
- Nếu AI quên (hallucination), canvas sẽ có "ghost edges" trỏ vào node không tồn tại

**Giải pháp:** Frontend parser `applyRoadmapDiff()` cần có bước **auto-cleanup**: sau khi xóa node, quét lại mảng edges và loại bỏ bất kỳ edge nào có `from` hoặc `to` trỏ đến node đã xóa.

### Vấn đề 5: @Mention — Regex `/@([\w\s]*)$/` không cover tiếng Việt

Roadmap name của user có thể là tiếng Việt (ví dụ: `@Lộ trình học Toán`). Regex `[\w\s]` không match Unicode characters như `ộ`, `ì`, `ạ`.

**Fix:** 
```javascript
// Thay thế
/@([\w\s]*)$/
// Bằng
/@([^\n@]*)$/
// Hoặc dùng Unicode-aware regex
/@([\p{L}\p{N}\s]*)$/u
```

---

## 📊 Đánh giá theo tiêu chí

| Tiêu chí | Điểm | Ghi chú |
|:---|:---:|:---|
| **Tầm nhìn kiến trúc** | ⭐⭐⭐⭐⭐ | Diff-based approach là lựa chọn tối ưu |
| **Chi tiết triển khai** | ⭐⭐⭐⭐ | Phân chia phase rõ ràng, nhưng thiếu spec chi tiết cho diff schema |
| **Đánh giá rủi ro** | ⭐⭐⭐ | Nhận diện đúng rủi ro nhưng giải pháp còn surface-level |
| **Khả thi với codebase hiện tại** | ⭐⭐⭐⭐⭐ | Tận dụng tốt `PATCH /roadmap/{id}` đã có, không cần sửa DB |
| **UX Design** | ⭐⭐⭐⭐ | Preview + Undo là quyết định đúng, lock canvas khi preview cũng tốt |

---

## 🎯 Khuyến nghị trước khi bắt tay code

1. **Viết Diff JSON Schema chi tiết** — Define rõ format cho cả 5 action types (`add_nodes`, `update_nodes`, `delete_nodes`, `add_edges`, `delete_edges`) với ví dụ cụ thể. Đây sẽ là "hợp đồng" giữa AI prompt, backend parser, và frontend renderer.

2. **Prototype prompt + test thủ công trước** — Trước khi viết bất kỳ dòng frontend nào, hãy cập nhật system prompt và test qua Postman/curl xem AI có trả đúng diff format hay không. Đây là bước rủi ro cao nhất (AI có thể không tuân thủ format mới).

3. **Giải quyết bài toán context compression** — Quyết định cách "nén" roadmap data trước khi nhét vào prompt. Đây là bottleneck lớn nhất về chi phí API.

4. **Fix regex cho tiếng Việt** — Thay `[\w\s]` bằng `[\p{L}\p{N}\s]` hoặc `[^\n@]`.

---

## Tóm lại

Đây là một bản kế hoạch **chất lượng cao**, thể hiện tư duy hệ thống tốt. Kiến trúc Diff là lựa chọn đúng, phân chia phase hợp lý, và việc giữ nguyên DB schema cho thấy sự thận trọng.

Điểm cần bổ sung chính là **chi tiết kỹ thuật ở tầng data contract** (diff schema) và **edge cases** (ghost edges, Unicode regex, node ID conflicts). Những thứ này không khó sửa nhưng nếu bỏ qua sẽ gây bug khó debug trong production.
