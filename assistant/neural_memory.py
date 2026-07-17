"""Trí nhớ liên tưởng kiểu MẠNG NƠ-RON (associative neural memory).

Ý tưởng: lưu ký ức GIỐNG NHƯ một mạng nơ-ron thay vì một danh sách phẳng.

- NƠ-RON (node): mỗi ký ức (fact / episode) và mỗi khái niệm (từ khoá) là một nơ-ron.
- SYNAPSE (edge): các nơ-ron nối nhau bằng liên kết CÓ TRỌNG SỐ (0..1).
- HỌC KIỂU HEBB: "các nơ-ron cùng kích hoạt sẽ nối chặt hơn" -> mỗi lần hai ký ức
  xuất hiện cùng nhau, synapse giữa chúng mạnh lên.
- NHỚ LẠI: LAN TRUYỀN KÍCH HOẠT (spreading activation) - câu hỏi kích hoạt vài
  nơ-ron, rồi kích hoạt lan qua các synapse tới những ký ức liên quan (dù diễn đạt khác).

Thuần thư viện chuẩn, lưu chung trong memory.json (khối 'net').
"""
from __future__ import annotations

import math
import re
import time

from .voice.wake import normalize as _denorm

# Trọng số synapse tăng theo luật Hebb có bão hoà: w += rate * (1 - w)
_W_MEM_CONCEPT = 0.5      # ký ức <-> khái niệm: nối mạnh
_W_MEM_MEM = 0.18        # ký ức <-> ký ức (đồng kích hoạt): nối vừa
_MERGE_SIM = 0.80        # >= ngưỡng này coi 2 fact là cùng một nơ-ron
_SPREAD_DECAY = 0.5      # mỗi bước lan truyền, kích hoạt yếu dần
_MAX_NODES = 3000        # trần số nơ-ron (cắt tỉa khi vượt)

# Từ dừng (đã bỏ dấu) - không tạo nơ-ron khái niệm cho chúng
_STOP = {
    "toi", "minh", "ban", "la", "va", "co", "khong", "cho", "cai", "nay", "do",
    "the", "mot", "nhung", "cac", "dc", "duoc", "o", "a", "oi", "voi", "de", "di",
    "len", "ra", "vao", "giup", "muon", "hay", "thi", "ma", "nhe", "nha", "con",
    "rat", "lam", "gi", "nhi", "um", "ve", "cua", "cung", "khi", "dang", "se",
    "da", "chi", "day", "kia", "bi", "cn", "nguoi", "dung",
}


# --------------------------------------------------------------------------- #
def ensure(net: dict) -> dict:
    net.setdefault("seq", 0)
    net.setdefault("nodes", {})
    net.setdefault("adj", {})
    return net


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _concepts(text: str) -> list[str]:
    """Rút các từ khoá (đã bỏ dấu) làm nơ-ron khái niệm."""
    toks = re.split(r"[^a-z0-9]+", _denorm(text or ""))
    out = []
    for t in toks:
        if len(t) >= 2 and t not in _STOP and not t.isdigit():
            out.append(t)
    return out


def _new_node(net: dict, kind: str, text: str, emb: list[float]) -> str:
    net["seq"] = int(net.get("seq", 0)) + 1
    nid = str(net["seq"])
    net["nodes"][nid] = {
        "kind": kind, "text": text, "emb": emb or [],
        "count": 1, "ts": time.time(),
    }
    return nid


def _strengthen(net: dict, a: str, b: str, rate: float) -> None:
    if a == b:
        return
    adj = net["adj"]
    for x, y in ((a, b), (b, a)):        # synapse hai chiều
        d = adj.setdefault(x, {})
        cur = d.get(y, 0.0)
        d[y] = min(1.0, cur + rate * (1.0 - cur))


def _find_similar_memory(net: dict, emb: list[float], kind: str,
                         thr: float) -> str | None:
    if not emb:
        return None
    best, best_id = thr, None
    for nid, n in net["nodes"].items():
        if n.get("kind") != kind:
            continue
        s = _cosine(emb, n.get("emb") or [])
        if s >= best:
            best, best_id = s, nid
    return best_id


def _find_concept(net: dict, token: str) -> str | None:
    for nid, n in net["nodes"].items():
        if n.get("kind") == "concept" and n.get("text") == token:
            return nid
    return None


