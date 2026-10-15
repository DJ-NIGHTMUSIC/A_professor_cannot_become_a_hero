"""AI 상대 — 거리 기반 행동 선택 + 반응형 방어"""
from __future__ import annotations

import random

from .config import DIFFICULTY
from .fighter import ATTACK, IDLE, Intent, KO, Fighter


class AI:
    def __init__(self, difficulty: str = "normal", seed: int | None = None):
        self.difficulty = difficulty
        self.rng = random.Random(seed)
        self.plan = Intent()
        self.plan_left = 0
        self.next_think = 0

    def reset(self) -> None:
        self.plan = Intent()
        self.plan_left = 0
        self.next_think = 0

    def act(self, self_f: Fighter, foe: Fighter, frame: int) -> Intent:
        p = DIFFICULTY[self.difficulty]
        if self_f.state == KO:
            return Intent()

        if self.plan_left > 0:
            self.plan_left -= 1
            return self.plan
        if frame >= self.next_think:
            self._decide(self_f, foe, p)
            self.next_think = frame + p["think"] + self.rng.randint(0, 4)
        return self.plan

    # -------------------------------------------------------------- 의사결정
    def _decide(self, f: Fighter, foe: Fighter, p: dict) -> None:
        self.plan = Intent()
        self.plan_left = 1

        if not f.can_act:
            return

        dist = abs(foe.x - f.x)
        d = 1 if foe.x >= f.x else -1
        light, heavy = f.moves["light"], f.moves["heavy"]
        spec = f.moves["special"]

        def hold(it: Intent, ticks: int) -> None:
            self.plan = it
            self.plan_left = ticks

        def atk(key: str, ticks: int) -> None:
            it = Intent()
            setattr(it, key, True)
            hold(it, ticks)

        # 1) 방어: 상대가 공격 중이면 확률로 가드
        threat = foe.state == ATTACK and foe.move is not None
        if threat and self.rng.random() < p["block"]:
            if dist > 80 and self.rng.random() < p["special"] and f.cooldown["special"] == 0:
                atk("special", 30)
            else:
                hold(Intent(block=True), 10 + self.rng.randint(0, 8))
            return

        # 2) 점프 중인 상대 (앵티에어)
        if not f.grounded and foe.vy > 0 and dist < 60 and self.rng.random() < p["jump"]:
            atk("heavy", 20)
            return

        # 3) 거리별
        if dist > 150:
            if f.cooldown["special"] == 0 and self.rng.random() < p["special"]:
                atk("special", 34)
                return
            if self.rng.random() < p["jump"] * 0.5:
                it = Intent(up=True)
                it.right = d > 0
                it.left = d < 0
                hold(it, 14)
                return
            it = Intent()
            it.right = d > 0
            it.left = d < 0
            hold(it, 20 + self.rng.randint(0, 14))
            return

        if dist > 60:
            r = self.rng.random()
            if f.cooldown["special"] == 0 and r < p["special"]:
                atk("special", 30)
                return
            if r < p["special"] + p["jump"] * 0.5 and self.rng.random() < p["jump"]:
                it = Intent(up=True)
                it.right = d > 0
                it.left = d < 0
                hold(it, 16)
                return
            if r > 0.78 and self.rng.random() > p["aggr"]:
                it = Intent()
                it.left = d > 0      # 뒤로
                it.right = d < 0
                hold(it, 12)
                return
            it = Intent()
            it.right = d > 0
            it.left = d < 0
            hold(it, 10 + self.rng.randint(0, 8))
            return

        # 4) 근접: 공격 위주
        r = self.rng.random()
        if f.cooldown["special"] == 0 and r < p["special"]:
            atk("special", 30)
            return
        if r < p["special"] + 0.45:
            atk("light", 16)
            return
        if r < p["special"] + 0.8:
            atk("heavy", 30)
            return
        if self.rng.random() < 0.35:
            it = Intent()
            it.left = d > 0
            it.right = d < 0
            hold(it, 8)
            return
        it = Intent()
        it.right = d > 0
        it.left = d < 0
        hold(it, 6)