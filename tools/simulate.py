"""
전체 매치 시뮬레이션 검증
========================
헤드리스로 AI vs AI 를 끝까지 돌려 라운드/매치 흐름이 정상인지 확인하고
결과 프레임을 PNG 로 저장한다.
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame  # noqa: E402
import random  # noqa: E402
import sys  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.ai import AI  # noqa: E402
from game.app import COUNTDOWN, FIGHT, MATCH_END, ROUND_END, Game  # noqa: E402
from game.fighter import KO, Intent, push_apart  # noqa: E402
from game.config import SCREEN_W  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "shots"
OUT.mkdir(exist_ok=True)


def main() -> None:
    difficulty = sys.argv[1] if len(sys.argv) > 1 else "normal"
    matches = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    game = Game(fullscreen=False)
    game.difficulty = difficulty
    game.ai.difficulty = difficulty

    total_frames = 0
    wins = [0, 0]

    for m in range(matches):
        game._new_match()
        game.ai.difficulty = difficulty
        game.mode = COUNTDOWN
        game.mode_timer = 1
        game.pressed.clear()

        frames = 0
        max_frames = 60 * 60 * 8      # 8분 상한
        shot_round = False
        ai1 = AI(difficulty, seed=m + 1)
        ai2 = AI(difficulty, seed=m + 999)
        # 좌우를 뒤집은 배치로 순서를 바꿔, P2 우세 여부를 구분한다
        flip = m % 2 == 1
        if flip:
            game.p1, game.p2 = game.p2, game.p1
            game.p1.x, game.p2.x = SCREEN_W * 0.35, SCREEN_W * 0.65

        while game.mode != MATCH_END and frames < max_frames:
            game.mode_timer = max(0, game.mode_timer - 1)
            if game.mode == COUNTDOWN:
                if game.mode_timer <= 0:
                    game.mode = FIGHT
            elif game.mode == FIGHT:
                # P1 도 AI 로 대체 (양쪽 다 AI)
                # AI 를 양쪽에 하나씩 둔다 (하나를 공유하면 plan 상태가 뒤섞인다)
                a1 = ai1.act(game.p1, game.p2, game.frame)
                a2 = ai2.act(game.p2, game.p1, game.frame)
                game.p1.update(a1, game.p2)
                game.p2.update(a2, game.p1)
                game._resolve(game.p1, game.p2)
                game._resolve(game.p2, game.p1)
                push_apart(game.p1, game.p2)
                game.round_time -= 1 / 60.0
                if not game.p1.alive or not game.p2.alive:
                    game._end_round(1 if game.p2.hp <= 0 and game.p1.hp > 0 else 2)
                elif game.round_time <= 0:
                    game._end_round(1 if game.p1.hp >= game.p2.hp else 2)
            elif game.mode == ROUND_END:
                if game.mode_timer <= 0:
                    if game.p1.wins >= 2 or game.p2.wins >= 2:
                        game.mode = MATCH_END
                    else:
                        game._new_round()
                        ai1.reset()
                        ai2.reset()
            game.frame += 1
            frames += 1

            if not shot_round and frames == 300:
                game.render()
                pygame.image.save(game.screen, str(OUT / f"sim-m{m}-fight.png"))
                shot_round = True

        game.render()
        pygame.image.save(game.screen, str(OUT / f"sim-m{m}-end.png"))

        result = 1 if game.p1.wins >= 2 else 2
        wins[result - 1] += 1
        status = "OK" if frames < max_frames else "TIMEOUT"
        # flip 매치에서는 P1/P2 라벨이 원래 자리를 바꿔 가므로 표기만 정리
        tag = f"{game.p1.ch.arch.title}/{game.p2.ch.arch.title}"
        print(f"match {m+1}: {game.p1.wins}-{game.p2.wins} "
              f"({'P1' if result == 1 else 'P2'} win) "
              f"frames={frames} ({frames/60:.1f}s) {status} "
              f"| {tag}{'  [flipped]' if flip else ''}")
        total_frames += frames

    print(f"\ntotal {total_frames} frames ({total_frames/60:.1f}s sim) "
          f"| P1 {wins[0]} - P2 {wins[1]}")
    pygame.quit()


if __name__ == "__main__":
    main()