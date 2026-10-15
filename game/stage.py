"""무대 · HUD 렌더 (픽셀 폰트 직접 구현)"""
from __future__ import annotations

import pygame

from .config import FLOOR_Y, SCREEN_H, SCREEN_W, WINS_NEEDED

# ------------------------------------------------------------------ 픽셀 폰트
# 3x5 글리프. 각 문자는 5줄의 3비트 문자열로 정의한다.
_GLYPHS: dict[str, tuple[str, ...]] = {
    "A": ("010", "101", "111", "101", "101"),
    "B": ("110", "101", "110", "101", "110"),
    "C": ("011", "100", "100", "100", "011"),
    "D": ("110", "101", "101", "101", "110"),
    "E": ("111", "100", "110", "100", "111"),
    "F": ("111", "100", "110", "100", "100"),
    "G": ("011", "100", "101", "101", "011"),
    "H": ("101", "101", "111", "101", "101"),
    "I": ("111", "010", "010", "010", "111"),
    "J": ("001", "001", "001", "101", "010"),
    "K": ("101", "101", "110", "101", "101"),
    "L": ("100", "100", "100", "100", "111"),
    "M": ("101", "111", "111", "101", "101"),
    "N": ("101", "111", "111", "111", "101"),
    "O": ("010", "101", "101", "101", "010"),
    "P": ("110", "101", "110", "100", "100"),
    "Q": ("010", "101", "101", "110", "011"),
    "R": ("110", "101", "110", "101", "101"),
    "S": ("011", "100", "010", "001", "110"),
    "T": ("111", "010", "010", "010", "010"),
    "U": ("101", "101", "101", "101", "111"),
    "V": ("101", "101", "101", "101", "010"),
    "W": ("101", "101", "111", "111", "101"),
    "X": ("101", "101", "010", "101", "101"),
    "Y": ("101", "101", "010", "010", "010"),
    "Z": ("111", "001", "010", "100", "111"),
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("110", "001", "010", "100", "111"),
    "3": ("111", "001", "011", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "110", "001", "110"),
    "6": ("011", "100", "111", "101", "111"),
    "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "110"),
    "-": ("000", "000", "111", "000", "000"),
    ":": ("000", "010", "000", "010", "000"),
    ".": ("000", "000", "000", "000", "010"),
    "/": ("001", "001", "010", "100", "100"),
    "!": ("010", "010", "010", "000", "010"),
    ">": ("100", "010", "001", "010", "100"),
    "<": ("001", "010", "100", "010", "001"),
    " ": ("000", "000", "000", "000", "000"),
    "_": ("000", "000", "000", "000", "111"),
}


def draw_text(surf, text: str, x: int, y: int, color, scale: int = 1) -> int:
    """3x5 픽셀 폰트. 반환값 = 그린 뒤 커서 x"""
    cx = x
    for ch in text.upper():
        g = _GLYPHS.get(ch)
        if g:
            for row, bits in enumerate(g):
                for col, b in enumerate(bits):
                    if b == "1":
                        surf.fill(color, (cx + col * scale, y + row * scale, scale, scale))
        cx += 4 * scale
    return cx


def text_width(text: str, scale: int = 1) -> int:
    return len(text) * 4 * scale


# ------------------------------------------------------------------ 무대
_bg_img: pygame.Surface | None = None

def _load_bg() -> pygame.Surface | None:
    """배경 이미지 로드 (캐시)"""
    global _bg_img
    if _bg_img is not None:
        return _bg_img
    from pathlib import Path
    bg_path = Path(__file__).parent.parent / "sprites" / "bg.png"
    if bg_path.exists():
        img = pygame.image.load(str(bg_path))
        # 640x360으로 스케일
        _bg_img = pygame.transform.scale(img, (640, 360))
    return _bg_img

