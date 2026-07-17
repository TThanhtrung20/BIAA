"""Lưu trí nhớ MẠNG NƠ-RON vào PostgreSQL + pgvector.

- Mỗi nơ-ron là một dòng trong bảng bia_neurons; embedding lưu ở cột kiểu
  halfvec(768) của pgvector: mỗi chiều chỉ 2 byte (nửa so với vector float32)
  -> "lưu dưới dạng bytes cho nhẹ", lại tìm kiếm vector ngay trong DB.
- Synapse (liên kết có trọng số) ở bảng bia_synapses.
- Phản hồi đồng ý/từ chối ở bảng bia_feedback.

Tìm kiếm tương đồng (cosine) chạy NGAY trong Postgres qua toán tử <=> nên không
cần kéo vector về Python. Lan truyền kích hoạt (spreading activation) chạy ở
Python trên các synapse lấy từ DB.

Nếu mất kết nối, các hàm ném PgError để lớp trên (memory.py) tự quay về JSON.
"""
from __future__ import annotations

import functools
import threading
import time

import psycopg2

from .neural_memory import (_MERGE_SIM, _SPREAD_DECAY, _W_MEM_CONCEPT,
                            _W_MEM_MEM, _concepts)

DIM = 768                       # số chiều embedding của nomic-embed-text
_MERGE_DIST = 1.0 - _MERGE_SIM  # khoảng cách cosine để coi 2 fact là một
_SKIP_ACTIONS = {"chat", "unknown"}
_CATEGORY_LABEL = {
    "ten": "Tên", "so_thich": "Sở thích", "thoi_quen": "Thói quen",
    "ca_nhan": "Cá nhân", "khac": "Khác",
}

_lock = threading.RLock()
_conn = None
_last_check = 0.0
_last_ok = False


class PgError(Exception):
    """Không dùng được Postgres (mất kết nối / lỗi) -> lớp trên fallback JSON."""


_SCHEMA = """
CREATE TABLE IF NOT EXISTS bia_neurons (
    id        BIGSERIAL PRIMARY KEY,
    kind      TEXT NOT NULL,
    content   TEXT NOT NULL,
    category  TEXT,
    fact_key  TEXT,
    action    TEXT,
    target    TEXT,
    hits      INTEGER NOT NULL DEFAULT 1,
    ts        DOUBLE PRECISION NOT NULL DEFAULT extract(epoch from now()),
    emb       halfvec({dim})
);
CREATE UNIQUE INDEX IF NOT EXISTS bia_concept_uq ON bia_neurons (content) WHERE kind = 'concept';
CREATE TABLE IF NOT EXISTS bia_synapses (
    a BIGINT NOT NULL REFERENCES bia_neurons(id) ON DELETE CASCADE,
    b BIGINT NOT NULL REFERENCES bia_neurons(id) ON DELETE CASCADE,
    w REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (a, b)
);
CREATE INDEX IF NOT EXISTS bia_syn_a ON bia_synapses (a);
CREATE TABLE IF NOT EXISTS bia_feedback (
    action TEXT NOT NULL,
    target TEXT NOT NULL,
    yes    INTEGER NOT NULL DEFAULT 0,
    no     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (action, target)
);
""".format(dim=DIM)


# --------------------------------------------------------------------------- #
# Kết nối
# --------------------------------------------------------------------------- #
def _load_cfg():
    from .config import Config
    return Config.load()


def _reset() -> None:
    global _conn
    try:
        if _conn is not None:
            _conn.close()
    except Exception:   # noqa: BLE001
        pass
    _conn = None


def _get():
    global _conn
    if _conn is None or _conn.closed:
        cfg = _load_cfg()
        _conn = psycopg2.connect(cfg.pg_dsn)
        _conn.autocommit = True
        _ensure_schema(_conn)
    return _conn


def _ensure_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        if not cur.fetchone():
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cur.execute(_SCHEMA)
        # Index vector (HNSW) để tìm cosine nhanh; bỏ qua nếu không tạo được
        try:
            cur.execute(
                "CREATE INDEX IF NOT EXISTS bia_emb_hnsw ON bia_neurons "
                "USING hnsw (emb halfvec_cosine_ops)")
        except psycopg2.Error:
            conn.rollback() if not conn.autocommit else None


def available() -> bool:
    """Có dùng được Postgres không (có bật + kết nối OK). Cache 5 giây."""
    global _last_check, _last_ok
    now = time.time()
    if now - _last_check < 5.0:
        return _last_ok
    _last_check = now
    with _lock:
        try:
            cfg = _load_cfg()
            if not getattr(cfg, "use_postgres", False):
                _last_ok = False
                return False
            conn = _get()
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            _last_ok = True
        except Exception:   # noqa: BLE001
            _reset()
            _last_ok = False
    return _last_ok


