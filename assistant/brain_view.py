"""Giao diện web xem trực quan mạng nơ-ron của Bia.

Chạy:
    python run.py brain

Sau đó mở trình duyệt: http://localhost:5050
"""
from __future__ import annotations

import json
import os

import psycopg2
from flask import Flask, jsonify, render_template

app = Flask(__name__, template_folder="templates")

# --------------------------------------------------------------------------- #
# Kết nối DB
# --------------------------------------------------------------------------- #
def _dsn() -> str:
    from .config import Config
    return Config.load().pg_dsn


def _conn():
    return psycopg2.connect(_dsn())


# --------------------------------------------------------------------------- #
# API endpoints
# --------------------------------------------------------------------------- #
@app.route("/")
def index():
    return render_template("brain.html")


@app.route("/api/graph")
def api_graph():
    """Trả toàn bộ nơ-ron + synapse dưới dạng {nodes, edges}."""
    try:
        con = _conn()
        with con.cursor() as cur:
            # Lấy nơ-ron (bỏ embedding cho nhẹ)
            cur.execute("""
                SELECT id, kind, content, category, hits,
                       to_timestamp(ts)::timestamp(0) AS time
                FROM bia_neurons
                ORDER BY ts DESC
                LIMIT 500
            """)
            cols = [d[0] for d in cur.description]
            neurons = [dict(zip(cols, row)) for row in cur.fetchall()]

            neuron_ids = {n["id"] for n in neurons}

            # Lấy synapse (chỉ 1 chiều a < b để tránh trùng)
            cur.execute("""
                SELECT a, b, w FROM bia_synapses
                WHERE a < b
                ORDER BY w DESC
                LIMIT 2000
            """)
            synapses = [
                {"from": a, "to": b, "w": round(float(w), 3)}
                for a, b, w in cur.fetchall()
                if a in neuron_ids and b in neuron_ids
            ]

        con.close()

        # Định màu theo kind
        color_map = {
            "fact":    {"background": "#4fc3f7", "border": "#0288d1"},
            "episode": {"background": "#a5d6a7", "border": "#388e3c"},
            "concept": {"background": "#ffcc80", "border": "#f57c00"},
        }

        nodes = []
        for n in neurons:
            kind = n["kind"]
            label = n["content"]
            if len(label) > 40:
                label = label[:37] + "..."
            nodes.append({
                "id":    n["id"],
                "label": label,
                "title": f"[{kind}] {n['content']}\nhits: {n['hits']}\n{n['time']}",
                "kind":  kind,
                "hits":  n["hits"],
                "color": color_map.get(kind, {"background": "#e0e0e0", "border": "#9e9e9e"}),
                "value": max(1, int(n["hits"])),   # kích thước node
            })

        edges = [
            {
                "from":  s["from"],
                "to":    s["to"],
                "value": s["w"],
                "title": f"w = {s['w']}",
            }
            for s in synapses
        ]

        return jsonify({"nodes": nodes, "edges": edges})

    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e), "nodes": [], "edges": []}), 500


@app.route("/api/stats")
def api_stats():
    """Thống kê nhanh."""
    try:
        con = _conn()
        with con.cursor() as cur:
            cur.execute("SELECT kind, COUNT(*) FROM bia_neurons GROUP BY kind")
            by_kind = {k: int(v) for k, v in cur.fetchall()}

            cur.execute("SELECT COUNT(*) FROM bia_synapses")
            synapses = int(cur.fetchone()[0]) // 2

            cur.execute("""
                SELECT content, hits FROM bia_neurons
                ORDER BY hits DESC LIMIT 10
            """)
            top = [{"content": c, "hits": h} for c, h in cur.fetchall()]

            cur.execute("""
                SELECT action, target, COUNT(*) n FROM bia_neurons
                WHERE kind='episode' AND action NOT IN ('chat','unknown')
                GROUP BY action, target ORDER BY n DESC LIMIT 10
            """)
            habits = [
                {"key": f"{a}: {t}".strip(": "), "count": int(n)}
                for a, t, n in cur.fetchall()
            ]

            cur.execute("SELECT COUNT(*) FROM conversation_memory")
            convs = int(cur.fetchone()[0])

        con.close()
        return jsonify({
            "by_kind": by_kind,
            "synapses": synapses,
            "top_neurons": top,
            "habits": habits,
            "conversations": convs,
        })
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500


@app.route("/api/conversations")
def api_conversations():
    """Lịch sử hội thoại gần nhất."""
    try:
        con = _conn()
        with con.cursor() as cur:
            cur.execute("""
                SELECT id, session_id, role, content,
                       created_at::timestamp(0) AS ts
                FROM conversation_memory
                ORDER BY created_at DESC
                LIMIT 50
            """)
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        con.close()
        # Chuyển datetime thành string
        for r in rows:
            r["ts"] = str(r["ts"])
        return jsonify(rows)
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def run(host: str = "0.0.0.0", port: int = 5050, debug: bool = False) -> None:
    print(f"\n🧠 Bia Brain Viewer đang chạy tại http://localhost:{port}\n")
    app.run(host=host, port=port, debug=debug)
