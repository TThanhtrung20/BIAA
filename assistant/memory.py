"""Trí nhớ agent: ghi nhớ + TỰ HỌC HỎI về người dùng.

Ba tầng trí nhớ, đều lưu local tại ~/.local/share/assistant/memory.json (riêng tư):

1. episodes  - nhật ký tương tác (kèm embedding) để truy hồi việc tương tự.
2. facts     - HỒ SƠ người dùng: thông tin lâu dài (tên, sở thích, thói quen...)
               do LLM tự trích xuất từ câu nói và gộp lại (không trùng lặp).
3. feedback  - học từ phản hồi: mỗi hành động được đồng ý/từ chối bao nhiêu lần.

Toàn bộ dùng thư viện chuẩn của Python (không cần numpy). Embedding tạo bởi
model nomic-embed-text qua Ollama.
"""
from __future__ import annotations

import json
import math
import os
import threading
import time
import urllib.error
import urllib.request
from collections import Counter

from . import neural_memory as nn
from . import pg_memory as pgmem
from .config import DATA_DIR, Config

MEMORY_PATH = os.path.join(DATA_DIR, "memory.json")


def _pg():
    """Trả module pg_memory nếu đang dùng được PostgreSQL, ngược lại None.

    Mọi hàm public sẽ ưu tiên Postgres; nếu mất kết nối (PgError) thì tự quay
    về lưu JSON để không gián đoạn.
    """
    try:
        return pgmem if pgmem.available() else None
    except Exception:   # noqa: BLE001
        return None

_MAX_EPISODES = 1000         # giữ tối đa ngần này tương tác gần nhất
_MAX_FACTS = 300             # giữ tối đa ngần này thông tin hồ sơ
_FACT_MERGE_SIM = 0.80       # >= ngưỡng này coi 2 fact là "cùng một điều" -> gộp
_SKIP_ACTIONS = {"chat", "unknown"}   # không tính vào thói quen / phản hồi

_CATEGORY_LABEL = {
    "ten": "Tên",
    "so_thich": "Sở thích",
    "thoi_quen": "Thói quen",
    "ca_nhan": "Cá nhân",
    "khac": "Khác",
}

_lock = threading.Lock()     # tránh 2 thread ghi đè file cùng lúc


# --------------------------------------------------------------------------- #
# Embedding + lưu trữ
# --------------------------------------------------------------------------- #
def _embed(text: str, cfg: Config) -> list[float]:
    url = f"{cfg.ollama_host}/api/embeddings"
    payload = {"model": cfg.embed_model, "prompt": text}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=cfg.request_timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body.get("embedding", [])


def _empty_store() -> dict:
    return {
        "version": 2, "episodes": [], "facts": [], "feedback": {},
        "net": {"seq": 0, "nodes": {}, "adj": {}},
    }


