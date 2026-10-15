"""
캐릭터 정의
============
테스트 단계에서는 양쪽 모두 같은 스프라이트를 쓴다.
색상 변시는 하지 않고, 능력치(체력/속도/파워/체중)만 랜덤으로 준다.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .config import CHAR_H, WALK_SPEED


@dataclass(frozen=True)
class Archetype:
    key: str
    title: str
    hp: int
    walk: float      # 이동 배율
    jump: float      # px/s
    power: float     # 데미지 배율
    weight: float    # 넉백 저항
    defense: float   # 받는 데미지 배율
    reach: float     # 사거리 배율
    speed: float     # 타격 배율 (클수록 빠름)
    ui_color: tuple[int, int, int]


ARCHETYPES: dict[str, Archetype] = {
    "rush": Archetype("rush", "RUSH", 92, 1.30, 480, 0.86, 0.90, 1.06, 0.92, 1.24, (255, 107, 107)),
    "balance": Archetype("balance", "ALLROUND", 104, 1.05, 462, 1.00, 1.00, 1.00, 1.00, 1.00, (107, 214, 255)),
    "power": Archetype("power", "POWER", 126, 0.82, 415, 1.24, 1.25, 0.90, 1.14, 0.78, (255, 176, 79)),
    "edge": Archetype("edge", "EDGE", 98, 1.02, 455, 1.02, 0.95, 1.02, 1.06, 1.10, (185, 140, 255)),
}

NAMES = [
    "KAI", "RIN", "ZORO", "VEX", "MIRA", "DRAX", "NOX", "SOL", "BRIG", "ZEN",
    "ONYX", "PYRE", "RAVE", "SABLE", "TITAN", "VOLT", "ASH", "JIN", "HALO", "WRAITH",
]


@dataclass
class Character:
    """캐릭터 정체성 + 능력치 (모션은 공유 스프라이트 사용)"""

    name: str
    arch: Archetype
    max_hp: int
    char_h: int
    walk_jitter: float = 1.0
    jump_jitter: float = 1.0
    power_jitter: float = 1.0

    @property
    def walk_speed(self) -> float:
        return WALK_SPEED * self.arch.walk * self.walk_jitter

    @property
    def jump_v(self) -> float:
        return self.arch.jump * self.jump_jitter

    def damage(self, base: float) -> float:
        return base * self.arch.power * self.power_jitter


def roll_character(rng: random.Random, forced: str | None = None) -> Character:
    arch = ARCHETYPES[forced or rng.choice(list(ARCHETYPES))]
    size = rng.uniform(0.94, 1.08)
    return Character(
        name=rng.choice(NAMES),
        arch=arch,
        max_hp=int(arch.hp * rng.uniform(0.94, 1.06)),
        char_h=int(CHAR_H * size),
        walk_jitter=rng.uniform(0.95, 1.05),
        jump_jitter=rng.uniform(0.97, 1.03),
        power_jitter=rng.uniform(0.95, 1.05),
    )