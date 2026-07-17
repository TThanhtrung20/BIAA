# Hướng dẫn chạy BIAA trên máy nhà

## Yêu cầu cài sẵn
- Git
- Docker + Docker Compose
- Python 3.10+
- Ollama (https://ollama.com)

---

## Bước 1 — Pull code về

```bash
git clone https://github.com/TThanhtrung20/BIAA.git
cd BIAA
```

---

## Bước 2 — Khởi động PostgreSQL (database)

```bash
docker compose up -d
```

Chờ khoảng 10 giây, kiểm tra đã chạy chưa:

```bash
docker ps
```

Thấy `agent-postgres` là OK.

> **Lần đầu chạy:** Docker tự nạp `db/init/01_init.sql` (tạo bảng) và `db/init/02_data.sql` (nạp data) — tự động, không cần làm gì thêm.

---

## Bước 3 — Cài Python dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Bước 4 — Tải model Ollama

```bash
ollama pull qwen2.5-coder:7b
ollama pull nomic-embed-text
```

---

## Bước 5 — Tạo file config

```bash
mkdir -p ~/.config/assistant
cat > ~/.config/assistant/config.json << 'EOF'
{
  "ollama_host": "http://localhost:11434",
  "model": "qwen2.5-coder:7b",
  "embed_model": "nomic-embed-text",
  "language": "vi",
  "use_postgres": true,
  "pg_dsn": "host=localhost port=5432 dbname=agentdb user=agent password=agent_local_pw",
  "assistant_name": "Bia",
  "wake_words": ["bia", "bi a"],
  "wake_enabled": true,
  "auto_learn": true,
  "piper_voice": "/home/TEN_USER/Desktop/BIAA/assets/voices/vi_VN-vais1000-medium.onnx",
  "mascot_qml": "/home/TEN_USER/Desktop/BIAA/assets/robot_qml/Robot.qml"
}
EOF
```

> **Lưu ý:** Thay `TEN_USER` bằng tên user trên máy nhà (ví dụ: `/home/trung/Desktop/BIAA/...`)

---

## Bước 6 — Chạy app

```bash
source .venv/bin/activate
python run.py
```

---

## Khi muốn tắt database

```bash
docker compose down
```

---

## Backup database lần sau (trên máy công ty)

```bash
docker exec agent-postgres pg_dump -U agent agentdb --no-owner --no-acl --data-only \
  > db/init/02_data.sql
git add db/init/02_data.sql
git commit -m "backup: update database dump"
git push
```

---

## Thông tin kết nối database

| | |
|---|---|
| Host | localhost |
| Port | 5432 |
| Database | agentdb |
| Username | agent |
| Password | agent_local_pw |
