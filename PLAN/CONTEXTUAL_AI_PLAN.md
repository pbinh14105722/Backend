# PLAN — Tích hợp Contextual AI (Sửa Roadmap & @Mention)

## 1. Tổng quan

Thêm 2 điểm chạm để user sửa Roadmap bằng AI:
1. **AI Bar** — thanh chat ngang nhúng trực tiếp trên màn hình Roadmap
2. **@Mention** — gõ `@TênRoadmap` trong Chatbot để gọi và sửa roadmap bất kỳ

**Cốt lõi:** AI trả về **Diff (Delta Update)**, không trả toàn bộ roadmap.

---

## 2. Diff JSON Schema

### 2.1 Response format mới: `type = "roadmap_update"`

```json
{
  "message": "✅ Đã cập nhật roadmap **Tên roadmap**: thêm 2 giai đoạn mới.",
  "type": "roadmap_update",
  "data": {
    "target_roadmap_id": "uuid-roadmap-đang-sửa",
    "diff": {
      "add_nodes": {
        "n6": {"x": 1500, "y": 250, "item": {"id": "f3", "name": "Deployment", "type": "FOLDER", "color": "#22d3ee", "parent_name": null, "parent_id": null}}
      },
      "update_nodes": {
        "n2": {"item": {"name": "Design & UX Research"}}
      },
      "delete_nodes": ["n4"],
      "add_edges": [
        {"from": "n5", "to": "n6", "fromPort": "right", "toPort": "left", "etype": "one", "style": "solid", "label": ""}
      ],
      "delete_edges": [
        {"from": "n2", "to": "n4"}
      ]
    }
  }
}
```

### 2.2 Quy tắc cho từng action

| Action | Format | Ghi chú |
|:---|:---|:---|
| `add_nodes` | `{nodeKey: {x, y, item}}` | Key = `n{nCnt+1}`, `n{nCnt+2}`... |
| `update_nodes` | `{nodeKey: {partial fields}}` | **Partial** — chỉ field cần sửa |
| `delete_nodes` | `["n4", "n5"]` | Mảng node keys |
| `add_edges` | `[{from, to, ...full edge}]` | Full edge object |
| `delete_edges` | `[{from, to}]` | Chỉ cần from+to để identify |

### 2.3 Context nén gửi cho AI

Frontend chỉ gửi **cấu trúc compact** (bỏ x, y, color) để tiết kiệm token:

```json
{
  "id": "uuid-roadmap", "name": "Tên roadmap", "nCnt": 5,
  "nodes_summary": [
    {"key": "n1", "name": "Discovery", "type": "FOLDER"},
    {"key": "n2", "name": "Design", "type": "PROJECT", "parent": "n1"}
  ],
  "edges_summary": ["n1→n2", "n2→n3"]
}
```

---

## 3. Phân chia công việc

### Phase 1: Backend — Prompt & Validation (`chatbot.py`)

**Việc 1:** Thêm Section 9 vào system prompt

```
SECTION 9 — ROADMAP UPDATE (EDIT EXISTING)
type = "roadmap_update"

PURPOSE: Edit existing roadmap by returning ONLY the diff.
WHEN: User provides [ROADMAP_CONTEXT] and asks to modify.
RULES:
1. add_nodes keys start from n{nCnt+1}
2. update_nodes: partial update only
3. delete_nodes: MUST include related edges in delete_edges
4. All 5 keys MUST exist (empty {} or [] nếu không thay đổi)

MANDATORY MESSAGE FORMAT:
"✅ Đã cập nhật roadmap **[name]**: [mô tả ngắn]."
```

**Việc 2:** Thêm `roadmap_update` vào bảng type selection (Section 2)

**Việc 3:** Validate diff trong `call_claude_api()` — fill missing keys với defaults

**Việc 4:** Parse `[ROADMAP_CONTEXT]...[/ROADMAP_CONTEXT]` từ message trước khi gửi AI

```python
import re
def extract_roadmap_context(message: str):
    match = re.search(r'\[ROADMAP_CONTEXT\](.*?)\[/ROADMAP_CONTEXT\]', message, re.DOTALL)
    if match:
        context = json.loads(match.group(1))
        clean = re.sub(r'\[ROADMAP_CONTEXT\].*?\[/ROADMAP_CONTEXT\]', '', message, flags=re.DOTALL).strip()
        return context, clean
    return None, message
```

---

### Phase 2: Roadmap AI Bar (`roadmap.js`, `roadmap.css`)