def add_memory(net: dict, kind: str, text: str, emb: list[float]) -> str:
    """Thêm một ký ức vào mạng: tạo nơ-ron, nối tới khái niệm, và nối Hebbian
    tới các ký ức chia sẻ khái niệm (đồng kích hoạt). Trả về id nơ-ron ký ức."""
    ensure(net)
    nodes, adj = net["nodes"], net["adj"]

    # Gộp fact gần trùng vào cùng một nơ-ron (củng cố thay vì tạo mới)
    mid = _find_similar_memory(net, emb, kind, _MERGE_SIM) if kind == "fact" else None
    if mid:
        nodes[mid]["count"] = int(nodes[mid].get("count", 1)) + 1
        nodes[mid]["ts"] = time.time()
        nodes[mid]["text"] = text
        if emb:
            nodes[mid]["emb"] = emb
    else:
        mid = _new_node(net, kind, text, emb)

    # Nơ-ron khái niệm + synapse ký-ức <-> khái-niệm
    concept_ids = []
    for tok in dict.fromkeys(_concepts(text)):     # giữ thứ tự, bỏ trùng
        cid = _find_concept(net, tok)
        if cid is None:
            cid = _new_node(net, "concept", tok, [])
        else:
            nodes[cid]["count"] = int(nodes[cid].get("count", 1)) + 1
        concept_ids.append(cid)
        _strengthen(net, mid, cid, _W_MEM_CONCEPT)

    # Hebbian: nối ký ức mới với các ký ức khác đang nối cùng khái niệm
    partners: set[str] = set()
    for cid in concept_ids:
        for other in adj.get(cid, {}):
            if other != mid and nodes.get(other, {}).get("kind") in ("fact", "episode"):
                partners.add(other)
    for other in partners:
        _strengthen(net, mid, other, _W_MEM_MEM)

    _prune(net)
    return mid


def activate(net: dict, query_emb: list[float], query_text: str,
             steps: int = 2, top_k: int = 5) -> list[dict]:
    """LAN TRUYỀN KÍCH HOẠT: trả các nơ-ron ký ức liên quan nhất tới câu hỏi."""
    ensure(net)
    nodes, adj = net["nodes"], net["adj"]
    if not nodes:
        return []

    qtokens = set(_concepts(query_text))
    energy: dict[str, float] = {}
    for nid, n in nodes.items():
        a = 0.0
        if query_emb and n.get("emb"):
            c = _cosine(query_emb, n["emb"])
            if c > 0.30:
                a = c
        if n.get("kind") == "concept" and n.get("text") in qtokens:
            a = max(a, 1.0)
        if a > 0:
            energy[nid] = a

    if not energy:
        return []

    total = dict(energy)
    frontier = dict(energy)
    for _ in range(max(1, steps)):
        nxt: dict[str, float] = {}
        for nid, a in frontier.items():
            for m, w in adj.get(nid, {}).items():
                nxt[m] = nxt.get(m, 0.0) + a * w * _SPREAD_DECAY
        for m, val in nxt.items():
            total[m] = total.get(m, 0.0) + val
        frontier = nxt
        if not frontier:
            break

    scored = [
        (val, nid) for nid, val in total.items()
        if nodes[nid].get("kind") in ("fact", "episode")
    ]
    scored.sort(reverse=True)
    return [dict(nodes[nid], id=nid, activation=round(val, 3))
            for val, nid in scored[:top_k]]


def _prune(net: dict, max_nodes: int = _MAX_NODES) -> None:
    """Quên bớt khi mạng quá lớn: bỏ nơ-ron ít được kích hoạt / cô lập nhất."""
    nodes, adj = net["nodes"], net["adj"]
    if len(nodes) <= max_nodes:
        return
    # điểm giữ lại = count + số synapse (bậc). Bỏ những nơ-ron điểm thấp nhất.
    def keep_score(nid: str) -> tuple:
        degree = len(adj.get(nid, {}))
        n = nodes[nid]
        # ưu tiên giữ fact hơn concept/episode khi ngang điểm
        kind_rank = {"fact": 2, "episode": 1, "concept": 0}.get(n.get("kind"), 0)
        return (int(n.get("count", 1)) + degree, kind_rank, n.get("ts", 0))

    ordered = sorted(nodes, key=keep_score)
    for nid in ordered[: len(nodes) - max_nodes]:
        nodes.pop(nid, None)
        for m in adj.pop(nid, {}):
            adj.get(m, {}).pop(nid, None)


def stats(net: dict) -> dict:
    """Thống kê để người dùng xem 'bộ não' đã lớn cỡ nào."""
    ensure(net)
    nodes, adj = net["nodes"], net["adj"]
    kinds = {"fact": 0, "episode": 0, "concept": 0}
    for n in nodes.values():
        kinds[n.get("kind", "concept")] = kinds.get(n.get("kind", "concept"), 0) + 1
    synapses = sum(len(v) for v in adj.values()) // 2

    # vài liên kết mạnh nhất giữa các khái niệm/ký ức (để minh hoạ)
    seen, links = set(), []
    for a, nbrs in adj.items():
        for b, w in nbrs.items():
            key = tuple(sorted((a, b)))
            if key in seen:
                continue
            seen.add(key)
            links.append((w, nodes.get(a, {}).get("text", "?"),
                          nodes.get(b, {}).get("text", "?")))
    links.sort(reverse=True)
    return {
        "neurons": len(nodes),
        "by_kind": kinds,
        "synapses": synapses,
        "top_links": links[:5],
    }
