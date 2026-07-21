"""Module tự học nâng cao cho Bia.

5 tầng tự học:
1. PATTERN RECOGNITION  — nhận diện mẫu hành vi lặp lại (thời gian, chuỗi hành động)
2. PREFERENCE TRACKING  — theo dõi sở thích ẩn qua cách dùng từ, phản hồi, lựa chọn
3. META-LEARNING        — học cách học: cải thiện prompt trích xuất dựa trên kết quả
4. REFLECTION           — tự phản tỉnh: đánh giá chất lượng phản hồi của mình
5. ADAPTIVE BEHAVIOR    — điều chỉnh hành vi dựa trên feedback tích lũy

Lưu vào 2 bảng mới: bia_patterns, bia_preferences (Postgres) hoặc JSON fallback.
"""
from __future__ import annotations

import json
import math
import re
import threading
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field

from .config import Config

# --------------------------------------------------------------------------- #
# Hằng số
# --------------------------------------------------------------------------- #
_TIME_SLOTS = {
    "sang_som": (5, 8),     # 5h-8h
    "sang": (8, 11),        # 8h-11h
    "trua": (11, 14),       # 11h-14h
    "chieu": (14, 17),      # 14h-17h
    "toi": (17, 21),        # 17h-21h
    "khuya": (21, 5),       # 21h-5h (vượt ngày)
}

_MOOD_KEYWORDS = {
    "vui": ["haha", "hihi", "vui", "hay", "thích", "tuyệt", "cảm ơn", "ok", "oke"],
    "buồn": ["buồn", "chán", "mệt", "khó", "thất vọng", "tệ"],
    "gấp": ["nhanh", "gấp", "khẩn", "ngay", "lập tức", "mau"],
    "thân_mật": ["bạn", "ông", "bà", "mày", "tao", "bồ", "cưng"],
    "lịch_sự": ["anh", "chị", "ạ", "xin", "vui lòng", "giúp"],
}

_STYLE_MARKERS = {
    "ngắn_gọn": lambda t: len(t.split()) <= 5,
    "chi_tiết": lambda t: len(t.split()) >= 20,
    "có_dấu_hỏi": lambda t: "?" in t,
    "viết_hoa": lambda t: t == t.upper() and len(t) > 3,
    "dùng_emoji": lambda t: bool(re.search(r"[\U0001F600-\U0001F9FF]", t)),
}


# --------------------------------------------------------------------------- #
# Data classes
# --------------------------------------------------------------------------- #
@dataclass
class Pattern:
    """Mẫu hành vi được nhận diện."""
    kind: str              # "time", "sequence", "trigger"
    description: str       # mô tả tiếng Việt
    confidence: float      # 0.0 - 1.0
    occurrences: int       # số lần xuất hiện
    last_seen: float = 0.0 # timestamp
    metadata: dict = field(default_factory=dict)


@dataclass
class Preference:
    """Sở thích/ưu tiên được suy luận."""
    aspect: str            # "tone", "detail_level", "topic", "time_response"
    value: str             # giá trị cụ thể
    strength: float        # 0.0 - 1.0 (cao = rất chắc)
    evidence_count: int    # số bằng chứng
    last_updated: float = 0.0