def _load() -> dict:
    if not os.path.exists(MEMORY_PATH):
        return _empty_store()
    try:
        with open(MEMORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return _empty_store()
    # Di trú định dạng cũ (một danh sách phẳng các tương tác)
    if isinstance(data, list):
        return {"version": 2, "episodes": data, "facts": [], "feedback": {}}
    if not isinstance(data, dict):
        return _empty_store()
    data.setdefault("version", 2)
    data.setdefault("episodes", [])
    data.setdefault("facts", [])
    data.setdefault("feedback", {})
    data.setdefault("net", {"seq": 0, "nodes": {}, "adj": {}})
    nn.ensure(data["net"])
    return data


def _save(store: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    store["episodes"] = store.get("episodes", [])[-_MAX_EPISODES:]
    store["facts"] = store.get("facts", [])[-_MAX_FACTS:]
    with open(MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _search(records: list[dict], q_emb: list[float], top_k: int,
            min_score: float) -> list[dict]:
    if not q_emb:
        return []
    scored = []
    for r in records:
        score = _cosine(q_emb, r.get("embedding") or [])
        if score >= min_score:
            scored.append((score, r))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [r for _, r in scored[:top_k]]


def _habits_from(episodes: list[dict], top_n: int) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for r in episodes:
        action = r.get("action")
        if action in _SKIP_ACTIONS or action is None:
            continue
        target = (r.get("target") or "").strip()
        key = f"{action}: {target}" if target else action
        counter[key] += 1
    return counter.most_common(top_n)


# --------------------------------------------------------------------------- #
# Tầng 1: nhật ký tương tác (episodes)
# --------------------------------------------------------------------------- #
def add_interaction(text: str, action: str, target: str, cfg: Config) -> None:
    """Ghi nhớ một tương tác. Bỏ qua mọi lỗi để không gián đoạn trải nghiệm."""
    try:
        emb = _embed(text, cfg)
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, ValueError):
        emb = []
    pg = _pg()
    if pg is not None:
        try:
            pg.add_interaction(text, action, target, emb)
            return
        except pg.PgError:
            pass
    with _lock:
        store = _load()
        store["episodes"].append({
            "text": text,
            "action": action,
            "target": target,
            "ts": time.time(),
            "embedding": emb,
        })
        # nạp vào mạng nơ-ron: câu nói kèm đích thao tác thành một nơ-ron ký ức
        mem_text = f"{text} {target}".strip() if target else text
        nn.add_memory(store["net"], "episode", mem_text, emb)
        _save(store)


def recall(query: str, cfg: Config, top_k: int = 3, min_score: float = 0.5) -> list[dict]:
    """Các tương tác cũ giống query nhất về ngữ nghĩa."""
    try:
        q = _embed(query, cfg)
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, ValueError):
        return []
    pg = _pg()
    if pg is not None:
        try:
            return pg.recall(q, top_k, min_score)
        except pg.PgError:
            pass
    store = _load()
    if not store["episodes"]:
        return []
    return _search(store["episodes"], q, top_k, min_score)


def habits(top_n: int = 5) -> list[tuple[str, int]]:
    """Các hành động lặp lại nhiều nhất (bỏ qua chat/unknown)."""
    pg = _pg()
    if pg is not None:
        try:
            return pg.habits(top_n)
        except pg.PgError:
            pass
    return _habits_from(_load()["episodes"], top_n)


# --------------------------------------------------------------------------- #
# Tầng 2: hồ sơ người dùng (facts) + TỰ HỌC HỎI
# --------------------------------------------------------------------------- #
def remember_fact(value: str, cfg: Config, category: str = "khac",
                  key: str = "") -> bool:
    """Ghi/gộp một thông tin lâu dài về người dùng.

    Nếu đã có fact rất giống (cùng key hoặc gần nghĩa) thì cập nhật + tăng đếm,
    ngược lại thêm mới. Trả True nếu có thay đổi.
    """
    value = (value or "").strip()
    if not value:
        return False
    try:
        emb = _embed(value, cfg)
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, ValueError):
        emb = []
    pg = _pg()
    if pg is not None:
        try:
            return pg.remember_fact(value, category, key, emb)
        except pg.PgError:
            pass
    with _lock:
        store = _load()
        facts = store["facts"]
        for f in facts:
            same_key = bool(key) and f.get("key") == key and f.get("category") == category
            sim = _cosine(emb, f.get("embedding") or []) if emb else 0.0
            if same_key or sim >= _FACT_MERGE_SIM:
                f["value"] = value
                f["count"] = int(f.get("count", 1)) + 1
                f["ts"] = time.time()
                if emb:
                    f["embedding"] = emb
                nn.add_memory(store["net"], "fact", value, emb)   # củng cố nơ-ron
                _save(store)
                return True
        facts.append({
            "category": category or "khac",
            "key": key,
            "value": value,
            "count": 1,
            "ts": time.time(),
            "embedding": emb,
        })
        nn.add_memory(store["net"], "fact", value, emb)
        _save(store)
        return True


