"""픽셀 격투 게임 — 진입점

옵션:
    python main.py              # 전체화면으로 실행 (기본)
    python main.py --window     # 창 모드 (2배)
"""
from __future__ import annotations

import sys

from game.app import Game


def main() -> None:
    fullscreen = "--window" not in sys.argv
    Game(fullscreen=fullscreen).run()


if __name__ == "__main__":
    main()