# --------------------------------------------------------------------------- #
# 1. PATTERN RECOGNITION — nhận diện mẫu hành vi
# --------------------------------------------------------------------------- #
class PatternRecognizer:
    """Phát hiện pattern: thời gian sử dụng, chuỗi hành động, trigger ngữ cảnh."""

    def __init__(self):
        self._action_log: list[dict] = []  # {action, target, ts, hour, weekday}
        self._patterns: list[Pattern] = []

    def observe(self, action: str, target: str, text: str) -> None:
        """Ghi nhận một tương tác mới."""
        now = time.time()
        lt = time.localtime(now)
        self._action_log.append({
            "action": action, "target": target, "text": text,
            "ts": now, "hour": lt.tm_hour, "weekday": lt.tm_wday,
        })
        # Giữ tối đa 500 log gần nhất
        self._action_log = self._action_log[-500:]

    def analyze(self) -> list[Pattern]:
        """Phân tích toàn bộ log và trả danh sách pattern mới."""
        patterns = []
        patterns.extend(self._detect_time_patterns())
        patterns.extend(self._detect_sequence_patterns())
        patterns.extend(self._detect_weekday_patterns())
        self._patterns = patterns
        return patterns

    def _detect_time_patterns(self) -> list[Pattern]:
        """Phát hiện hành vi lặp theo khung giờ."""
        if len(self._action_log) < 5:
            return []
        slot_actions: dict[str, Counter] = defaultdict(Counter)
        for entry in self._action_log:
            slot = self._hour_to_slot(entry["hour"])
            key = f"{entry['action']}:{entry.get('target', '')}"
            slot_actions[slot][key] += 1

        patterns = []
        for slot, counter in slot_actions.items():
            for key, count in counter.most_common(3):
                if count >= 3:
                    action, target = key.split(":", 1)
                    patterns.append(Pattern(
                        kind="time",
                        description=f"Hay {action} '{target}' vào buổi {slot}",
                        confidence=min(1.0, count / 10),
                        occurrences=count,
                        last_seen=time.time(),
                        metadata={"slot": slot, "action": action, "target": target},
                    ))
        return patterns

    def _detect_sequence_patterns(self) -> list[Pattern]:
        """Phát hiện chuỗi hành động lặp (A rồi B)."""
        if len(self._action_log) < 6:
            return []
        pairs: Counter = Counter()
        for i in range(len(self._action_log) - 1):
            a = self._action_log[i]
            b = self._action_log[i + 1]
            # Chỉ tính nếu 2 hành động xảy ra trong 5 phút
            if b["ts"] - a["ts"] <= 300:
                pair = (a["action"], b["action"])
                pairs[pair] += 1

        patterns = []
        for (a, b), count in pairs.most_common(5):
            if count >= 3 and a != b:
                patterns.append(Pattern(
                    kind="sequence",
                    description=f"Sau '{a}' thường làm '{b}'",
                    confidence=min(1.0, count / 8),
                    occurrences=count,
                    last_seen=time.time(),
                    metadata={"first": a, "then": b},
                ))
        return patterns

    def _detect_weekday_patterns(self) -> list[Pattern]:
        """Phát hiện hành vi lặp theo ngày trong tuần."""
        if len(self._action_log) < 10:
            return []
        day_names = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]
        day_actions: dict[int, Counter] = defaultdict(Counter)
        for entry in self._action_log:
            key = f"{entry['action']}:{entry.get('target', '')}"
            day_actions[entry["weekday"]][key] += 1

        patterns = []
        for wday, counter in day_actions.items():
            for key, count in counter.most_common(2):
                if count >= 3:
                    action, target = key.split(":", 1)
                    patterns.append(Pattern(
                        kind="weekday",
                        description=f"Hay {action} '{target}' vào {day_names[wday]}",
                        confidence=min(1.0, count / 6),
                        occurrences=count,
                        last_seen=time.time(),
                        metadata={"weekday": wday, "action": action, "target": target},
                    ))
        return patterns

    @staticmethod
    def _hour_to_slot(hour: int) -> str:
        for slot, (start, end) in _TIME_SLOTS.items():
            if start <= end:
                if start <= hour < end:
                    return slot
            else:  # vượt ngày (khuya)
                if hour >= start or hour < end:
                    return slot
        return "khac"