def _guard(fn):
    @functools.wraps(fn)
    def wrap(*args, **kwargs):
        with _lock:
            try:
                return fn(*args, **kwargs)
            except (psycopg2.OperationalError, psycopg2.InterfaceError) as exc:
                _reset()
                raise PgError(str(exc)) from exc
    return wrap


def _vec(emb) -> str | None:
    """Định dạng embedding thành literal cho halfvec, hoặc None nếu không hợp lệ."""
    if not emb or len(emb) != DIM:
        return None
    return "[" + ",".join(format(float(x), ".6g") for x in emb) + "]"


# --------------------------------------------------------------------------- #
# Ghi: nơ-ron + synapse (Hebbian)
# --------------------------------------------------------------------------- #
def _strengthen(cur, a: int, b: int, rate: float) -> None:
    if a == b:
        return
    for x, y in ((a, b), (b, a)):        # synapse hai chiều
        cur.execute(
            "INSERT INTO bia_synapses (a, b, w) VALUES (%s, %s, %s) "
            "ON CONFLICT (a, b) DO UPDATE SET "
            "w = LEAST(1.0::real, bia_synapses.w + %s * (1.0 - bia_synapses.w))",
            (x, y, rate, rate))


def _upsert_concept(cur, token: str) -> int:
    cur.execute("SELECT id FROM bia_neurons WHERE kind='concept' AND content=%s",
                (token,))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE bia_neurons SET hits = hits + 1 WHERE id = %s", (row[0],))
        return row[0]
    cur.execute(
        "INSERT INTO bia_neurons (kind, content, ts) VALUES ('concept', %s, %s) "
        "RETURNING id", (token, time.time()))
    return cur.fetchone()[0]


def _wire(cur, mem_id: int, text: str) -> None:
    """Nối nơ-ron ký ức tới các khái niệm + Hebbian tới ký ức chia sẻ khái niệm."""
    concept_ids = []
    for tok in dict.fromkeys(_concepts(text)):
        cid = _upsert_concept(cur, tok)
        concept_ids.append(cid)
        _strengthen(cur, mem_id, cid, _W_MEM_CONCEPT)
    if concept_ids:
        cur.execute(
            "SELECT DISTINCT s.b FROM bia_synapses s "
            "JOIN bia_neurons n ON n.id = s.b "
            "WHERE s.a = ANY(%s) AND n.kind IN ('fact','episode') AND s.b <> %s",
            (concept_ids, mem_id))
        for (other,) in cur.fetchall():
            _strengthen(cur, mem_id, other, _W_MEM_MEM)


@_guard
def add_interaction(text: str, action: str, target: str, emb) -> None:
    content = f"{text} {target}".strip() if target else text
    conn = _get()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO bia_neurons (kind, content, action, target, ts, emb) "
            "VALUES ('episode', %s, %s, %s, %s, %s::halfvec) RETURNING id",
            (content, action, target, time.time(), _vec(emb)))
        mem_id = cur.fetchone()[0]
        _wire(cur, mem_id, content)


@_guard
def remember_fact(value: str, category: str, key: str, emb) -> bool:
    value = (value or "").strip()
    if not value:
        return False
    vec = _vec(emb)
    conn = _get()
    with conn.cursor() as cur:
        found = None
        if key:
            cur.execute(
                "SELECT id FROM bia_neurons WHERE kind='fact' AND fact_key=%s "
                "AND category=%s LIMIT 1", (key, category))
            r = cur.fetchone()
            found = r[0] if r else None
        if found is None and vec is not None:
            cur.execute(
                "SELECT id, (emb <=> %s::halfvec) AS d FROM bia_neurons "
                "WHERE kind='fact' AND emb IS NOT NULL ORDER BY d LIMIT 1", (vec,))
            r = cur.fetchone()
            if r and r[1] is not None and float(r[1]) <= _MERGE_DIST:
                found = r[0]
        if found is not None:
            cur.execute(
                "UPDATE bia_neurons SET content=%s, category=%s, fact_key=%s, "
                "hits=hits+1, ts=%s" + (", emb=%s::halfvec" if vec else "") +
                " WHERE id=%s",
                ((value, category, key, time.time(), vec, found) if vec
                 else (value, category, key, time.time(), found)))
            _wire(cur, found, value)
            return True
        cur.execute(
            "INSERT INTO bia_neurons (kind, content, category, fact_key, ts, emb) "
            "VALUES ('fact', %s, %s, %s, %s, %s::halfvec) RETURNING id",
            (value, category, key, time.time(), vec))
        mem_id = cur.fetchone()[0]
        _wire(cur, mem_id, value)
        return True


