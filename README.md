# 🤖 Bia — Trợ lý AI trên desktop (chạy 100% local)

**Bia** là một trợ lý ảo tiếng Việt sống ngay trên desktop của bạn: một nhân vật 3D
đi lại, vẫy tay, nói chuyện — và **nghe lệnh rảnh tay** bằng cách gọi tên *"a lô Bia"*.
Bia hiểu ý bạn qua **Ollama (LLM local)**, **hỏi xác nhận trước khi hành động**, tự
điều khiển máy, soạn file Office, và **tự học hỏi** về bạn bằng một **trí nhớ dạng
mạng nơ-ron** lưu trong PostgreSQL/pgvector.

> Bộ não, giọng nói và trí nhớ chạy **offline** trên máy bạn. Riêng khi bạn hỏi
> tin tức / thông tin thời gian thực, Bia mới truy vấn internet (chỉ gửi từ khoá tìm kiếm).

---

## ✨ Tính năng

- 🧠 **Bộ não LLM local**: dùng Ollama phân tích câu nói tiếng Việt thành hành động (JSON).
- ✅ **Xác nhận trước khi làm**: Bia luôn hỏi lại ("Bạn muốn mình mở YouTube đúng không?") rồi mới thực thi.
- 🕹️ **Điều khiển máy**: mở web, mở ứng dụng, tìm kiếm.
- 📄 **Soạn Office**: tạo file Word, Excel, PowerPoint có nội dung do LLM sinh.
- ⏰ **Ngày giờ tức thì**: hỏi "mấy giờ / hôm nay thứ mấy" — trả lời từ đồng hồ máy (offline).
- 🌐 **Tin tức & thông tin mới**: hỏi bản tin mới nhất, luật mới, thời tiết... Bia tra Google News rồi tóm tắt (cần internet).
- 🎙️ **Giọng nói offline**: nghe bằng `faster-whisper` (STT), nói bằng `piper` (TTS) — tiếng Việt.
- 📢 **Gọi tên rảnh tay (wake word)**: nói *"a lô Bia ..."* là Bia thức dậy và làm, không cần bấm.
- 🧍 **Mascot 3D**: nhân vật nổi trên desktop, tự đi/chạy/nhảy, vẫy tay chào, đổi trạng thái khi nghe/nói.
- 🕸️ **Trí nhớ mạng nơ-ron + tự học**: Bia nhớ tên, sở thích, thói quen của bạn; các ký ức nối nhau như nơ-ron và nhớ lại theo *liên tưởng*. Lưu trong PostgreSQL (pgvector), embedding nén dạng `halfvec` cho nhẹ.

---

## 🗂️ Cấu trúc dự án

```
BIAA/
├─ run.py                     # điểm khởi chạy (CLI text hoặc mascot)
├─ requirements.txt
├─ assistant/
│  ├─ config.py               # cấu hình (đọc ~/.config/assistant/config.json)
│  ├─ llm.py                  # bộ não: gọi Ollama -> intent / trích fact / nội dung Office
│  ├─ intents.py              # định nghĩa hành động + mức rủi ro
│  ├─ executor.py             # thực thi hành động
│  ├─ confirm.py              # luồng xác nhận
│  ├─ cli.py                  # chế độ chat bằng chữ
│  ├─ memory.py               # trí nhớ (tự định tuyến Postgres <-> JSON)
│  ├─ neural_memory.py        # mạng nơ-ron trí nhớ (bản lưu JSON)
│  ├─ pg_memory.py            # mạng nơ-ron trí nhớ trên PostgreSQL/pgvector
│  ├─ actions/                # system.py (mở app/web), office.py (Word/Excel/PPT)
│  ├─ voice/                  # stt.py (nghe), tts.py (nói), wake.py (nhận tên gọi)
│  └─ mascot/                 # pet_animated.py (3D có animation), app.py (2D)...
└─ assets/                    # mô hình 3D + giọng piper
```

---

## 📋 Yêu cầu

- **Linux** có màn hình đồ họa (mascot cần OpenGL) và **micro** (cho giọng nói).
- **Python 3.12+**.
- **Ollama** đang chạy + đã tải model:
  - `qwen2.5-coder:7b` (hoặc `:14b`) — bộ não.
  - `nomic-embed-text` — tạo embedding cho trí nhớ.
- **Trình phát WAV** `aplay` (gói `alsa-utils`) để đọc phản hồi.
- *(Tùy chọn)* **PostgreSQL có extension `pgvector`** để lưu trí nhớ. Không có cũng không sao — Bia tự lưu vào JSON.

---