# --------------------------------------------------------------------------- #
# 2. PREFERENCE TRACKING — suy luận sở thích ẩn
# --------------------------------------------------------------------------- #
class PreferenceTracker:
    """Theo dõi sở thích qua cách dùng từ, phản hồi, style."""

    def __init__(self):
        self._mood_log: list[dict] = []      # {mood, ts}
        self._style_log: list[dict] = []     # {style, ts}
        self._topic_log: list[str] = []      # chủ đề đã hỏi
        self._response_feedback: list[dict] = []  # {length, approved}
        self._preferences: list[Preference] = []

    def observe_text(self, text: str) -> None:
        """Phân tích văn phong từ tin nhắn của người dùng."""
        now = time.time()
        # Detect mood
        text_lower = text.lower()
        for mood, keywords in _MOOD_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                self._mood_log.append({"mood": mood, "ts": now})
                break

        # Detect style
        for style, check in _STYLE_MARKERS.items():
            if check(text):
                self._style_log.append({"style": style, "ts": now})

        # Track topic keywords (lấy 3 từ dài nhất)
        words = [w for w in re.split(r"\s+", text) if len(w) >= 3]
        words.sort(key=len, reverse=True)
        self._topic_log.extend(words[:3])

        # Giữ log nhẹ
        self._mood_log = self._mood_log[-200:]
        self._style_log = self._style_log[-200:]
        self._topic_log = self._topic_log[-500:]

    def observe_feedback(self, response_length: int, approved: bool) -> None:
        """Ghi nhận feedback để biết user thích phản hồi ngắn hay dài."""
        self._response_feedback.append({
            "length": response_length, "approved": approved, "ts": time.time()
        })
        self._response_feedback = self._response_feedback[-100:]

    def analyze(self) -> list[Preference]:
        """Tổng hợp sở thích từ dữ liệu quan sát."""
        prefs = []
        prefs.extend(self._infer_communication_style())
        prefs.extend(self._infer_mood_tendency())
        prefs.extend(self._infer_response_length_pref())
        prefs.extend(self._infer_topic_interests())
        self._preferences = prefs
        return prefs

    def _infer_communication_style(self) -> list[Preference]:
        """Suy luận phong cách giao tiếp ưa thích."""
        if len(self._style_log) < 5:
            return []
        counter = Counter(e["style"] for e in self._style_log[-50:])
        total = sum(counter.values())
        prefs = []
        for style, count in counter.most_common(3):
            ratio = count / total
            if ratio >= 0.3:
                desc_map = {
                    "ngắn_gọn": "Người dùng thích viết ngắn gọn, nên trả lời cô đọng",
                    "chi_tiết": "Người dùng hay viết chi tiết, có thể giải thích rõ hơn",
                    "có_dấu_hỏi": "Người dùng hay hỏi, nên chủ động giải thích",
                    "viết_hoa": "Người dùng hay VIẾT HOA, có thể đang nhấn mạnh/gấp",
                    "dùng_emoji": "Người dùng dùng emoji, nên thân thiện hơn",
                }
                prefs.append(Preference(
                    aspect="communication_style",
                    value=desc_map.get(style, style),
                    strength=min(1.0, ratio * 1.5),
                    evidence_count=count,
                    last_updated=time.time(),
                ))
        return prefs

    def _infer_mood_tendency(self) -> list[Preference]:
        """Nhận diện xu hướng cảm xúc gần đây."""
        if len(self._mood_log) < 3:
            return []
        recent = self._mood_log[-20:]
        counter = Counter(e["mood"] for e in recent)
        top_mood, count = counter.most_common(1)[0]
        if count >= 3:
            return [Preference(
                aspect="mood_tendency",
                value=f"Gần đây người dùng có xu hướng '{top_mood}'",
                strength=min(1.0, count / len(recent)),
                evidence_count=count,
                last_updated=time.time(),
            )]
        return []

    def _infer_response_length_pref(self) -> list[Preference]:
        """Suy luận: user thích phản hồi ngắn hay dài."""
        if len(self._response_feedback) < 5:
            return []
        approved = [f for f in self._response_feedback if f["approved"]]
        rejected = [f for f in self._response_feedback if not f["approved"]]
        if not approved:
            return []
        avg_approved = sum(f["length"] for f in approved) / len(approved)
        if avg_approved < 100:
            desc = "Người dùng thích phản hồi NGẮN (dưới 100 ký tự)"
        elif avg_approved > 300:
            desc = "Người dùng thích phản hồi CHI TIẾT (trên 300 ký tự)"
        else:
            desc = "Người dùng OK với phản hồi vừa phải"
        return [Preference(
            aspect="response_length",
            value=desc,
            strength=min(1.0, len(approved) / 10),
            evidence_count=len(approved),
            last_updated=time.time(),
        )]

    def _infer_topic_interests(self) -> list[Preference]:
        """Nhận diện chủ đề quan tâm nhiều nhất."""
        if len(self._topic_log) < 10:
            return []
        counter = Counter(self._topic_log[-200:])
        prefs = []
        for word, count in counter.most_common(5):
            if count >= 4:
                prefs.append(Preference(
                    aspect="topic_interest",
                    value=f"Người dùng quan tâm nhiều đến: {word}",
                    strength=min(1.0, count / 15),
                    evidence_count=count,
                    last_updated=time.time(),
                ))
        return prefs


# --------------------------------------------------------------------------- #
# 3. META-LEARNING — học cách học tốt hơn
# --------------------------------------------------------------------------- #
class MetaLearner:
    """Theo dõi hiệu quả trích xuất facts và cải thiện."""

    def __init__(self):
        self._extraction_results: list[dict] = []  # {text, facts_count, useful}
        self._failed_extractions: list[str] = []   # câu đáng ra phải học được

    def record_extraction(self, text: str, facts_count: int) -> None:
        """Ghi nhận kết quả trích xuất."""
        self._extraction_results.append({
            "text": text, "facts_count": facts_count, "ts": time.time(),
        })
        self._extraction_results = self._extraction_results[-200:]

    def record_missed_learning(self, text: str) -> None:
        """Ghi nhận câu mà lẽ ra phải học được nhưng bỏ sót."""
        self._failed_extractions.append(text)
        self._failed_extractions = self._failed_extractions[-50:]

    def get_extraction_rate(self) -> float:
        """Tỉ lệ câu nào trích được fact (effectiveness)."""
        if not self._extraction_results:
            return 0.0
        useful = sum(1 for r in self._extraction_results if r["facts_count"] > 0)
        return useful / len(self._extraction_results)

    def suggest_improvement(self) -> str | None:
        """Đề xuất cải thiện dựa trên meta-learning."""
        rate = self.get_extraction_rate()
        if rate < 0.1 and len(self._extraction_results) > 20:
            return "extraction_too_low"  # cần nới rộng prompt
        if rate > 0.8:
            return "extraction_too_high"  # có thể đang trích quá nhiều rác
        if len(self._failed_extractions) > 10:
            return "missed_patterns"  # có mẫu bỏ sót
        return None


