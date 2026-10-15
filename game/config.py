"""전역 상수"""
from __future__ import annotations

import pygame

# ---------------------------------------------------------------- 화면
SCREEN_W = 640
SCREEN_H = 360
FPS = 60
TITLE = "PIXEL DUEL"

# ---------------------------------------------------------------- 무대
FLOOR_Y = 300
# 캐릭터 이동 영역을 화면 밖으로 확장 (카메라가 따라가도록)
WALL_L = -80
WALL_R = SCREEN_W + 80

# ---------------------------------------------------------------- 카메라
CAMERA_SMOOTH = 0.08  # 카메라 이동 부드러움 (0~1, 작을수록 느림)
CAMERA_EDGE = 0.3     # 화면 가장자리 이 비율까지 오면 카메라 이동

# ---------------------------------------------------------------- 캐릭터
# 스프라이트 실루엣 높이를 이 값(월드 px)으로 정규화한다.
# 서로 해상도가 다른 스프라이트(162x122 / 32x61)도 같은 크기로Shown된다.
CHAR_H = 96

BODY_W = 26          # 히트박스 폭
BODY_H = CHAR_H      # 히트박스 높이 (입력 rect 는 CHAR_H 로 만든다)
CROUCH_H = int(CHAR_H * 0.68)

# ---------------------------------------------------------------- 물리 (px/s)
GRAVITY = 1900.0
WALK_SPEED = 160.0
BACK_SPEED = 120.0
JUMP_V = 470.0
GROUND_FRICTION = 0.80
AIR_FRICTION = 0.94

# ---------------------------------------------------------------- 전투
ROUND_TIME = 60          # 초
WINS_NEEDED = 2
MAX_ROUNDS = 99

# 넉백 감쇠 (히트스턴 중 속도 배율)
HITSTUN_FRICTION = 0.86
BLOCK_PUSH = 0.28

# ---------------------------------------------------------------- 입력
KEY_MAP = {
    # 이동/점프/방어
    "left": [pygame.K_LEFT, pygame.K_a],
    "right": [pygame.K_RIGHT, pygame.K_d],
    "up": [pygame.K_UP, pygame.K_w],
    "down": [pygame.K_DOWN, pygame.K_s],
    "block": [pygame.K_LSHIFT, pygame.K_RSHIFT, pygame.K_h],
    # 공격
    "light": [pygame.K_j, pygame.K_z],
    "heavy": [pygame.K_k, pygame.K_x],
    "special": [pygame.K_l, pygame.K_c],
    # 시스템
    "pause": [pygame.K_ESCAPE, pygame.K_p],
    "confirm": [pygame.K_RETURN, pygame.K_SPACE],
}

DIFFICULTY = {
    # 반응 프레임 / 방어 확률 / 공격 성향 / 스페셜 사용
    "easy":   dict(think=26, block=0.18, aggr=0.55, special=0.10, jump=0.10),
    "normal": dict(think=16, block=0.45, aggr=0.75, special=0.22, jump=0.30),
    "hard":   dict(think=8,  block=0.72, aggr=0.92, special=0.34, jump=0.55),
}