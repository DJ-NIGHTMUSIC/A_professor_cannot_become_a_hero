"""
전투 엔티티
===========
상태기계 + 물리 + 히트박스 판정.
양쪽 모두 같은 스프라이트 세트를 쓰고, 캐릭터마다 능력치만 다르다.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import pygame

from .character import Character
from .config import (
    AIR_FRICTION, BLOCK_PUSH, BODY_W, CROUCH_H, FLOOR_Y, GRAVITY,
    GROUND_FRICTION, HITSTUN_FRICTION, WALL_L, WALL_R,
)
from .sprites import Animation, get_animation

# 상태 상수
IDLE, WALK, CROUCH, JUMP, FALL, ATTACK, BLOCK, HURT, KO, WIN, SIT = range(11)

# 상태 → 애니메이션 폴더명
STATE_ANIM = {
    IDLE: "idle", WALK: "walk", CROUCH: "idle", JUMP: "idle", FALL: "idle",
    BLOCK: "idle", HURT: "idle", KO: "idle", WIN: "idle", ATTACK: "fight", SIT: "sit",
}


# ------------------------------------------------------------------ 무브
@dataclass
class Move:
    key: str
    name: str
    startup: int
    active: int
    recovery: int
    damage: float
    reach: float
    height: float
    box_top: float
    hitstun: int
    blockstun: int
    knockback: float
    launch: float
    hitstop: int
    self_x: float
    self_y: float
    cooldown: int
    invuln: int
    air_ok: bool
    crouch_ok: bool
    is_special: bool = False

    @property
    def total(self) -> int:
        return self.startup + self.active + self.recovery


def build_moves(ch: Character) -> dict[str, Move]:
    """캐릭터 능력치를 반영한 3技"""
    p = ch.arch.power
    r = ch.arch.reach
    return {
        "light": Move(
            "light", "JAB",
            4, 30, 8, 6 * p, 40 * r, 22, 50,
            13, 9, 280, 120, 5, 70, 0, 0, 0, True, True,
        ),
        "heavy": Move(
            "heavy", "SWING",
            6, 30, 14, 14 * p, 56 * r, 30, 38,
            21, 15, 500, 350, 8, 200, 0, 0, 0, True, False,
        ),
        "special": Move(
            "special", ch.arch.title + " BURST",
            10, 30, 22, 18 * p, 62 * r, 44, 32,
            26, 17, 650, 420, 10, 250, -260, 52, 3, False, False,
            is_special=True,
        ),
    }


# ------------------------------------------------------------------ 입력
@dataclass
class Intent:
    left: bool = False
    right: bool = False
    up: bool = False
    down: bool = False
    block: bool = False
    light: bool = False
    heavy: bool = False
    special: bool = False
    # 연타 대시용: 이번 프레임에 눌린 키
    pressed_left: bool = False
    pressed_right: bool = False

    @staticmethod
    def none() -> "Intent":
        return Intent()


# ------------------------------------------------------------------ 파티클
@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: int
    color: tuple[int, int, int]


class Fighter:
    """전투원 1명"""

    def __init__(self, ch: Character, slot: int, x: float):
        self.ch = ch
        self.slot = slot
        # 캐릭터 크기별로 애니메이션을캐시에서 가져온다 (스프라이트는 공유)
        self.anims: dict[str, Animation] = {
            "idle": get_animation("idle", ch.char_h),
            "walk": get_animation("walk", ch.char_h),
            "sit": get_animation("sit", ch.char_h),
            "fight": get_animation("fight", ch.char_h),
            "kick": get_animation("kick", ch.char_h),
        }

        self.x = x
        self.y = FLOOR_Y
        self.vx = 0.0
        self.vy = 0.0
        self.facing = 1 if slot == 1 else -1

        self.hp = float(ch.max_hp)
        self.state = IDLE
        self.state_frame = 0

        self.moves = build_moves(ch)
        self.move: Move | None = None
        self.move_frame = 0
        self.hit_used = False
        self.cooldown = {"light": 0, "heavy": 0, "special": 0}

        self.hitstun = 0
        self.blockstun = 0
        self.hitstop = 0
        self.flash = 0
        self.blocking = False
        self.wins = 0

        self.anim_name = "idle"
        self.anim_frame = 0
        self.anim_tick = 0
        self.particles: list[Particle] = []

        # 대시 관련
        self.dash_cooldown = 0
        self.last_left_time = -999
        self.last_right_time = -999
        self.DASH_WINDOW = 12  # 12프레임(0.2초) 이내 연타 시 대시
        self.DASH_SPEED_MULT = 2.5
        self.DASH_DURATION = 8
        self.dash_timer = 0
        self.dash_dir = 0

    # ------------------------------------------------------------ 상태
    @property
    def grounded(self) -> bool:
        return self.y >= FLOOR_Y - 0.5

    @property
    def alive(self) -> bool:
        return self.hp > 0

    @property
    def can_act(self) -> bool:
        # 공격 중이고 활성 프레임(주먹이 펼쳐진 상태)일 때는 행동 불가
        if self.state == ATTACK and self.move:
            t = self.move_frame
            if self.move.startup <= t < self.move.startup + self.move.active:
                return False
        return self.state not in (ATTACK, HURT, KO, SIT) and self.hitstun <= 0 and self.blockstun <= 0

    @property
    def body_w(self) -> float:
        """
        히트박스 폭. 캐릭터 키(x96) 대비 약 42%.
        push_apart 가 이 값을 최소 간격으로 쓰므로,
        이 이상 작아지면 두 캐릭터가 파고든다.
        """
        return self.ch.char_h * 0.42

    @property
    def body_h(self) -> float:
        return float(self.ch.char_h)

    def hurtbox(self) -> pygame.Rect:
        if self.state == SIT:
            # 회피 모션: 너비 고정, 높이만 낮게 (아래로 숙임)
            h = int(self.ch.char_h * 0.35)
            w = int(self.body_w)
            return pygame.Rect(int(self.x - w / 2), int(self.y - h), w, h)
        h = CROUCH_H * (self.ch.char_h / 96.0) if self.state == CROUCH else self.body_h
        w = self.body_w
        return pygame.Rect(int(self.x - w / 2), int(self.y - h), int(w), int(h))

    def hitbox(self) -> pygame.Rect | None:
        if not self.move or self.state != ATTACK:
            return None
        m = self.move
        t = self.move_frame
        if t < m.startup or t >= m.startup + m.active:
            return None
        s = self.ch.char_h / 96.0
        reach = m.reach * s
        # 팔이 앞으로 뻗으므로 판정 시작점을 몸통 앞쪽으로 밀어준다
        x = self.x + self.body_w * 0.5 if self.facing > 0 else self.x - self.body_w * 0.5 - reach
        return pygame.Rect(int(x), int(self.y - m.box_top * s), int(reach), int(m.height * s))

    # ------------------------------------------------------------ 행동
    def try_move(self, key: str, facing: int) -> bool:
        if not self.can_act or self.cooldown[key] > 0:
            return False
        m = self.moves[key]
        if not self.grounded and not m.air_ok:
            return False
        self.move = m
        self.state = ATTACK
        self.state_frame = 0
        self.move_frame = 0
        self.hit_used = False
        self.blocking = False
        self.facing = facing
        # heavy는 kick, 나머지는 fight
        self.anim_name = "kick" if key == "heavy" else "fight"
        self.anim_frame = 0
        self.anim_tick = 0
        self.vx *= 0.4
        return True

    def take_damage(self, dmg: float, from_x: float, m: Move) -> None:
        self.hp = max(0.0, self.hp - max(1.0, dmg * self.ch.arch.defense))
        d = 1 if self.x >= from_x else -1
        self.vx = d * m.knockback / self.ch.arch.weight
        self.vy = min(self.vy, 0) - m.launch / self.ch.arch.weight
        self.state = HURT
        self.state_frame = 0
        self.move = None
        self.hitstun = m.hitstun
        self.blockstun = 0
        self.blocking = False
        self.hitstop = m.hitstop
        self.flash = 4
        self.burst(int(self.x + d * 12), int(self.y - self.body_h * 0.55), 10, (255, 235, 190))
        if self.hp <= 0:
            self.state = KO
            self.hitstun = 0

    def take_block(self, from_x: float, m: Move) -> None:
        d = 1 if self.x >= from_x else -1
        self.vx = d * m.knockback / self.ch.arch.weight * BLOCK_PUSH
        self.blockstun = m.blockstun
        self.hitstop = 4
        self.burst(int(self.x - d * 14), int(self.y - self.body_h * 0.6), 8, (150, 210, 255))

    def burst(self, x: int, y: int, n: int, color) -> None:
        for _ in range(n):
            a = random.random() * math.tau
            sp = random.uniform(70, 240)
            self.particles.append(Particle(
                x, y, math.cos(a) * sp, math.sin(a) * sp, random.randint(8, 20), color,
            ))

    # ------------------------------------------------------------ 업데이트
    def update(self, it: Intent, foe: "Fighter") -> None:
        if self.hitstop > 0:
            self.hitstop -= 1
            return

        self.state_frame += 1
        self.flash = max(0, self.flash - 1)
        for k in self.cooldown:
            if self.cooldown[k] > 0:
                self.cooldown[k] -= 1
        if self.hitstun > 0:
            self.hitstun -= 1
        if self.blockstun > 0:
            self.blockstun -= 1
        self.step_particles()

        want = 1 if foe.x >= self.x else -1
        
        # 이동 방향 결정
        moving_left = it.left and not it.right
        moving_right = it.right and not it.left
        moving_backward = (moving_left and want > 0) or (moving_right and want < 0)
        
        if self.state not in (ATTACK, KO):
            # 뒤로 갈 때는 이동 방향을 향함 (키를 뗀 후에도 유지)
            if moving_backward and self.grounded and self.can_act:
                self.facing = -want
            elif not moving_backward:
                # 앞으로 갈 때는 상대를 향함 (키를 뗀 후에도 유지)
                self.facing = want

        if self.state == KO:
            self.physics()
            self.tick_anim("walk")
            return

        if self.state == HURT:
            self.physics()
            if self.hitstun <= 0 and self.grounded:
                self.state = IDLE
            self.tick_anim("walk")
            return

        if self.state == SIT:
            self.physics()
            anim = self.anims.get("sit")
            if anim and len(anim) >= 2:
                if it.down:
                    # 키 누름: sit_2 (앉은 자세)로 전환 및 유지
                    self.set_anim("sit")
                    self.anim_frame = 1
                    self.anim_tick = 0
                else:
                    # 키 뗌: sit_1 (중립)로 잠시 표시 후 IDLE
                    self.set_anim("sit")
                    self.anim_frame = 0
                    self.anim_tick = 0
                    self.state = IDLE
            return

        if self.state == ATTACK and self.move:
            self.tick_attack()
            return

        # ---- 자유 행동 ----
        # SIT/회피: 아래키(S) + 행동 가능 시
        if it.down and self.grounded and self.can_act:
            self.state = SIT
            self.state_frame = 0
            self.vx *= 0.2  # 회피 중 감속
            self.tick_anim("sit")
            return

        self.blocking = it.block and self.grounded and self.can_act
        if self.blocking:
            self.vx *= GROUND_FRICTION
            self.physics()
            self.tick_anim("idle")
            return

        if it.up and self.grounded and self.can_act:
            d = -1 if it.left else (1 if it.right else 0)
            self.vy = -self.ch.jump_v
            self.vx = d * self.ch.walk_speed * 0.9
            self.state = JUMP
            self.physics()
            self.tick_anim("idle")
            return

        if it.special and self.try_move("special", want):
            return
        if it.heavy and self.try_move("heavy", want):
            return
        if it.light and self.try_move("light", want):
            return

        # ---- 대시 감지 (연타) ----
        if self.grounded and self.can_act:
            # 왼쪽 대시
            if it.pressed_left:
                if self.state_frame - self.last_left_time <= self.DASH_WINDOW and self.last_left_time > 0:
                    self.dash_timer = self.DASH_DURATION
                    self.dash_dir = -1
                    self.vx = -self.ch.walk_speed * self.DASH_SPEED_MULT
                    self.state = WALK
                self.last_left_time = self.state_frame
            # 오른쪽 대시
            if it.pressed_right:
                if self.state_frame - self.last_right_time <= self.DASH_WINDOW and self.last_right_time > 0:
                    self.dash_timer = self.DASH_DURATION
                    self.dash_dir = 1
                    self.vx = self.ch.walk_speed * self.DASH_SPEED_MULT
                    self.state = WALK
                self.last_right_time = self.state_frame

        # 대시 타이머 감소
        if self.dash_timer > 0:
            self.dash_timer -= 1
            # 대시 중에도 방향 유지
            self.vx = self.dash_dir * self.ch.walk_speed * self.DASH_SPEED_MULT
            self.state = WALK
        else:
            self.dash_dir = 0

        if it.left != it.right:
            d = -1 if it.left else 1
            self.vx = d * self.ch.walk_speed * (0.78 if d != want else 1.0)
            self.state = WALK
        else:
            self.vx *= GROUND_FRICTION
            self.state = CROUCH if it.down else IDLE

        if not self.grounded:
            self.state = JUMP if self.vy < 0 else FALL

        self.physics()
        self.tick_anim("walk" if self.state == WALK else "idle")

    def tick_attack(self) -> None:
        m = self.move
        t = self.move_frame
        self.move_frame += 1

        # 공격 종류별 애니메이션 선택
        is_kick = (m.key == "heavy")
        anim_name = "kick" if is_kick else "fight"
        anim = self.anims.get(anim_name)

        if anim:
            if len(anim) >= 4:
                # 4프레임 공통: 1(중립) -> 2 -> 3(메인) -> 4(중립직전) -> 1
                if t < m.startup:
                    # 시작 전: 프레임 0 (중립)
                    self.set_anim(anim_name)
                    self.anim_frame = 0
                elif t < m.startup + m.active // 3:
                    # 활성 초반: 프레임 1 (준비)
                    self.set_anim(anim_name)
                    self.anim_frame = 1
                elif t < m.startup + 2 * m.active // 3:
                    # 활성 중반: 프레임 2 (메인 타격)
                    self.set_anim(anim_name)
                    self.anim_frame = 2
                elif t < m.startup + m.active:
                    # 활성 후반: 프레임 3 (중립 직전)
                    self.set_anim(anim_name)
                    self.anim_frame = 3
                else:
                    # 회복: 프레임 0 (중립)
                    self.set_anim(anim_name)
                    self.anim_frame = 0
            elif len(anim) >= 2:
                # 2프레임 폴백: 기존 로직
                if t < m.startup:
                    self.set_anim(anim_name)
                    self.anim_frame = 0
                elif t < m.startup + m.active:
                    self.set_anim(anim_name)
                    self.anim_frame = 1
                else:
                    self.set_anim(anim_name)
                    self.anim_frame = 0

        if m.startup <= t < m.startup + m.active:
            s = self.ch.char_h / 96.0
            self.vx = self.facing * m.self_x * s
            if m.self_y:
                self.vy = m.self_y * s

        self.physics()

        if self.move_frame >= m.total:
            self.cooldown[m.key] = m.cooldown
            self.move = None
            self.state = IDLE if self.grounded else (JUMP if self.vy < 0 else FALL)

    def physics(self) -> None:
        self.x += self.vx / 60.0
        self.y += self.vy / 60.0

        if not self.grounded:
            self.vy += GRAVITY / 60.0
            self.vx *= AIR_FRICTION
        else:
            self.vx *= GROUND_FRICTION
        if self.hitstun > 0:
            self.vx *= HITSTUN_FRICTION

        self.x = max(WALL_L, min(WALL_R, self.x))
        if self.y >= FLOOR_Y:
            self.y = FLOOR_Y
            self.vy = 0

    def step_particles(self) -> None:
        for p in self.particles:
            p.x += p.vx / 60.0
            p.y += p.vy / 60.0
            p.vy += 800 / 60.0
            p.life -= 1
        self.particles = [p for p in self.particles if p.life > 0]

    # ------------------------------------------------------------ 애니메이션
    def tick_anim(self, name: str) -> None:
        if self.anim_name != name:
            self.anim_name = name
            self.anim_frame = 0
            self.anim_tick = 0
        anim = self.anims[name]
        if len(anim) == 0:
            return
        self.anim_tick += 1
        if self.anim_tick >= anim.ticks[self.anim_frame]:
            self.anim_tick = 0
            self.anim_frame = (self.anim_frame + 1) % len(anim)

    def set_anim(self, name: str) -> None:
        """존재하지 않는 애니메이션이면 idle 로 폴백한다"""
        if name not in self.anims:
            name = "idle"
        if self.anim_name != name:
            self.anim_name = name
            self.anim_frame = 0
            self.anim_tick = 0

    # ------------------------------------------------------------ 렌더
    def draw(self, surf: pygame.Surface, cam: int = 0) -> None:
        if self.anim_name not in self.anims:
            self.anim_name = "idle"
        anim = self.anims[self.anim_name]
        fi = anim.frames[self.anim_frame % len(anim)]
        img = fi.surface
        w, h = img.get_size()

        # 카메라 오프셋 적용
        draw_x = self.x - cam

        # 그림자
        lift = min(1.0, max(0.0, (FLOOR_Y - self.y) / 120.0))
        sw = int(self.body_h * 0.40 * (1 - lift * 0.45))
        sh = max(2, int(3 - lift * 1.2))
        if sw > 2:
            shade = pygame.Surface((sw, sh), pygame.SRCALPHA)
            shade.fill((0, 0, 0, 110))
            surf.blit(shade, (int(draw_x - sw / 2), int(FLOOR_Y - sh + 1)))

        # 앵커 정렬: 머리 중심 = x, 발바닥 = y
        if self.facing < 0:
            img = pygame.transform.flip(img, True, False)
            ax = w - fi.head_px
        else:
            ax = fi.head_px
        rect = img.get_rect(topleft=(int(draw_x - ax), int(self.y - fi.foot_px)))

        if self.flash > 0:
            img = img.copy()
            img.fill((255, 255, 255, 0), None, pygame.BLEND_RGB_MAX)
        surf.blit(img, rect)

        for p in self.particles:
            if p.life % 4 < 2:
                surf.fill(p.color, (int(p.x - cam), int(p.y), 2, 2))


def push_apart(a: Fighter, b: Fighter) -> None:
    """두 캐릭터가 겹치지 않게 서로 밀어낸다 (공중일 때는 통과 허용)"""
    # 공중 상태(JUMP, FALL)일 때는 서로 통과 가능
    if a.state in (JUMP, FALL) or b.state in (JUMP, FALL):
        return
    gap = (a.body_w + b.body_w) / 2
    d = b.x - a.x
    if abs(d) >= gap:
        return
    s = 1 if d >= 0 else -1
    push = (gap - abs(d)) / 2
    a.x -= s * push
    b.x += s * push
    a.x = max(WALL_L, min(WALL_R, a.x))
    b.x = max(WALL_L, min(WALL_R, b.x))