# --------------------------------------------------------------------------- #
# 4. REFLECTION — tự phản tỉnh chất lượng phản hồi
# --------------------------------------------------------------------------- #
class Reflector:
    """Đánh giá chất lượng phản hồi qua feedback gián tiếp."""

    def __init__(self):
        self._interactions: list[dict] = []  # {query, response, followed_up, ts}
        self._quality_scores: list[float] = []

    def record_interaction(self, query: str, response: str) -> None:
        """Ghi nhận cặp hỏi-đáp."""
        self._interactions.append({
            "query": query, "response": response,
            "ts": time.time(), "followed_up": False,
        })
        self._interactions = self._interactions[-100:]

    def mark_follow_up(self) -> None:
        """User hỏi tiếp (cùng chủ đề) = phản hồi trước chưa đủ tốt."""
        if self._interactions:
            self._interactions[-1]["followed_up"] = True

    def get_quality_score(self) -> float:
        """Điểm chất lượng: % phản hồi không bị hỏi lại."""
        if len(self._interactions) < 5:
            return 0.5  # chưa đủ data
        recent = self._interactions[-30:]
        good = sum(1 for i in recent if not i["followed_up"])
        return good / len(recent)

    def get_weak_areas(self) -> list[str]:
        """Nhận diện lĩnh vực trả lời chưa tốt."""
        if len(self._interactions) < 10:
            return []
        followed = [i for i in self._interactions if i["followed_up"]]
        if not followed:
            return []
        # Tìm keyword chung trong các câu bị hỏi lại
        words: Counter = Counter()
        for i in followed:
            for w in re.split(r"\s+", i["query"]):
                if len(w) >= 3:
                    words[w.lower()] += 1
        return [w for w, c in words.most_common(5) if c >= 2]