# --------------------------------------------------------------------------- #
# Đọc: tìm theo vector + thói quen + phản hồi
# --------------------------------------------------------------------------- #
@_guard
def recall(query_emb, top_k: int = 3, min_score: float = 0.5) -> list[dict]:
    vec = _vec(query_emb)
    if vec is None:
        return []
    conn = _get()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT content, action, target, 1 - (emb <=> %s::halfvec) AS sim "
            "FROM bia_neurons WHERE kind='episode' AND emb IS NOT NULL "
            "ORDER BY emb <=> %s::halfvec LIMIT %s", (vec, vec, top_k))
        out = []
        for content, action, target, sim in cur.fetchall():
            if sim is not None and float(sim) >= min_score:
                out.append({"text": content, "action": action, "target": target})
        return out


@_guard
def recall_facts(query_emb, top_k: int = 3, min_score: float = 0.55) -> list[dict]:
    vec = _vec(query_emb)
    if vec is None:
        return []
    conn = _get()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT content, category, hits, 1 - (emb <=> %s::halfvec) AS sim "
            "FROM bia_neurons WHERE kind='fact' AND emb IS NOT NULL "
            "ORDER BY emb <=> %s::halfvec LIMIT %s", (vec, vec, top_k))
        return [{"value": c, "category": cat, "count": h}
                for c, cat, h, sim in cur.fetchall()
                if sim is not None and float(sim) >= min_score]


@_guard
def all_facts() -> list[dict]:
    conn = _get()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT content, category, fact_key, hits FROM bia_neurons "
            "WHERE kind='fact' ORDER BY hits DESC, ts DESC")
        return [{"value": c, "category": cat, "key": k, "count": h}
                for c, cat, k, h in cur.fetchall()]


@_guard
def habits(top_n: int = 5) -> list[tuple[str, int]]:
    conn = _get()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT action, target, COUNT(*) AS n FROM bia_neurons "
            "WHERE kind='episode' AND action IS NOT NULL AND action NOT IN ('chat','unknown') "
            "GROUP BY action, target ORDER BY n DESC LIMIT %s", (top_n,))
        out = []
        for action, target, n in cur.fetchall():
            target = (target or "").strip()
            key = f"{action}: {target}" if target else action
            out.append((key, int(n)))
        return out


@_guard
def record_feedback(action: str, target: str, approved: bool) -> None:
    if action in _SKIP_ACTIONS or not action:
        return
    col = "yes" if approved else "no"
    conn = _get()
    with conn.cursor() as cur:
        cur.execute(
            f"INSERT INTO bia_feedback (action, target, {col}) VALUES (%s, %s, 1) "
            f"ON CONFLICT (action, target) DO UPDATE SET {col} = bia_feedback.{col} + 1",
            (action, (target or "").strip()))


@_guard
def approval_rate(action: str, target: str):
    conn = _get()
    with conn.cursor() as cur:
        cur.execute("SELECT yes, no FROM bia_feedback WHERE action=%s AND target=%s",
                    (action, (target or "").strip()))
        r = cur.fetchone()
    if not r:
        return 0, 0, None
    yes, no = int(r[0]), int(r[1])
    total = yes + no
    return yes, no, (yes / total if total else None)


# --------------------------------------------------------------------------- #
# Nhớ lại theo LIÊN TƯỞNG: lan truyền kích hoạt qua mạng
# --------------------------------------------------------------------------- #
@_guard
def activate(query_emb, query_text: str, steps: int = 2, top_k: int = 5) -> list[dict]:
    conn = _get()
    energy: dict[int, float] = {}
    with conn.cursor() as cur:
        vec = _vec(query_emb)
        if vec is not None:
            cur.execute(
                "SELECT id, 1 - (emb <=> %s::halfvec) AS sim FROM bia_neurons "
                "WHERE emb IS NOT NULL ORDER BY emb <=> %s::halfvec LIMIT 20",
                (vec, vec))
            for nid, sim in cur.fetchall():
                if sim is not None and float(sim) > 0.30:
                    energy[nid] = max(energy.get(nid, 0.0), float(sim))
        tokens = list(dict.fromkeys(_concepts(query_text)))
        if tokens:
            cur.execute(
                "SELECT id FROM bia_neurons WHERE kind='concept' AND content = ANY(%s)",
                (tokens,))
            for (nid,) in cur.fetchall():
                energy[nid] = max(energy.get(nid, 0.0), 1.0)
        if not energy:
            return []

        total = dict(energy)
        frontier = dict(energy)
        for _ in range(max(1, steps)):
            ids = list(frontier.keys())
            cur.execute("SELECT a, b, w FROM bia_synapses WHERE a = ANY(%s)", (ids,))
            nxt: dict[int, float] = {}
            for a, b, w in cur.fetchall():
                nxt[b] = nxt.get(b, 0.0) + frontier[a] * float(w) * _SPREAD_DECAY
            for m, val in nxt.items():
                total[m] = total.get(m, 0.0) + val
            frontier = nxt
            if not frontier:
                break

        ids = list(total.keys())
        cur.execute(
            "SELECT id, kind, content, hits FROM bia_neurons WHERE id = ANY(%s)", (ids,))
        meta = {r[0]: (r[1], r[2], r[3]) for r in cur.fetchall()}

    scored = [(val, nid) for nid, val in total.items()
              if meta.get(nid, ("",))[0] in ("fact", "episode")]
    scored.sort(reverse=True)
    return [{"id": nid, "kind": meta[nid][0], "text": meta[nid][1],
             "count": meta[nid][2], "activation": round(val, 3)}
            for val, nid in scored[:top_k]]