def draw_stage(surf: pygame.Surface, cam: int = 0) -> None:
    w, h = surf.get_size()

    # 배경 이미지 사용 시 - 절대 잘리지 않도록 고정
    bg = _load_bg()
    if bg:
        # 배경은 카메라의 30%만큼만 움직임 (원경 효과)
        bg_cam = int(cam * 0.3)
        # 배경 이미지를 중앙에 고정 (화면 크기와 동일하게 스케일됨)
        surf.blit(bg, (0, 0))
        # 바닥 그림 - 절대 잘리지 않도록 카메라 오프셋 적용 안 함
        surf.fill("#1a1a2e", (0, FLOOR_Y, w, h - FLOOR_Y))
        surf.fill("#2a2a4a", (0, FLOOR_Y, w, 2))
        for tx in range(0, w, 26):
            surf.fill("#1e1e38", (tx, FLOOR_Y + 2, 1, h - FLOOR_Y - 2))
        for ty in range(FLOOR_Y + 7, h, 9):
            surf.fill("#1e1e38", (0, ty, w, 1))
        return

    # 폴백: 기존 프로그래밍 방식 배경
    # 하늘 (밴드)
    bands = ["#141021", "#1b1630", "#241a3d", "#2e2048", "#3a2552", "#472a58"]
    bh = (h // len(bands)) + 1
    for i, c in enumerate(bands):
        surf.fill(c, (0, i * bh, w, bh))

    # 원경 빌딩 (카메라 오프셋 적용 - 배경이 더 천천히 움직임)
    seed = 12345
    def rnd() -> float:
        nonlocal seed
        seed = (seed * 1103515245 + 12345) % 2147483648
        return seed / 2147483648

    # 배경은 카메라의 50%만큼만 움직임 (원경 효과)
    bg_cam = cam // 2
    x = -8 + bg_cam
    while x < w + 8 + abs(bg_cam):
        bw = int(18 + rnd() * 28)
        bh2 = int(40 + rnd() * 80)
        top = FLOOR_Y - 40 - bh2
        surf.fill("#0e0a18", (x, top, bw, FLOOR_Y - top))
        for wy in range(top + 5, FLOOR_Y - 46, 11):
            for wx in range(x + 4, x + bw - 4, 8):
                if rnd() > 0.55:
                    surf.fill("#3b2a5e", (wx, wy, 3, 4))
        x += bw + 4

    # 바닥 (카메라 오프셋 적용)
    floor_cam = cam
    surf.fill("#5a3a8f", (floor_cam, FLOOR_Y - 42, w, 1))
    surf.fill("#241a2e", (floor_cam, FLOOR_Y, w, h - FLOOR_Y))
    surf.fill("#3a2a48", (floor_cam, FLOOR_Y, w, 2))
    for tx in range(floor_cam, w + abs(floor_cam), 26):
        surf.fill("#2e2138", (tx, FLOOR_Y + 2, 1, h - FLOOR_Y - 2))
    for ty in range(FLOOR_Y + 7, h, 9):
        surf.fill("#2e2138", (0, ty, w, 1))


# ------------------------------------------------------------------ HUD
def _bar(surf, x, y, w, h, ratio, flip, color, back=(36, 26, 46)) -> None:
    surf.fill((21, 15, 30), (x - 2, y - 2, w + 4, h + 4))
    surf.fill(back, (x, y, w, h))
    fw = int(w * max(0.0, min(1.0, ratio)))
    bx = x + w - fw if flip else x
    surf.fill(color, (bx, y, fw, h))
    surf.fill(tuple(min(255, c + 40) for c in color), (bx, y, fw, 2))
    surf.fill("#0c0812", (x - 1, y - 1, w + 2, 1))
    surf.fill("#0c0812", (x - 1, y + h, w + 2, 1))


def draw_hud(surf, p1, p2, round_time: int, difficulty: str) -> None:
    bw, bh, y = 200, 10, 12
    c1, c2 = p1.ch.arch.ui_color, p2.ch.arch.ui_color

    _bar(surf, 14, y, bw, bh, p1.hp / p1.ch.max_hp, False, c1)
    _bar(surf, SCREEN_W - 14 - bw, y, bw, bh, p2.hp / p2.ch.max_hp, True, c2)

    white = (232, 226, 240)
    draw_text(surf, p1.ch.arch.title, 14, y + bh + 4, c1, 1)
    draw_text(surf, p1.ch.name, 14 + text_width(p1.ch.arch.title) + 8, y + bh + 4, white, 1)
    w2 = text_width(p2.ch.arch.title)
    draw_text(surf, p2.ch.arch.title, SCREEN_W - 14 - w2, y + bh + 4, c2, 1)
    draw_text(surf, p2.ch.name, SCREEN_W - 14 - w2 - 8 - text_width(p2.ch.name), y + bh + 4, white, 1)

    # 타이머
    t = str(max(0, round_time)).rjust(2, "0")
    draw_text(surf, t, SCREEN_W // 2 - text_width(t, 3) // 2, y - 4, (255, 212, 71), 3)

    # 라운드 승리 표시
    for i in range(WINS_NEEDED):
        on1 = i < p1.wins
        on2 = i < p2.wins
        surf.fill((255, 212, 71) if on1 else (58, 47, 74),
                  (SCREEN_W // 2 - 18 + i * 10, y + 22, 7, 7))
        surf.fill((255, 212, 71) if on2 else (58, 47, 74),
                  (SCREEN_W // 2 + 11 - i * 10, y + 22, 7, 7))

    # 조작 안내
    draw_text(surf, "A D MOVE   W JUMP   S CROUCH   H BLOCK   J K L ATTACK   ESC PAUSE",
              14, SCREEN_H - 16, (125, 116, 149), 1)
    draw_text(surf, f"AI: {difficulty.upper()}", SCREEN_W - 14 - text_width(f"AI: {difficulty.upper()}"),
              SCREEN_H - 16, (125, 116, 149), 1)


def draw_banner(surf, text: str, color, y: int = 96, scale: int = 4) -> None:
    x = SCREEN_W // 2 - text_width(text, scale) // 2
    draw_text(surf, text, x, y, color, scale)