**UI:** Thanh `#rm-ai-bar` fixed bottom, blur background + `#rm-preview-banner` top center

**Logic chính:**

```javascript
// 1. Nén roadmap → context compact
function buildRoadmapContext() { /* nodes_summary + edges_summary */ }

// 2. Gửi AI kèm context
async function sendAiEditRequest(userText) {
    backupState = deepClone({ nodes, edges, nCnt });
    const ctx = buildRoadmapContext();
    const payload = `[ROADMAP_CONTEXT]${JSON.stringify(ctx)}[/ROADMAP_CONTEXT]\n${userText}`;
    // POST → Poll → nhận diff → applyRoadmapDiff()
}

// 3. Apply diff lên canvas
function applyRoadmapDiff(diff) {
    // delete_nodes → delete_edges → auto-cleanup ghost edges
    // → update_nodes (partial merge) → add_nodes → add_edges
    // → rebuildAllNodes() + renderEdges()
}

// 4. Lock canvas khi preview + nút Hủy/Lưu
function cancelPreview()  { /* restore backupState */ }
async function commitPreview() { /* PATCH /roadmap/{id} */ }
```

---

### Phase 3: @Mention trong Chatbot (`chatbot.js`, `chatbot.css`)

**Việc 1:** Load danh sách roadmaps khi boot

```javascript
let _roadmaps = [];
async function loadRoadmapsList() {
    const res = await apiFetch(`${API}/roadmap`);
    if (res.ok) _roadmaps = await res.json();
}
```

**Việc 2:** Unicode-aware regex detect `@`

```javascript
const MENTION_REGEX = /(?:^|\s)@([\p{L}\p{N}\s]*)$/u;

inputEl.addEventListener('input', () => {
    const match = inputEl.value.match(MENTION_REGEX);
    if (match) {
        const filtered = _roadmaps.filter(r =>
            r.name.toLowerCase().includes(match[1].toLowerCase())
        );
        showMentionDropdown(filtered);
    } else {
        hideMentionDropdown();
    }
});
```

> `\p{L}` match mọi ký tự chữ cái Unicode (tiếng Việt + tiếng Anh), flag `u` bắt buộc.

**Việc 3:** Dropdown autocomplete + tag chip visual

**Việc 4:** Chọn roadmap → fetch context → inject `[ROADMAP_CONTEXT]` vào message

**Việc 5:** Render card "Áp dụng thay đổi" khi nhận `type: "roadmap_update"` trong chat

---

### Phase 4: Testing

| # | Test case | Kỳ vọng |
|:--|:---|:---|
| 1 | "Thêm giai đoạn Testing" trên AI Bar | `add_nodes` + `add_edges`, preview → Save |
| 2 | "Xóa node Design" | `delete_nodes` + `delete_edges` auto-cleanup |
| 3 | "Đổi tên Frontend → Web App" | `update_nodes` partial |
| 4 | Bấm Hủy sau preview | Rollback backup state |
| 5 | `@Lộ trình Toán` trong chatbot | Dropdown match tiếng Việt, tag chip |
| 6 | Roadmap 20+ nodes | Context compact < 1000 tokens |
| 7 | AI hallucinate node ID | `applyRoadmapDiff` skip invalid IDs |
| 8 | Delete node nhưng AI quên delete edge | Auto-cleanup ghost edges |

---

## 4. Rủi ro & Giải pháp

| Rủi ro | Giải pháp |
|:---|:---|
| AI hallucinate node ID | `if (!nodes[nid]) return;` trong parser |
| AI thiếu key trong diff | Backend fill defaults `{}` / `[]` |
| Ghost edges sau delete | Frontend auto-filter: `edges.filter(e => validKeys.has(e.from) && validKeys.has(e.to))` |
| Token limit roadmap lớn | Context nén: chỉ name+type+key, bỏ x/y/color |
| Race condition drag + AI | Lock canvas khi preview banner hiện |
| Tiếng Việt trong @Mention | `[\p{L}\p{N}\s]` + flag `u` |

---

## 5. Thứ tự thực hiện

```
Phase 1 (Backend prompt) → Test Postman → OK?
    ↓
Phase 2 (AI Bar)         → Test canvas  → OK?
    ↓
Phase 3 (@Mention)       → Test chatbot → OK?
    ↓
Phase 4 (Cross-test)     → Mobile + Desktop → Ship 🚀
```

**Bắt đầu:** Cập nhật system prompt + validate diff trong `chatbot.py`, test qua Postman.