def learn(text: str, cfg: Config) -> list[dict]:
    """Tự học: nhờ LLM trích thông tin lâu dài từ câu nói rồi lưu vào hồ sơ.

    Trả danh sách fact đã học được (có thể rỗng). Nuốt mọi lỗi.
    """
    from .llm import extract_facts
    try:
        facts = extract_facts(text, cfg)
    except Exception:   # noqa: BLE001
        return []
    learned = []
    for f in facts:
        if remember_fact(f["value"], cfg, category=f.get("category", "khac"),
                          key=f.get("key", "")):
            learned.append(f)
    return learned


def learn_async(text: str, cfg: Config) -> None:
    """Học ở thread nền để không làm chậm phản hồi cho người dùng."""
    if not getattr(cfg, "auto_learn", True):
        return
    threading.Thread(target=lambda: learn(text, cfg), daemon=True).start()


def recall_facts(query: str, cfg: Config, top_k: int = 3,
                 min_score: float = 0.55) -> list[dict]:
    try:
        q = _embed(query, cfg)
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, ValueError):
        return []
    pg = _pg()
    if pg is not None:
        try:
            return pg.recall_facts(q, top_k, min_score)
        except pg.PgError:
            pass
    store = _load()
    if not store["facts"]:
        return []
    return _search(store["facts"], q, top_k, min_score)


def all_facts() -> list[dict]:
    """Toàn bộ hồ sơ, sắp theo mức độ được nhắc nhiều + mới nhất."""
    pg = _pg()
    if pg is not None:
        try:
            return pg.all_facts()
        except pg.PgError:
            pass
    facts = list(_load()["facts"])
    facts.sort(key=lambda f: (int(f.get("count", 1)), f.get("ts", 0)), reverse=True)
    return facts


def forget_facts() -> None:
    """Xoá hồ sơ người dùng (giữ nguyên nhật ký tương tác)."""
    pg = _pg()
    if pg is not None:
        try:
            pg.forget_facts()
            return
        except pg.PgError:
            pass
    with _lock:
        store = _load()
        store["facts"] = []
        _save(store)


# --------------------------------------------------------------------------- #
# Tầng 3: học từ phản hồi (đồng ý / từ chối)
# --------------------------------------------------------------------------- #
def record_feedback(action: str, target: str, approved: bool) -> None:
    if action in _SKIP_ACTIONS or not action:
        return
    pg = _pg()
    if pg is not None:
        try:
            pg.record_feedback(action, target, approved)
            return
        except pg.PgError:
            pass
    with _lock:
        store = _load()
        key = f"{action}|{(target or '').strip()}"
        fb = store["feedback"].setdefault(key, {"yes": 0, "no": 0})
        fb["yes" if approved else "no"] += 1
        _save(store)


def approval_rate(action: str, target: str) -> tuple[int, int, float | None]:
    """Trả (số lần đồng ý, số lần từ chối, tỉ lệ đồng ý hoặc None nếu chưa có)."""
    pg = _pg()
    if pg is not None:
        try:
            return pg.approval_rate(action, target)
        except pg.PgError:
            pass
    store = _load()
    fb = store["feedback"].get(f"{action}|{(target or '').strip()}")
    if not fb:
        return 0, 0, None
    yes, no = int(fb.get("yes", 0)), int(fb.get("no", 0))
    total = yes + no
    return yes, no, (yes / total if total else None)