# --------------------------------------------------------------------------- #
# Ngữ cảnh + tóm tắt + thống kê + xoá
# --------------------------------------------------------------------------- #
def build_context(query: str, query_emb) -> str:
    lines: list[str] = []
    shown: set[str] = set()

    chosen: list[dict] = []
    seen: set[str] = set()
    for f in recall_facts(query_emb, 3, 0.55) + all_facts()[:5]:
        v = f.get("value", "")
        if v and v not in seen:
            seen.add(v)
            chosen.append(f)
    if chosen:
        lines.append("Điều mình đã biết về người dùng:")
        for f in chosen[:6]:
            lines.append(f"- {f['value']}")
            shown.add(f["value"])

    assoc_lines: list[str] = []
    for node in activate(query_emb, query, 2, 8):
        t = node.get("text", "")
        if t and t not in shown:
            shown.add(t)
            assoc_lines.append(f"- {t}")
        if len(assoc_lines) >= 4:
            break
    if assoc_lines:
        lines.append("Liên tưởng tới (trí nhớ liên kết):")
        lines.extend(assoc_lines)

    top = habits(5)
    if top:
        lines.append("Thói quen thường dùng:")
        for key, count in top:
            lines.append(f"- {key} (đã làm {count} lần)")

    return "\n".join(lines)


@_guard
def stats() -> dict:
    conn = _get()
    with conn.cursor() as cur:
        cur.execute("SELECT kind, COUNT(*) FROM bia_neurons GROUP BY kind")
        by_kind = {"fact": 0, "episode": 0, "concept": 0}
        total = 0
        for kind, n in cur.fetchall():
            by_kind[kind] = int(n)
            total += int(n)
        cur.execute("SELECT COUNT(*) FROM bia_synapses")
        synapses = int(cur.fetchone()[0]) // 2
        cur.execute(
            "SELECT s.w, na.content, nb.content FROM bia_synapses s "
            "JOIN bia_neurons na ON na.id = s.a "
            "JOIN bia_neurons nb ON nb.id = s.b "
            "WHERE s.a < s.b ORDER BY s.w DESC LIMIT 5")
        top_links = [(float(w), a, b) for w, a, b in cur.fetchall()]
    return {"neurons": total, "by_kind": by_kind,
            "synapses": synapses, "top_links": top_links}


@_guard
def _episode_count() -> int:
    conn = _get()
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM bia_neurons WHERE kind='episode'")
        return int(cur.fetchone()[0])


def summary() -> str:
    facts = all_facts()
    ep = _episode_count()
    if not facts and not ep:
        return "Mình chưa ghi nhớ gì về bạn cả."

    lines = [f"📚 Mình đã ghi nhớ {ep} tương tác và {len(facts)} thông tin về bạn "
             f"(lưu trong PostgreSQL/pgvector)."]

    if facts:
        lines.append("\n🧑 Hồ sơ về bạn:")
        by_cat: dict[str, list[str]] = {}
        for f in facts:
            by_cat.setdefault(f.get("category", "khac"), []).append(f.get("value", ""))
        for cat, values in by_cat.items():
            label = _CATEGORY_LABEL.get(cat, cat)
            for v in values:
                lines.append(f"  • [{label}] {v}")

    top = habits(10)
    if top:
        lines.append("\n🔁 Thói quen nổi bật:")
        for key, count in top:
            lines.append(f"  • {key} — {count} lần")

    st = stats()
    if st["neurons"]:
        bk = st["by_kind"]
        lines.append(
            f"\n🧠 Mạng nơ-ron (Postgres): {st['neurons']} nơ-ron "
            f"({bk.get('fact', 0)} hồ sơ, {bk.get('episode', 0)} ký ức, "
            f"{bk.get('concept', 0)} khái niệm), {st['synapses']} liên kết.")
        for w, a, b in st["top_links"]:
            lines.append(f"    • {a} ↔ {b} ({w:.2f})")
    return "\n".join(lines)


@_guard
def clear() -> None:
    conn = _get()
    with conn.cursor() as cur:
        cur.execute("TRUNCATE bia_synapses, bia_neurons, bia_feedback RESTART IDENTITY")


@_guard
def forget_facts() -> None:
    conn = _get()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM bia_neurons WHERE kind='fact'")
