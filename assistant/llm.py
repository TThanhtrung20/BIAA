"""Bộ não LLM: dùng Ollama để chuyển câu nói của người dùng thành hành động.

Gọi Ollama qua HTTP (stdlib, không cần thư viện ngoài) và bắt buộc model trả về
JSON theo schema định sẵn.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from .config import Config
from .intents import CHAT, NO_CONFIRM_ACTIONS, UNKNOWN, VALID_ACTIONS, Intent

SYSTEM_PROMPT = """Bạn là Bia, một trợ lý ảo thân thiện chạy trên máy tính Linux.
Tên của bạn là Bia. Khi người dùng chào hoặc hỏi tên, hãy tự xưng là Bia.
Nhiệm vụ: đọc câu nói của người dùng (tiếng Việt) và chuyển thành MỘT hành động
dưới dạng JSON. CHỈ trả về JSON hợp lệ, không thêm bất kỳ chữ nào khác.

Schema bắt buộc:
{
  "action": "open_url | open_app | search_web | create_word | create_excel | create_powerpoint | get_datetime | web_answer | chat",
  "target": "đích của hành động",
  "reply": "một câu ngắn bằng tiếng Việt để xác nhận lại với người dùng",
  "needs_confirmation": true hoặc false
}

Quy tắc:
- "open_url": mở một trang web. target là URL đầy đủ (vd: https://www.youtube.com).
- "open_app": mở một ứng dụng trên máy. target là tên app (vd: firefox, calculator, files, terminal).
- "search_web": MỞ trình duyệt để người dùng TỰ xem kết quả tìm kiếm. target là từ khoá. Chỉ dùng khi người dùng nói rõ "mở/tìm trên web/google".
- "get_datetime": trả lời NGÀY/GIỜ/THỨ hiện tại. Dùng khi hỏi mấy giờ, hôm nay ngày mấy, thứ mấy. target để trống. needs_confirmation=false.
- "web_answer": Bia TỰ tra thông tin MỚI trên internet rồi trả lời (bản tin/tin tức mới nhất, luật mới, thời tiết, giá vàng/xăng, tỉ số, sự kiện đang diễn ra...). target là chủ đề cần tra (vd "luật giao thông mới", "thời tiết Hà Nội", để trống nếu hỏi bản tin chung). needs_confirmation=false.
- "create_word": soạn file Word. target là chủ đề/mô tả nội dung tài liệu.
- "create_excel": tạo file Excel. target là mô tả bảng dữ liệu cần tạo.
- "create_powerpoint": làm bài thuyết trình. target là chủ đề bài trình chiếu.
- "chat": chỉ trò chuyện/trả lời, không thao tác máy. Khi đó needs_confirmation=false.
- Mọi hành động thao tác máy hoặc tạo file thì needs_confirmation=true.
- reply LUÔN bằng tiếng Việt, thân thiện, dạng hỏi lại để người dùng chốt.

Ví dụ:
Người dùng: "mở youtube"
{"action":"open_url","target":"https://www.youtube.com","reply":"Bạn muốn mình mở YouTube đúng không?","needs_confirmation":true}

Người dùng: "mở máy tính tính toán"
{"action":"open_app","target":"calculator","reply":"Bạn muốn mình mở ứng dụng Máy tính đúng không?","needs_confirmation":true}

Người dùng: "mở google tìm cách nấu phở bò"
{"action":"search_web","target":"cách nấu phở bò","reply":"Bạn muốn mình mở trình duyệt tìm 'cách nấu phở bò' đúng không?","needs_confirmation":true}

Người dùng: "bây giờ mấy giờ rồi"
{"action":"get_datetime","target":"","reply":"","needs_confirmation":false}

Người dùng: "hôm nay ngày bao nhiêu, thứ mấy"
{"action":"get_datetime","target":"","reply":"","needs_confirmation":false}

Người dùng: "cho mình bản tin mới nhất hôm nay"
{"action":"web_answer","target":"","reply":"","needs_confirmation":false}

Người dùng: "có luật giao thông gì mới không"
{"action":"web_answer","target":"luật giao thông mới","reply":"","needs_confirmation":false}

Người dùng: "thời tiết Hà Nội hôm nay thế nào"
{"action":"web_answer","target":"thời tiết Hà Nội hôm nay","reply":"","needs_confirmation":false}

Người dùng: "soạn giúp tôi file word về lợi ích của việc đọc sách"
{"action":"create_word","target":"lợi ích của việc đọc sách","reply":"Bạn muốn mình soạn một file Word về 'lợi ích của việc đọc sách' đúng không?","needs_confirmation":true}

Người dùng: "tạo bảng excel quản lý chi tiêu hàng tháng"
{"action":"create_excel","target":"bảng quản lý chi tiêu hàng tháng","reply":"Bạn muốn mình tạo file Excel quản lý chi tiêu hàng tháng đúng không?","needs_confirmation":true}

Người dùng: "làm slide thuyết trình về biến đổi khí hậu"
{"action":"create_powerpoint","target":"biến đổi khí hậu","reply":"Bạn muốn mình làm bài thuyết trình về 'biến đổi khí hậu' đúng không?","needs_confirmation":true}

Người dùng: "chào bạn"
{"action":"chat","target":"","reply":"Chào bạn! Mình là Bia đây, mình giúp được gì cho bạn hôm nay?","needs_confirmation":false}

Người dùng: "bạn tên gì"
{"action":"chat","target":"","reply":"Mình tên là Bia, trợ lý ảo của bạn đây!","needs_confirmation":false}
"""


def parse_intent(text: str, cfg: Config, context: str = "") -> Intent:
    """Phân tích câu nói -> Intent. Không bao giờ ném lỗi ra ngoài."""
    user_content = text.strip()
    if context:
        user_content = (
            f"[Thông tin về người dùng]\n{context}\n\n[Câu nói]\n{text.strip()}"
        )

    try:
        data = _chat_json(cfg, SYSTEM_PROMPT, user_content)
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
        return Intent(
            action=UNKNOWN,
            reply=f"Mình không kết nối được tới Ollama. Kiểm tra 'ollama serve' giúp mình nhé. ({exc})",
            needs_confirmation=False,
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        return Intent(
            action=CHAT,
            reply="Xin lỗi, mình chưa hiểu ý bạn. Bạn nói rõ hơn được không?",
            needs_confirmation=False,
        )

    action = str(data.get("action", UNKNOWN)).strip()
    if action not in VALID_ACTIONS:
        action = UNKNOWN

    intent = Intent(
        action=action,
        target=str(data.get("target", "")).strip(),
        reply=str(data.get("reply", "")).strip(),
        needs_confirmation=bool(data.get("needs_confirmation", True)),
        raw=data,
    )
    if action in NO_CONFIRM_ACTIONS:
        intent.needs_confirmation = False
    return intent


def _chat_json(cfg: Config, system: str, user: str) -> dict:
    """Gọi Ollama /api/chat với format=json và trả về dict đã parse."""
    url = f"{cfg.ollama_host}/api/chat"
    payload = {
        "model": cfg.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=cfg.request_timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return json.loads(body["message"]["content"])


def _chat_text(cfg: Config, system: str, user: str, temperature: float = 0.3) -> str:
    """Gọi Ollama /api/chat trả về văn bản thường (không ép JSON)."""
    url = f"{cfg.ollama_host}/api/chat"
    payload = {
        "model": cfg.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {"temperature": temperature},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=cfg.request_timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body["message"]["content"]


def summarize_web(topic: str, titles: list[str], cfg: Config) -> str:
    """Tóm tắt các tiêu đề tin (lấy từ internet) thành câu trả lời ngắn, có kiểm soát."""
    headlines = "\n".join(f"- {t}" for t in titles)
    system = (
        "Bạn là Bia, trợ lý ảo tiếng Việt. Dưới đây là các tiêu đề tin tức MỚI vừa "
        "lấy từ internet. Câu trả lời của bạn sẽ được ĐỌC TO cho người dùng nghe, nên "
        "phải NGẮN GỌN: tối đa 3 câu, nói tự nhiên như đang kể, KHÔNG đánh số, KHÔNG "
        "liệt kê dài. Nêu 2-3 tin nổi bật nhất. CHỈ dựa trên các tiêu đề được cung cấp, "
        "TUYỆT ĐỐI không bịa thêm chi tiết."
    )
    user = f"Chủ đề người dùng hỏi: {topic or 'tin mới nhất'}\n\nCác tiêu đề:\n{headlines}"
    return _chat_text(cfg, system, user)


# --------------------------------------------------------------------------- #
# Sinh nội dung cho file Office
# --------------------------------------------------------------------------- #
_OFFICE_PROMPTS = {
    "word": """Bạn là trợ lý soạn thảo văn bản. Hãy soạn nội dung cho một tài liệu Word bằng tiếng Việt.
CHỈ trả về JSON hợp lệ, không thêm chữ nào khác, theo schema:
{
  "title": "tiêu đề tài liệu",
  "blocks": [
    {"type":"heading","text":"...","level":1},
    {"type":"paragraph","text":"..."},
    {"type":"bullets","items":["...","..."]}
  ]
}
Yêu cầu: nội dung mạch lạc, có 2-4 mục lớn (heading level 1), mỗi mục kèm đoạn văn
và/hoặc danh sách gạch đầu dòng. Viết tiếng Việt có dấu đầy đủ.""",

    "excel": """Bạn là trợ lý tạo bảng tính. Hãy tạo dữ liệu cho một bảng Excel bằng tiếng Việt.
CHỈ trả về JSON hợp lệ, không thêm chữ nào khác, theo schema:
{
  "sheet_name": "tên sheet ngắn",
  "headers": ["cột 1","cột 2","cột 3"],
  "rows": [["...", 123, "..."], ["...", 456, "..."]]
}
Yêu cầu: 3-6 cột hợp lý, 6-10 dòng dữ liệu mẫu. Các giá trị số hãy để dạng số
(không bọc trong dấu nháy).""",

    "powerpoint": """Bạn là trợ lý làm slide thuyết trình. Hãy tạo nội dung bài thuyết trình bằng tiếng Việt.
CHỈ trả về JSON hợp lệ, không thêm chữ nào khác, theo schema:
{
  "title": "tiêu đề bài",
  "subtitle": "phụ đề ngắn",
  "slides": [
    {"title":"tiêu đề slide","bullets":["ý 1","ý 2","ý 3"]}
  ]
}
Yêu cầu: 4-6 slide nội dung, mỗi slide 3-5 gạch đầu dòng ngắn gọn.""",
}


def generate_office_content(doc_type: str, topic: str, cfg: Config) -> dict:
    """Gọi LLM sinh nội dung có cấu trúc cho một loại file Office.

    doc_type: "word" | "excel" | "powerpoint".
    Trả về dict theo schema tương ứng (xem _OFFICE_PROMPTS).
    """
    system = _OFFICE_PROMPTS[doc_type]
    user = f"Chủ đề/yêu cầu: {topic}"
    return _chat_json(cfg, system, user)


# --------------------------------------------------------------------------- #
# Trích xuất "trí nhớ": rút thông tin lâu dài về người dùng để tự học hỏi
# --------------------------------------------------------------------------- #
_EXTRACT_PROMPT = """Bạn là bộ trích xuất trí nhớ cho trợ lý ảo tên Bia.
Từ câu nói của người dùng, hãy rút ra những THÔNG TIN LÂU DÀI đáng nhớ về họ:
tên, sở thích, thói quen, thông tin cá nhân, cách họ muốn được phục vụ.
TUYỆT ĐỐI BỎ QUA các mệnh lệnh nhất thời (mở app, tạo file, tìm kiếm...) vì chúng
không phải thông tin lâu dài.

CHỈ trả về JSON hợp lệ, không thêm chữ nào khác:
{"facts":[{"category":"ten|so_thich|thoi_quen|ca_nhan|khac","key":"khoá ngắn không dấu","value":"câu mô tả đầy đủ bằng tiếng Việt"}]}
Nếu không có gì đáng nhớ lâu dài, trả {"facts":[]}.

Ví dụ:
"tôi tên là Nam" -> {"facts":[{"category":"ten","key":"ten","value":"Người dùng tên là Nam"}]}
"tôi thích dùng firefox hơn chrome" -> {"facts":[{"category":"so_thich","key":"trinh_duyet","value":"Người dùng thích dùng trình duyệt Firefox hơn Chrome"}]}
"mình hay nghe nhạc lofi lúc làm việc" -> {"facts":[{"category":"thoi_quen","key":"nhac_lam_viec","value":"Người dùng hay nghe nhạc lofi khi làm việc"}]}
"nhớ giúp tôi thứ 6 tuần sau có hẹn nha sĩ" -> {"facts":[{"category":"ca_nhan","key":"hen_nha_si","value":"Thứ 6 tuần sau người dùng có hẹn nha sĩ"}]}
"mở youtube lên" -> {"facts":[]}
"tạo file excel chi tiêu" -> {"facts":[]}
"""


def extract_facts(text: str, cfg: Config) -> list[dict]:
    """Rút các thông tin lâu dài từ câu nói. Không bao giờ ném lỗi ra ngoài."""
    try:
        data = _chat_json(cfg, _EXTRACT_PROMPT, text.strip())
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError,
            json.JSONDecodeError, KeyError, TypeError):
        return []
    raw = data.get("facts", []) if isinstance(data, dict) else []
    out: list[dict] = []
    for f in raw:
        if not isinstance(f, dict):
            continue
        value = str(f.get("value", "")).strip()
        if not value:
            continue
        out.append({
            "category": (str(f.get("category", "khac")).strip() or "khac"),
            "key": str(f.get("key", "")).strip(),
            "value": value,
        })
    return out
