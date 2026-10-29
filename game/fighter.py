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
            4, 6, 8, 6 * p, 40 * r, 22, 50,
            13, 9, 280, 120, 5, 70, 0, 0, 0, True, True,
        ),
        "heavy": Move(
            "heavy", "SWING",
            6, 8, 14, 14 * p, 56 * r, 30, 38,
            21, 15, 500, 350, 8, 200, 0, 0, 0, True, False,
        ),
        "special": Move(
            "special", ch.arch.title + " BURST",
            10, 10, 22, 18 * p, 62 * r, 44, 32,
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
        self.DASH_SPEED_MULT = 1.8
        self.DASH_DURATION = 8
        self.dash_timer = 0
        self.dash_dir = 0
        self.attack_buffer = {"light": 0, "heavy": 0, "special": 0}
        self.jump_buffer = 0

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
            h = int(self.ch.char_h * 0.35)
            w = int(self.body_w)
            return pygame.Rect(
                int(self.x - w / 2),
                int(self.y - h),
                w,
                h,
            )

        h = CROUCH_H * (self.ch.char_h / 96.0) if self.state == CROUCH else self.body_h
        w = self.body_w
        return pygame.Rect(
            int(self.x - w / 2),
            int(self.y - h),
            int(w),
            int(h),
        )
    def update(self, it: Intent, foe: "Fighter") -> None:
        if self.hitstop > 0:
            self.hitstop -= 1
            return

        self.state_frame += 1
        self.flash = max(0, self.flash - 1)

        for key in self.cooldown:
            if self.cooldown[key] > 0:
                self.cooldown[key] -= 1

        if self.hitstun > 0:
            self.hitstun -= 1
        if self.blockstun > 0:
            self.blockstun -= 1

        self.step_particles()
        want = 1 if foe.x >= self.x else -1

        moving_left = it.left and not it.right
        moving_right = it.right and not it.left
        moving_backward = (
            (moving_left and want > 0)
            or (moving_right and want < 0)
        )

        if self.state not in (ATTACK, KO):
            if moving_backward and self.grounded and self.can_act:
                self.facing = -want
            elif not moving_backward:
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
                    self.set_anim("sit")
                    self.anim_frame = 1
                    self.anim_tick = 0
                else:
                    self.set_anim("sit")
                    self.anim_frame = 0
                    self.anim_tick = 0
                    self.state = IDLE
            else:
                self.state = IDLE
            return

        if self.state == ATTACK and self.move:
            self.tick_attack(foe)
            return

        # 아래 방향키: 앉기
        if it.down and self.grounded and self.can_act:
            self.state = SIT
            self.state_frame = 0
            self.vx *= 0.2
            self.tick_anim("sit")
            return

        # 방어
        self.blocking = (
            it.block or (self.blocking and self.blockstun > 0)
        ) and self.grounded and (
            self.can_act or self.blockstun > 0
        )

        if self.blocking:
            self.vx *= GROUND_FRICTION
            self.physics()
            self.tick_anim("idle")
            return

        # 위 방향키: 점프
        if it.up and self.grounded and self.can_act:
            d = -1 if it.left else (1 if it.right else 0)
            self.vy = -self.ch.jump_v
            self.vx = d * self.ch.walk_speed * 0.9
            self.state = JUMP
            self.physics()
            self.tick_anim("idle")
            return

        # 공격
        for key in ("special", "heavy", "light"):
            if getattr(it, key) and self.try_move(key, want):
                return

        # 방향키 연타 대시
        if self.grounded and self.can_act:
            if it.pressed_left:
                if (
                    self.state_frame - self.last_left_time
                    <= self.DASH_WINDOW
                    and self.last_left_time > 0
                ):
                    self.dash_timer = self.DASH_DURATION
                    self.dash_dir = -1
                    self.vx = (
                        -self.ch.walk_speed * self.DASH_SPEED_MULT
                    )
                    self.state = WALK

                self.last_left_time = self.state_frame

            if it.pressed_right:
                if (
                    self.state_frame - self.last_right_time
                    <= self.DASH_WINDOW
                    and self.last_right_time > 0
                ):
                    self.dash_timer = self.DASH_DURATION
                    self.dash_dir = 1
                    self.vx = (
                        self.ch.walk_speed * self.DASH_SPEED_MULT
                    )
                    self.state = WALK

                self.last_right_time = self.state_frame

        if self.dash_timer > 0:
            self.dash_timer -= 1
            self.vx = (
                self.dash_dir
                * self.ch.walk_speed
                * self.DASH_SPEED_MULT
            )
            self.state = WALK
        else:
            self.dash_dir = 0

        if self.dash_timer > 0:
            self.state = WALK
        elif it.left != it.right:
            d = -1 if it.left else 1
            self.vx = d * self.ch.walk_speed * (
                0.78 if d != want else 1.0
            )
            self.state = WALK
        else:
            self.vx *= GROUND_FRICTION
            self.state = CROUCH if it.down else IDLE

        if not self.grounded:
            self.state = JUMP if self.vy < 0 else FALL

        self.physics()
        self.tick_anim(
            "walk" if self.state == WALK else "idle"
        )

    def tick_attack(self, foe: "Fighter") -> None:
        m = self.move
        t = self.move_frame
        self.move_frame += 1

        # 공격 종류별 애니메이션 선택
        is_kick = (m.key == "heavy")
        anim_name = "kick" if is_kick else "fight"
        anim = self.anims.get(anim_name)

        if anim:
            if len(anim) >= 4:
                # 시작 전: 중립 프레임
                if t < m.startup:
                    self.set_anim(anim_name)
                    self.anim_frame = 0

                # 활성 초반: 준비 프레임
                elif t < m.startup + m.active // 3:
                    self.set_anim(anim_name)
                    self.anim_frame = 1

                # 활성 중반: 공격 프레임
                elif t < m.startup + 2 * m.active // 3:
                    self.set_anim(anim_name)
                    self.anim_frame = 2

                # 활성 후반: 공격 마무리
                elif t < m.startup + m.active:
                    self.set_anim(anim_name)
                    self.anim_frame = 3

                else:
                    self.set_anim(anim_name)
                    self.anim_frame = 0

            else:
                self.tick_anim(anim_name)

        # 공격이 끝났으면 상태 초기화
        if self.move_frame >= m.total:
            self.move = None
            self.move_frame = 0
            self.hit_used = False

            if self.alive:
                self.state = IDLE
                self.state_frame = 0

            self.vx *= 0.5
            self.tick_anim("idle")
            return

        # 활성 프레임에 공격 판정
        if (
            m.startup <= t < m.startup + m.active
            and not self.hit_used
        ):
            if self.try_hit(foe, m):
                self.hit_used = True

    def try_move(self, key: str, want: int) -> bool:
        m = self.moves[key]

        if self.cooldown[key] > 0:
            return False

        if not self.grounded and not m.air_ok:
            return False

        if self.state == CROUCH and not m.crouch_ok:
            return False

        self.move = m
        self.move_frame = 0
        self.hit_used = False
        self.state = ATTACK
        self.state_frame = 0
        self.facing = want
        self.vx = m.self_x * want
        self.vy = m.self_y
        self.cooldown[key] = m.cooldown

        return True

    def try_hit(self, foe: "Fighter", m: Move) -> bool:
        if not foe.alive:
            return False

        # 공격 방향과 상대 위치 확인
        dx = foe.x - self.x
        if dx * self.facing < 0:
            return False

        if abs(dx) > m.reach + foe.body_w / 2:
            return False

        # 높이 판정
        attack_y = self.y - m.box_top
        foe_top = foe.y - foe.body_h

        if attack_y < foe.y - m.height:
            return False

        if attack_y > foe.y:
            return False

        # 방어 중이면 피해 감소
        if foe.blocking and foe.grounded:
            foe.blockstun = m.blockstun
            foe.vx = self.facing * BLOCK_PUSH
            foe.hitstop = m.hitstop
            foe.state = BLOCK
            foe.state_frame = 0
            foe.hp = max(0, foe.hp - m.damage * 0.15)
            foe.flash = 3
            return True

        # 일반 피격
        foe.hp = max(0, foe.hp - m.damage)
        foe.hitstun = m.hitstun
        foe.vx = self.facing * m.knockback
        foe.vy = -m.launch
        foe.hitstop = m.hitstop
        foe.state = HURT if foe.hp > 0 else KO
        foe.state_frame = 0
        foe.flash = 6

        self.hitstop = m.hitstop
        foe.spawn_hit_particles()

        return True
    def physics(self) -> None:
        """중력, 이동, 바닥 및 벽 충돌 처리."""
        if not self.grounded or self.vy < 0:
            self.vy += GRAVITY
            self.y += self.vy

        if self.y >= FLOOR_Y:
            self.y = FLOOR_Y
            self.vy = 0.0

        self.x += self.vx

        if self.grounded:
            self.vx *= GROUND_FRICTION
        else:
            self.vx *= AIR_FRICTION

        half_w = self.body_w / 2
        self.x = max(WALL_L + half_w, min(WALL_R - half_w, self.x))

    def set_anim(self, name: str) -> None:
        """애니메이션이 바뀔 때 프레임을 초기화한다."""
        if self.anim_name != name:
            self.anim_name = name
            self.anim_frame = 0
            self.anim_tick = 0

    def tick_anim(self, name: str) -> None:
        """현재 애니메이션의 프레임을 진행한다."""
        self.set_anim(name)

        anim = self.anims.get(name)
        if not anim:
            return

        self.anim_tick += 1

        frame_count = len(anim)
        if frame_count <= 0:
            return

        # 프레임 속도 조절
        frame_delay = 6

        if self.anim_tick >= frame_delay:
            self.anim_tick = 0
            self.anim_frame = (self.anim_frame + 1) % frame_count

    def spawn_hit_particles(self) -> None:
        """피격 효과 파티클 생성."""
        for _ in range(8):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(1.5, 4.5)

            self.particles.append(
                Particle(
                    x=self.x,
                    y=self.y - self.body_h * 0.55,
                    vx=math.cos(angle) * speed,
                    vy=math.sin(angle) * speed,
                    life=random.randint(8, 16),
                    color=(255, 210, 90),
                )
            )

    def step_particles(self) -> None:
        """파티클 위치와 수명을 갱신한다."""
        alive_particles = []

        for p in self.particles:
            p.x += p.vx
            p.y += p.vy
            p.vy += 0.15
            p.life -= 1

            if p.life > 0:
                alive_particles.append(p)

        self.particles = alive_particles

    def draw(self, screen: pygame.Surface) -> None:
        """캐릭터와 파티클을 화면에 그린다."""
        for p in self.particles:
            pygame.draw.circle(
                screen,
                p.color,
                (int(p.x), int(p.y)),
                max(1, p.life // 4),
            )

        anim = self.anims.get(self.anim_name)
        if not anim:
            return

        # Animation 구현에 따라 프레임 가져오는 방식이 다를 수 있음.
        # 기존 프로젝트의 draw()가 있다면 그 구현을 유지하는 것이 안전함.
        try:
            frame = anim[self.anim_frame]
        except (TypeError, IndexError, KeyError):
            return

        if frame is None:
            return

        image = frame

        if not isinstance(image, pygame.Surface):
            return

        if self.facing < 0:
            image = pygame.transform.flip(image, True, False)

        if self.flash > 0:
            image = image.copy()
            image.fill(
                (255, 255, 255, 0),
                special_flags=pygame.BLEND_RGBA_ADD,
            )

        rect = image.get_rect(
            midbottom=(int(self.x), int(self.y))
        )
        screen.blit(image, rect)