# --------------------------------------------------------------------------- #
# Ngữ cảnh cho LLM + tóm tắt cho người dùng
# --------------------------------------------------------------------------- #
def build_context(query: str, cfg: Config) -> str:
    """Ghép ngữ cảnh ngắn từ trí nhớ (hồ sơ + thói quen + việc tương tự)."""
    try:
        q = _embed(query, cfg)
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, ValueError):
        q = []
    pg = _pg()
    if pg is not None:
        try:
            return pg.build_context(query, q)
        except pg.PgError:
            pass

    store = _load()
    lines: list[str] = []
    shown: set[str] = set()

    # Hồ sơ: ưu tiên fact liên quan câu hỏi, thêm vài fact nổi bật
    chosen: list[dict] = []
    seen: set[str] = set()
    for f in _search(store["facts"], q, 3, 0.55) + all_facts()[:5]:
        v = f.get("value", "")
        if v and v not in seen:
            seen.add(v)
            chosen.append(f)
    if chosen:
        lines.append("Điều mình đã biết về người dùng:")
        for f in chosen[:6]:
            lines.append(f"- {f['value']}")
            shown.add(f["value"])

    # Liên tưởng qua MẠNG NƠ-RON: lan truyền kích hoạt tới ký ức liên quan
    assoc_lines: list[str] = []
    for node in nn.activate(store["net"], q, query, steps=2, top_k=8):
        t = node.get("text", "")
        if t and t not in shown:
            shown.add(t)
            assoc_lines.append(f"- {t}")
        if len(assoc_lines) >= 4:
            break
    if assoc_lines:
        lines.append("Liên tưởng tới (trí nhớ liên kết):")
        lines.extend(assoc_lines)

    # Thói quen
    top = _habits_from(store["episodes"], top_n=5)
    if top:
        lines.append("Thói quen thường dùng:")
        for key, count in top:
            lines.append(f"- {key} (đã làm {count} lần)")

    return "\n".join(lines)


def associations(query: str, cfg: Config, top_k: int = 6) -> list[dict]:
    """Các ký ức được 'liên tưởng' tới query qua mạng nơ-ron (spreading activation)."""
    try:
        q = _embed(query, cfg)
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, ValueError):
        q = []
    pg = _pg()
    if pg is not None:
        try:
            return pg.activate(q, query, 2, top_k)
        except pg.PgError:
            pass
    return nn.activate(_load()["net"], q, query, steps=2, top_k=top_k)


def net_stats() -> dict:
    """Thống kê mạng nơ-ron trí nhớ (số nơ-ron, synapse, liên kết mạnh nhất)."""
    pg = _pg()
    if pg is not None:
        try:
            return pg.stats()
        except pg.PgError:
            pass
    return nn.stats(_load()["net"])


def clear() -> None:
    """Xoá toàn bộ trí nhớ (nhật ký + hồ sơ + phản hồi), cả Postgres lẫn JSON."""
    pg = _pg()
    if pg is not None:
        try:
            pg.clear()
        except pg.PgError:
            pass
    with _lock:
        _save(_empty_store())


def summary() -> str:
    """Tóm tắt trí nhớ để người dùng xem/kiểm soát."""
    pg = _pg()
    if pg is not None:
        try:
            return pg.summary()
        except pg.PgError:
            pass
    store = _load()
    episodes = store["episodes"]
    facts = sorted(store["facts"],
                   key=lambda f: (int(f.get("count", 1)), f.get("ts", 0)), reverse=True)
    if not episodes and not facts:
        return "Mình chưa ghi nhớ gì về bạn cả."

    lines = [f"📚 Mình đã ghi nhớ {len(episodes)} tương tác và {len(facts)} thông tin về bạn."]

    if facts:
        lines.append("\n🧑 Hồ sơ về bạn:")
        # gom theo nhóm
        by_cat: dict[str, list[str]] = {}
        for f in facts:
            by_cat.setdefault(f.get("category", "khac"), []).append(f.get("value", ""))
        for cat, values in by_cat.items():
            label = _CATEGORY_LABEL.get(cat, cat)
            for v in values:
                lines.append(f"  • [{label}] {v}")

    top = _habits_from(episodes, top_n=10)
    if top:
        lines.append("\n🔁 Thói quen nổi bật:")
        for key, count in top:
            lines.append(f"  • {key} — {count} lần")

    # Mạng nơ-ron trí nhớ
    st = nn.stats(store["net"])
    if st["neurons"]:
        bk = st["by_kind"]
        lines.append(
            f"\n🧠 Mạng nơ-ron: {st['neurons']} nơ-ron "
            f"({bk.get('fact', 0)} hồ sơ, {bk.get('episode', 0)} ký ức, "
            f"{bk.get('concept', 0)} khái niệm), {st['synapses']} liên kết.")
        if st["top_links"]:
            lines.append("  Liên kết mạnh nhất:")
            for w, a, b in st["top_links"]:
                lines.append(f"    • {a} ↔ {b} ({w:.2f})")

    return "\n".join(lines)
