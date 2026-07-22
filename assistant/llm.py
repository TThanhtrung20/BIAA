"""Bộ não LLM: dùng Ollama để chuyển câu nói của người dùng thành hành động.

Gọi Ollama qua HTTP (stdlib, không cần thư viện ngoài) và bắt buộc model trả về
JSON theo schema định sẵn.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from .config import Config
from .intents import (CHAT, GET_DATETIME, NO_CONFIRM_ACTIONS, OPEN_ARTICLE,
                      PLAY_MUSIC, SCROLL, SET_VOLUME, UNKNOWN, VALID_ACTIONS,
                      Intent)
from .voice.wake import normalize as _norm

SYSTEM_PROMPT = """Bạn là Bia, một trợ lý ảo thân thiện chạy trên máy tính Linux.
Tên của bạn là Bia. Khi người dùng chào hoặc hỏi tên, hãy tự xưng là Bia.
Nhiệm vụ: đọc câu nói của người dùng (tiếng Việt) và chuyển thành MỘT hành động
dưới dạng JSON. CHỈ trả về JSON hợp lệ, không thêm bất kỳ chữ nào khác.

Schema bắt buộc:
{
  "action": "open_url | open_app | search_web | create_word | create_excel | create_powerpoint | get_datetime | web_answer | show_location | play_music | scroll | set_volume | open_article | chat",
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
- "show_location": mở VỊ TRÍ/ĐỊA ĐIỂM trên bản đồ (Google Maps). Dùng khi người dùng muốn XEM vị trí, đường đi, chỉ đường, tìm địa điểm cụ thể trên bản đồ. target là tên địa điểm/địa chỉ (vd "Hồ Gươm Hà Nội", "sân bay Tân Sơn Nhất"), hoặc để trống nếu muốn xem vị trí hiện tại. needs_confirmation=false.
- "play_music": PHÁT NHẠC hoặc video trên YouTube. Dùng khi người dùng muốn nghe nhạc, mở bài hát, phát video. target là tên bài hát/ca sĩ/từ khoá nhạc (vd "nhạc lofi", "Sơn Tùng MTP", "nhạc không lời thư giãn"), để trống nếu chỉ nói "mở nhạc" chung chung. needs_confirmation=false.
- "scroll": CUỘN màn hình lên hoặc xuống ở cửa sổ đang mở. Dùng khi người dùng nói lướt lên/xuống, cuộn lên/xuống, kéo lên/xuống. target là "up" (lên) hoặc "down" (xuống). needs_confirmation=false.
- "set_volume": CHỈNH ÂM LƯỢNG loa. Dùng khi người dùng nói tăng/giảm/to/nhỏ âm lượng, tắt/bật tiếng. target là "up" (tăng), "down" (giảm), "mute" (tắt tiếng), "unmute" (bật lại), hoặc số 0-100 để đặt mức cụ thể (vd "50"). needs_confirmation=false.
- "open_article": MỞ BÀI BÁO để đọc chi tiết, SAU KHI đã tra tin bằng web_answer. Dùng khi người dùng nói "mở/xem/đọc bài viết đó", "bài báo đó", "mở bài số 2", "cho tôi đọc tin đó". target là số thứ tự nếu có (vd "2"), để trống nếu là bài đầu/không rõ. needs_confirmation=false. LƯU Ý: "bài viết/bài báo/tin" là BÀI BÁO (open_article), KHÁC với "bài hát/nhạc" là NHẠC (play_music).
- "create_word": soạn file Word. target là chủ đề/mô tả nội dung tài liệu.
- "create_excel": tạo file Excel. target là mô tả bảng dữ liệu cần tạo.
- "create_powerpoint": làm bài thuyết trình. target là chủ đề bài trình chiếu.
- "chat": chỉ trò chuyện/trả lời, không thao tác máy. Khi đó needs_confirmation=false.
- Mọi hành động thao tác máy hoặc tạo file thì needs_confirmation=true.
- reply LUÔN bằng tiếng Việt, thân thiện, dạng hỏi lại để người dùng chốt.
- QUAN TRỌNG về NGỮ CẢNH: nếu có phần "[Thông tin về người dùng]" kèm "Cuộc trò chuyện gần đây", hãy DÙNG nó để hiểu các từ chỉ định như "cái đó", "bài viết đó", "chủ đề vừa nói", "tin đó", "nó". Hãy THAY chúng bằng nội dung cụ thể suy ra từ cuộc trò chuyện để điền vào "target". VD nếu vừa nói về tin "Mỹ và Iran ở Hormuz" và người dùng bảo "search bài viết đó", thì target là "Mỹ Iran Hormuz" chứ KHÔNG phải "bài viết đó".

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

Người dùng: "cho tôi xem bài viết đó đi"
{"action":"open_article","target":"","reply":"","needs_confirmation":false}

Người dùng: "mở bài báo số 2"
{"action":"open_article","target":"2","reply":"","needs_confirmation":false}

Người dùng: "đọc tin đó cho tôi"
{"action":"open_article","target":"","reply":"","needs_confirmation":false}

Người dùng: "thời tiết Hà Nội hôm nay thế nào"
{"action":"web_answer","target":"thời tiết Hà Nội hôm nay","reply":"","needs_confirmation":false}

Người dùng: "cho tôi xem vị trí Hồ Gươm trên bản đồ"
{"action":"show_location","target":"Hồ Gươm Hà Nội","reply":"","needs_confirmation":false}

Người dùng: "chỉ đường tới sân bay Tân Sơn Nhất"
{"action":"show_location","target":"sân bay Tân Sơn Nhất","reply":"","needs_confirmation":false}

Người dùng: "quán cà phê gần đây ở đâu"
{"action":"show_location","target":"quán cà phê gần đây","reply":"","needs_confirmation":false}

Người dùng: "mình đang ở đâu trên bản đồ"
{"action":"show_location","target":"","reply":"","needs_confirmation":false}

Người dùng: "mở nhạc cho tôi nghe"
{"action":"play_music","target":"","reply":"","needs_confirmation":false}

Người dùng: "phát bài của Sơn Tùng MTP"
{"action":"play_music","target":"Sơn Tùng MTP","reply":"","needs_confirmation":false}

Người dùng: "mở youtube phát nhạc lofi đi"
{"action":"play_music","target":"nhạc lofi","reply":"","needs_confirmation":false}

Người dùng: "lướt xuống dưới"
{"action":"scroll","target":"down","reply":"","needs_confirmation":false}

Người dùng: "cuộn lên trên giúp mình"
{"action":"scroll","target":"up","reply":"","needs_confirmation":false}

Người dùng: "kéo xuống tí nữa"
{"action":"scroll","target":"down","reply":"","needs_confirmation":false}

Người dùng: "tăng âm lượng lên"
{"action":"set_volume","target":"up","reply":"","needs_confirmation":false}

Người dùng: "nhỏ tiếng lại giúp mình"
{"action":"set_volume","target":"down","reply":"","needs_confirmation":false}

Người dùng: "tắt tiếng đi"
{"action":"set_volume","target":"mute","reply":"","needs_confirmation":false}

Người dùng: "để âm lượng 50 phần trăm"
{"action":"set_volume","target":"50","reply":"","needs_confirmation":false}

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


# --------------------------------------------------------------------------- #
# FAST-PATH: nhận diện lệnh phổ biến bằng luật (KHÔNG gọi LLM -> tức thì).
# Chỉ dùng cho các hành động an toàn, không cần xác nhận. Nếu không chắc -> None
# để LLM xử lý như bình thường.
# --------------------------------------------------------------------------- #
_GREETINGS = ("chao", "hello", "hi", "alo", "a lo", "hey", "xin chao", "bia")
_MUSIC_KW = ("mo nhac", "phat nhac", "nghe nhac", "bat nhac", "mo bai",
             "phat bai", "bat bai", "mo bai hat")

# Câu người dùng xưng tên / muốn được gọi là gì
_NAME_TRIGGERS = ("gọi mình là", "gọi tôi là", "gọi tớ là", "gọi em là",
                  "gọi anh là", "gọi chị là", "tôi tên là", "mình tên là",
                  "tớ tên là", "em tên là", "tên tôi là", "tên mình là",
                  "tên tớ là", "tên là")
_NAME_TAIL = {"nhé", "nha", "nhá", "ạ", "đi", "với", "nghe", "nhaa", "nhee"}


def _name_from(low: str) -> str:
    """Trích tên người dùng từ câu như 'gọi mình là Trung' (giữ nguyên dấu)."""
    for trig in _NAME_TRIGGERS:
        i = low.find(trig)
        if i < 0:
            continue
        rest = low[i + len(trig):].strip(" ,.!?")
        words = rest.split()
        while words and words[-1] in _NAME_TAIL:
            words = words[:-1]
        words = words[:4]                     # tên tối đa 4 từ
        if words:
            return " ".join(words).title()
    return ""


_MUSIC_STOP = {"cho", "tôi", "mình", "giúp", "đi", "nhé", "với", "nào", "ạ",
               "youtube", "trên", "hộ", "giùm", "dùm", "lên", "bài", "hát",
               "nhạc", "của", "bản", "mở", "bật", "phát", "nghe"}


# Ưu tiên: tên bài thường đứng SAU "bài"/"bài hát"; nếu không có thì sau "nhạc"...
_MUSIC_KEYS = ("bài hát", "bài", "bản nhạc", "nhạc", "bật", "phát", "nghe", "mở")


def _music_target(low: str) -> str:
    """Lấy tên bài/ca sĩ từ câu (giữ nguyên dấu, làm sạch dấu câu).

    Ưu tiên phần sau 'bài'/'bài hát' vì tên bài hát thường theo sau đó.
    VD: 'nghe nhạc, mở bài em của ngày hôm qua cho tôi' -> 'em của ngày hôm qua'
    """
    low = low.strip()
    seg = None
    for key in _MUSIC_KEYS:
        idx = low.rfind(key)          # vị trí xuất hiện cuối cùng
        if idx >= 0:
            seg = low[idx + len(key):]
            break
    if seg is None:
        return ""
    # tách từ, bỏ dấu câu bám quanh mỗi từ
    words = [w.strip(" ,.!?;:\"'()[]") for w in seg.split()]
    words = [w for w in words if w]
    # bỏ từ khoá/đệm ở đầu và cuối
    while words and words[0] in _MUSIC_STOP:
        words = words[1:]
    while words and words[-1] in _MUSIC_STOP:
        words = words[:-1]
    return " ".join(words)


def _strip_wake(raw: str) -> str:
    """Bỏ tiền tố gọi tên 'bia', 'bia ơi', 'a lô bia'... ở đầu câu."""
    t = _norm(raw)
    words = raw.split()
    tw = t.split()
    # bỏ 'a lo'/'alo' đứng đầu
    while tw and tw[0] in ("alo", "a", "lo", "ê", "e"):
        tw = tw[1:]; words = words[1:]
    # bỏ 'bia' + filler theo sau ('ơi', 'à', 'ê')
    if tw and tw[0] == "bia":
        tw = tw[1:]; words = words[1:]
        while tw and tw[0] in ("oi", "a", "à", "e", "ê", "nay", "ne"):
            tw = tw[1:]; words = words[1:]
    return " ".join(words).strip(" ,.!?")


def _fast_intent(text: str) -> Intent | None:
    raw = (text or "").strip()
    if not raw:
        return None

    # Bỏ tiền tố gọi tên: "bia mở nhạc" -> "mở nhạc"; "bia ơi" -> "" (chào)
    stripped = _strip_wake(raw)
    if not stripped:
        return Intent(action=CHAT, target="",
                      reply="Bia đây! Bạn cần mình giúp gì nào?",
                      needs_confirmation=False)
    raw = stripped
    low = raw.lower()
    t = _norm(raw)   # bỏ dấu, lowercase

    # 1) Cuộn màn hình
    if any(k in t for k in ("cuon", "luot", "keo")) or "scroll" in t:
        if any(k in t for k in ("xuong", "duoi", "down")):
            return Intent(action=SCROLL, target="down", needs_confirmation=False)
        if any(k in t for k in ("len", "tren", "up")):
            return Intent(action=SCROLL, target="up", needs_confirmation=False)

    # 2) Ngày/giờ
    if any(k in t for k in ("may gio", "gio roi", "ngay may", "ngay bao nhieu",
                            "thu may", "hom nay ngay", "hom nay la thu")):
        return Intent(action=GET_DATETIME, target="", needs_confirmation=False)

    # 2b) Âm lượng
    if any(k in t for k in ("am luong", "volume", "am thanh", "tieng")):
        if any(k in t for k in ("tat tieng", "cam tieng", "im lang", "mute")):
            return Intent(action=SET_VOLUME, target="mute", needs_confirmation=False)
        if any(k in t for k in ("bat tieng", "mo tieng", "unmute")):
            return Intent(action=SET_VOLUME, target="unmute", needs_confirmation=False)
        # Có số cụ thể -> đặt đúng mức đó (vd "tăng âm lượng lên 80")
        mnum = re.search(r"\b(\d{1,3})\b", t)
        if mnum:
            level = min(100, int(mnum.group(1)))
            return Intent(action=SET_VOLUME, target=str(level),
                          needs_confirmation=False)
        if any(k in t for k in ("tang", "to hon", "to len", "len", "cao hon", "lon hon")):
            return Intent(action=SET_VOLUME, target="up", needs_confirmation=False)
        if any(k in t for k in ("giam", "nho hon", "nho lai", "xuong", "thap hon")):
            return Intent(action=SET_VOLUME, target="down", needs_confirmation=False)
    # cách nói ngắn không kèm "âm lượng": "to lên"/"nhỏ lại"/"tắt tiếng"
    if "tat tieng" in t or "cam tieng" in t:
        return Intent(action=SET_VOLUME, target="mute", needs_confirmation=False)
    if any(p == t for p in ("to len", "to hon", "vặn to", "van to")):
        return Intent(action=SET_VOLUME, target="up", needs_confirmation=False)
    if any(p == t for p in ("nho lai", "nho hon", "van nho", "vặn nhỏ")):
        return Intent(action=SET_VOLUME, target="down", needs_confirmation=False)

    # 3) Xưng tên / muốn được gọi là gì -> xác nhận + ghi nhớ ngay
    name = _name_from(low)
    if name:
        return Intent(
            action=CHAT, target=name,
            reply=f"Rõ rồi, từ giờ mình sẽ gọi bạn là {name} nhé!",
            needs_confirmation=False)

    # 3b) Mở/đọc BÀI BÁO trong tin vừa tra (đặt TRƯỚC nhạc vì "mở bài viết"
    #     chứa "mở bài"). "bài viết/bài báo/tin đó/bài số N" -> open_article.
    if any(k in t for k in ("bai viet", "bai bao", "doc bai", "doc tin",
                            "bai so", "tin so")) or \
       (("tin do" in t or "bai do" in t) and
            any(v in t for v in ("mo", "xem", "doc", "coi"))):
        return Intent(action=OPEN_ARTICLE, target=raw, needs_confirmation=False)

    # 4) Phát nhạc
    if any(k in t for k in _MUSIC_KW):
        return Intent(action=PLAY_MUSIC, target=_music_target(low),
                      needs_confirmation=False)

    # 5) Chào hỏi -> trả lời cố định (không cần LLM)
    words = t.split()
    if words and words[0] in _GREETINGS and len(words) <= 4:
        return Intent(
            action=CHAT, target="",
            reply="Chào bạn! Mình là Bia đây, mình giúp được gì cho bạn?",
            needs_confirmation=False)

    return None


def parse_intent(text: str, cfg: Config, context: str = "") -> Intent:
    """Phân tích câu nói -> Intent. Không bao giờ ném lỗi ra ngoài.

    Thử fast-path bằng luật trước (tức thì); không khớp mới gọi LLM.
    """
    fast = _fast_intent(text)
    if fast is not None:
        return fast

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
        "keep_alive": "30m",     # giữ model trong RAM, tránh nạp lại mỗi lần (nhanh hơn)
        "options": {"temperature": 0.2, "num_predict": 256},  # JSON ngắn -> giới hạn output
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
_EXTRACT_PROMPT = """Bạn là bộ trích xuất trí nhớ NÂNG CAO cho trợ lý ảo tên Bia.
Nhiệm vụ: từ câu nói của người dùng, rút ra MỌI thông tin lâu dài đáng nhớ, bao gồm:

A. THÔNG TIN TƯỜNG MINH: tên, tuổi, nghề nghiệp, sở thích, thói quen.
B. SUY LUẬN NGẦM: thông tin không nói thẳng nhưng suy ra được.
   Ví dụ: "mở vscode lên" -> có thể suy ra người dùng là lập trình viên.
C. PHONG CÁCH GIAO TIẾP: viết tắt, dùng tiếng lóng, lịch sự/thân mật, ngắn/dài.
D. CẢM XÚC & TRẠNG THÁI: stress, vui, gấp, thư giãn (nếu rõ ràng).
E. ƯU TIÊN PHỤC VỤ: cách họ muốn được trả lời (ngắn gọn, chi tiết, có ví dụ...).

QUY TẮC:
- BỎ QUA mệnh lệnh nhất thời (mở app, tạo file, tìm kiếm) KHÔNG PHẢI thông tin lâu dài.
- Chỉ trích suy luận ngầm khi CÓ CĂN CỨ RÕ RÀNG, không bịa.
- Mỗi fact phải có confidence: "high" (rõ ràng) hoặc "medium" (suy luận hợp lý).
- Nếu không có gì đáng nhớ, trả {"facts":[]}.

CHỈ trả về JSON hợp lệ, không thêm chữ nào khác:
{"facts":[{"category":"ten|so_thich|thoi_quen|ca_nhan|nghe_nghiep|phong_cach|cam_xuc|uu_tien|khac","key":"khoá ngắn không dấu","value":"câu mô tả đầy đủ bằng tiếng Việt","confidence":"high|medium"}]}

Ví dụ:
"tôi tên là Nam, đang làm ở FPT" -> {"facts":[{"category":"ten","key":"ten","value":"Người dùng tên là Nam","confidence":"high"},{"category":"nghe_nghiep","key":"cong_ty","value":"Người dùng đang làm việc ở FPT","confidence":"high"}]}
"nhanh lên, deadline rồi" -> {"facts":[{"category":"cam_xuc","key":"trang_thai","value":"Người dùng đang gấp/áp lực deadline","confidence":"medium"},{"category":"uu_tien","key":"toc_do","value":"Người dùng ưu tiên phản hồi nhanh","confidence":"medium"}]}
"tôi thích dùng firefox hơn chrome" -> {"facts":[{"category":"so_thich","key":"trinh_duyet","value":"Người dùng thích dùng Firefox hơn Chrome","confidence":"high"}]}
"mình hay code python lúc tối" -> {"facts":[{"category":"thoi_quen","key":"code_toi","value":"Người dùng hay code Python vào buổi tối","confidence":"high"},{"category":"nghe_nghiep","key":"ngon_ngu","value":"Người dùng biết lập trình Python","confidence":"high"}]}
"trả lời ngắn thôi đừng dài dòng" -> {"facts":[{"category":"uu_tien","key":"do_dai","value":"Người dùng muốn được trả lời ngắn gọn, không dài dòng","confidence":"high"}]}
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
        confidence = str(f.get("confidence", "medium")).strip()
        out.append({
            "category": (str(f.get("category", "khac")).strip() or "khac"),
            "key": str(f.get("key", "")).strip(),
            "value": value,
            "confidence": confidence if confidence in ("high", "medium") else "medium",
        })
    return out
