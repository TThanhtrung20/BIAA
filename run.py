#!/usr/bin/env python3
"""Điểm khởi chạy trợ lý.

Cách dùng:
    python3 run.py            # chế độ chat bằng chữ trong terminal
    python3 run.py mascot     # nhân vật mascot nổi trên desktop
                              # (tự dùng 3D nếu đã cấu hình mascot_model, không thì 2D)
"""
import os
import sys


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg in ("mascot", "--mascot", "-m"):
        from assistant.config import Config
        cfg = Config.load()
        qml = os.path.expanduser(cfg.mascot_qml or "")
        model = os.path.expanduser(cfg.mascot_model or "")
        if qml and os.path.exists(qml):
            from assistant.mascot.pet_animated import run as run_mascot_anim
            run_mascot_anim(cfg)           # mô hình có animation (balsam)
        elif model and os.path.exists(model):
            from assistant.mascot.pet3d import run as run_mascot_3d
            run_mascot_3d(cfg)             # mô hình 3D tĩnh (RuntimeLoader)
        else:
            from assistant.mascot.app import run as run_mascot_2d
            run_mascot_2d()                # nhân vật 2D vẽ tay
    else:
        from assistant.cli import run as run_cli
        run_cli()


if __name__ == "__main__":
    main()
