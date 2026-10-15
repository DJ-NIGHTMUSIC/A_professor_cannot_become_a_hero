"""표시 배율 검증 — 실제 창을 열지 않고 해상도별 계산만 확인"""
from __future__ import annotations

import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame  # noqa: E402

pygame.init()

SCREEN_W, SCREEN_H = 640, 360
SRC_AR = SCREEN_W / SCREEN_H


def plan(win_w: int, win_h: int) -> None:
    """game/app.py 의 _apply_display 계산과 동일"""
    ideal = min(win_w / SCREEN_W, win_h / SCREEN_H)
    whole = max(1, int(ideal))
    scale = float(whole) if ideal - whole < 0.05 else ideal

    vw = max(1, round(SCREEN_W * scale))
    vh = max(1, round(SCREEN_H * scale))

    ox = (win_w - vw) // 2
    oy = (win_h - vh) // 2
    # 실제 표시 영역의 가로세로비 (1.0 이면 균등)
    ar = vw / vh if vh else 0
    # 화면 점유율
    fill = (vw * vh) / (win_w * win_h) * 100
    # 확대율 (몇 배로 커졌는가)
    gain = vw / SCREEN_W

    print(f"{win_w}x{win_h:<5} scale={gain:5.2f}x  view={vw}x{vh}  "
          f"비율={ar:.3f}{'  균등' if abs(ar - SRC_AR) < 0.01 else '  !!!'}  "
          f"점유={fill:5.1f}%  위치=({ox},{oy})")


def main() -> None:
    print(f"내부 해상도 {SCREEN_W}x{SCREEN_H} (비율 {SRC_AR:.3f})")
    print()
    for sz in [(1920, 1080), (1600, 900), (1440, 900), (1366, 768),
               (1280, 720), (1152, 648), (1024, 768), (960, 540),
               (800, 600), (720, 480), (640, 360), (2560, 1440), (3840, 2160)]:
        plan(*sz)
    pygame.quit()


if __name__ == "__main__":
    main()