## 🚀 Cài đặt

```bash
# 1) Lấy mã nguồn
git clone https://github.com/TThanhtrung20/BIAA.git
cd BIAA

# 2) Môi trường ảo + thư viện
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 3) Ollama + model (cài Ollama từ https://ollama.com trước)
ollama pull qwen2.5-coder:7b
ollama pull nomic-embed-text
```

Model Whisper (STT) sẽ **tự tải** lần chạy đầu. Giọng piper (TTS) đã có sẵn trong
`assets/voices/`.

> **Ghi chú Linux/Qt:** nếu mascot báo thiếu `libxcb-cursor0`, cài:
> `sudo apt install libxcb-cursor0` (hoặc gói tương đương của bản phân phối).

---

## ▶️ Cách dùng

```bash
# Chế độ chat bằng chữ trong terminal
.venv/bin/python run.py

# Nhân vật mascot 3D nổi trên desktop
.venv/bin/python run.py mascot
```

**Trong chế độ text**, gõ yêu cầu bằng tiếng Việt. Lệnh đặc biệt:
- `trí nhớ` — xem Bia đã học gì về bạn (kèm thống kê mạng nơ-ron).
- `liên tưởng <điều gì>` — xem mạng liên tưởng tới ký ức nào.
- `quên hết` — xoá toàn bộ trí nhớ. &nbsp;•&nbsp; `thoát` — dừng.

**Với mascot**, có thể:
- Nói **"a lô Bia, mở YouTube"** — rảnh tay, không cần bấm.
- Hoặc **double-click** vào Bia để nói chuyện.
- **Chuột phải** để mở menu (đổi động tác, bật/tắt nghe gọi tên, thoát).

---

## ⚙️ Cấu hình

Cấu hình nằm ở `~/.config/assistant/config.json` (tạo tự động). Vài khóa hay dùng:

| Khóa | Ý nghĩa | Mặc định |
|---|---|---|
| `model` | Model Ollama làm bộ não | `qwen2.5-coder:7b` |
| `assistant_name` | Tên trợ lý | `Bia` |
| `wake_words` | Các cách gọi tên để kích hoạt | `["bia", "bi a"]` |
| `wake_enabled` | Luôn lắng nghe tên gọi | `true` |
| `wake_threshold` | Ngưỡng năng lượng mic coi là có tiếng | `0.02` |
| `auto_learn` | Tự học thông tin lâu dài sau mỗi câu | `true` |
| `use_postgres` | Lưu trí nhớ vào Postgres (không thì JSON) | `true` |
| `pg_dsn` | Chuỗi kết nối Postgres/pgvector | *(để trống mật khẩu)* |
| `whisper_model` | Kích thước model STT (`tiny`/`base`/`small`...) | `small` |
| `piper_voice` | Đường dẫn giọng piper (.onnx) | `assets/voices/...` |

> 🔒 **Bảo mật:** không đặt mật khẩu DB trong mã nguồn. Đặt DSN thật trong
> `config.json` hoặc biến môi trường `BIA_PG_DSN`.

---

## 🕸️ Trí nhớ "mạng nơ-ron"

Thay vì một danh sách phẳng, Bia lưu ký ức **như một mạng nơ-ron**:

- **Nơ-ron**: mỗi ký ức (hồ sơ / việc đã làm) và mỗi **khái niệm** (từ khóa) là một nơ-ron.
- **Synapse**: các nơ-ron nối nhau bằng liên kết **có trọng số**.
- **Học kiểu Hebb**: ký ức cùng xuất hiện thì liên kết mạnh lên ("fire together, wire together").
- **Nhớ lại = lan truyền kích hoạt**: câu hỏi làm sáng vài nơ-ron rồi lan tới ký ức liên quan — nên hỏi *"trình duyệt web"* vẫn lần ra được *"thích Firefox"*.

Khi bật Postgres, mỗi embedding lưu ở cột `halfvec(768)` (2 byte/chiều — nhẹ hơn
JSON ~8 lần) và tìm kiếm tương đồng chạy ngay trong DB bằng pgvector. Xem trong
pgAdmin4 qua các bảng `bia_neurons`, `bia_synapses`, `bia_feedback`.

---

## ⚠️ Ghi chú & hạn chế

- Ở chế độ wake word, **mic luôn bật để nghe tên** (chỉ xử lý khi có tiếng nói). Tắt qua menu chuột phải hoặc `wake_enabled: false`.
- `.venv/` không nằm trong repo — hãy tạo lại như phần Cài đặt.
- Dự án phát triển và thử nghiệm trên Linux.
