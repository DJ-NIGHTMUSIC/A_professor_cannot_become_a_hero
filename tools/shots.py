"""
헤드리스 스모크 테스트
=====================
SDL 더미 드라이버로 게임을 실제로 구동하고, 특정 프레임을 PNG 로 저장한다.
디버깅용이므로 본 게임 루프와 동일한 step()/render() 를 사용한다.

사용법:
    python -m tools.shots            # 기본 시퀀스
    python -m tools.shots --frames 400
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.app import Game, TITLE_SCREEN, COUNTDOWN, FIGHT  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "shots"
OUT.mkdir(exist_ok=True)


def save(game: Game, name: str) -> None:
    path = OUT / f"{name}.png"
    pygame.image.save(game.screen, str(path))
    print(f"  saved {path.name}")


def main() -> None:
    game = Game()
    print(f"sprites ok  p1={game.p1.ch.name}({game.p1.ch.arch.title}) "
          f"p2={game.p2.ch.name}({game.p2.ch.arch.title})")
    print(f"anim idle frames={len(game.p1.anims['idle'])} "
          f"ticks={game.p1.anims['idle'].ticks} | "
          f"walk frames={len(game.p1.anims['walk'])} "
          f"ticks={game.p1.anims['walk'].ticks}")
    for f in game.p1.anims['walk'].frames:
        print(f"    {f.name:6s} head={f.head_px:6.1f} foot={f.foot_px:6.1f} phase={f.phase}")

    game.mode = TITLE_SCREEN
    game.render()
    save(game, "01-title")

    # 카운트다운 → 전투 진입
    game.mode = COUNTDOWN
    game.mode_timer = 0
    game.step()
    assert game.mode == FIGHT, f"카운트다운 후 FIGHT 여야 함 (현재 {game.mode})"

    # 전투 시뮬레이션: AI가 자동 플레이하므로 몇백 프레임만 돌리면 된다
    n = 400
    for _ in range(n):
        game.step()
        game.pressed.clear()
    game.render()
    save(game, "02-fight")
    print(f"after {n}f: hp1={game.p1.hp:.0f}/{game.p1.ch.max_hp} "
          f"hp2={game.p2.hp:.0f}/{game.p2.ch.max_hp} "
          f"state1={game.p1.state} state2={game.p2.state} "
          f"wins={game.p1.wins}-{game.p2.wins} mode={game.mode}")

    # 공격 동작을 눈으로 확인: 강타를 강제로 실행
    game.p1.x = game.p2.x - 70
    game.p1.try_move("heavy", 1)
    for i in range(12):
        game.p1.update(__import__("game.fighter", fromlist=["Intent"]).Intent(), game.p2)
    game.render()
    save(game, "03-attack")

    print("OK")
    pygame.quit()


if __name__ == "__main__":
    main()