# --------------------------------------------------------------------------- #
# 5. ADAPTIVE BEHAVIOR — điều chỉnh hành vi tổng hợp
# --------------------------------------------------------------------------- #
class AdaptiveBehavior:
    """Tổng hợp tất cả tầng học để đưa ra gợi ý hành vi."""

    def __init__(self):
        self.pattern_recognizer = PatternRecognizer()
        self.preference_tracker = PreferenceTracker()
        self.meta_learner = MetaLearner()
        self.reflector = Reflector()

    def observe(self, text: str, action: str, target: str,
                response: str = "") -> None:
        """Quan sát toàn diện một lượt tương tác."""
        self.pattern_recognizer.observe(action, target, text)
        self.preference_tracker.observe_text(text)
        if response:
            self.reflector.record_interaction(text, response)

    def observe_feedback(self, response_length: int, approved: bool) -> None:
        """Ghi nhận feedback."""
        self.preference_tracker.observe_feedback(response_length, approved)

    def observe_extraction(self, text: str, facts_count: int) -> None:
        """Ghi nhận kết quả trích xuất fact."""
        self.meta_learner.record_extraction(text, facts_count)

    def build_adaptive_context(self) -> str:
        """Tạo ngữ cảnh bổ sung cho LLM dựa trên tất cả tầng học."""
        lines: list[str] = []

        # Patterns
        patterns = self.pattern_recognizer.analyze()
        high_conf_patterns = [p for p in patterns if p.confidence >= 0.5]
        if high_conf_patterns:
            lines.append("Mẫu hành vi đã học:")
            for p in high_conf_patterns[:4]:
                lines.append(f"  - {p.description} (tin cậy: {p.confidence:.0%})")

        # Preferences
        prefs = self.preference_tracker.analyze()
        strong_prefs = [p for p in prefs if p.strength >= 0.4]
        if strong_prefs:
            lines.append("Sở thích/ưu tiên:")
            for p in strong_prefs[:4]:
                lines.append(f"  - {p.value}")

        # Reflection quality
        quality = self.reflector.get_quality_score()
        if quality < 0.6:
            weak = self.reflector.get_weak_areas()
            if weak:
                lines.append(f"Lưu ý: phản hồi về '{', '.join(weak[:3])}'"
                             " thường chưa đủ tốt, cần chi tiết hơn.")

        # Meta-learning suggestion
        suggestion = self.meta_learner.suggest_improvement()
        if suggestion == "extraction_too_low":
            lines.append("(Đang học chậm — cần chú ý hơn đến thông tin người dùng chia sẻ)")

        return "\n".join(lines)

    def predict_next_action(self) -> str | None:
        """Dự đoán hành động tiếp theo dựa trên pattern."""
        patterns = self.pattern_recognizer.analyze()
        now = time.localtime()
        slot = PatternRecognizer._hour_to_slot(now.tm_hour)

        # Tìm pattern thời gian phù hợp hiện tại
        for p in patterns:
            if (p.kind == "time" and p.confidence >= 0.6
                    and p.metadata.get("slot") == slot):
                return (f"Lúc này bạn hay {p.metadata['action']} "
                        f"'{p.metadata['target']}'. Có cần mình giúp không?")

        # Tìm pattern chuỗi
        log = self.pattern_recognizer._action_log
        if log:
            last_action = log[-1]["action"]
            for p in patterns:
                if (p.kind == "sequence" and p.confidence >= 0.6
                        and p.metadata.get("first") == last_action):
                    return (f"Sau '{last_action}' bạn hay làm "
                            f"'{p.metadata['then']}'. Mình làm luôn nhé?")
        return None

    def to_dict(self) -> dict:
        """Serialize state để lưu vào DB."""
        return {
            "action_log": self.pattern_recognizer._action_log[-100:],
            "mood_log": self.preference_tracker._mood_log[-50:],
            "style_log": self.preference_tracker._style_log[-50:],
            "topic_log": self.preference_tracker._topic_log[-100:],
            "response_feedback": self.preference_tracker._response_feedback[-50:],
            "extraction_results": self.meta_learner._extraction_results[-50:],
            "interactions": self.reflector._interactions[-30:],
        }

    def load_dict(self, data: dict) -> None:
        """Khôi phục state từ DB."""
        if not data:
            return
        self.pattern_recognizer._action_log = data.get("action_log", [])
        self.preference_tracker._mood_log = data.get("mood_log", [])
        self.preference_tracker._style_log = data.get("style_log", [])
        self.preference_tracker._topic_log = data.get("topic_log", [])
        self.preference_tracker._response_feedback = data.get("response_feedback", [])
        self.meta_learner._extraction_results = data.get("extraction_results", [])
        self.reflector._interactions = data.get("interactions", [])


# --------------------------------------------------------------------------- #
# Singleton toàn cục
# --------------------------------------------------------------------------- #
_instance: AdaptiveBehavior | None = None
_init_lock = threading.Lock()


def get_learner() -> AdaptiveBehavior:
    """Trả singleton AdaptiveBehavior, khởi tạo lần đầu."""
    global _instance
    if _instance is None:
        with _init_lock:
            if _instance is None:
                _instance = AdaptiveBehavior()
                _load_state(_instance)
    return _instance


# --------------------------------------------------------------------------- #
# Persistence — lưu/nạp state từ Postgres hoặc JSON
# --------------------------------------------------------------------------- #
def _load_state(learner: AdaptiveBehavior) -> None:
    """Nạp state từ DB hoặc JSON fallback."""
    try:
        from . import pg_memory as pgmem
        if pgmem.available():
            data = pgmem.load_learner_state()
            learner.load_dict(data)
            return
    except Exception:  # noqa: BLE001
        pass
    # JSON fallback
    import os
    from .config import DATA_DIR
    path = os.path.join(DATA_DIR, "learner_state.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                learner.load_dict(json.load(f))
        except (json.JSONDecodeError, OSError):
            pass


def save_state() -> None:
    """Lưu state hiện tại — gọi định kỳ hoặc khi thoát."""
    learner = get_learner()
    data = learner.to_dict()
    try:
        from . import pg_memory as pgmem
        if pgmem.available():
            pgmem.save_learner_state(data)
            return
    except Exception:  # noqa: BLE001
        pass
    # JSON fallback
    import os
    from .config import DATA_DIR
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, "learner_state.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError:
        pass


def save_state_async() -> None:
    """Lưu state ở background thread."""
    threading.Thread(target=save_state, daemon=True).start()
