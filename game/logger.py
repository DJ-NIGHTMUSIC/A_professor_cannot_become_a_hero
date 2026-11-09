"""
플레이 기록 (텍스트 로그)
=========================
게임을 실행할 때마다 logs/play_log.txt 에 한 줄씩 이어서 기록한다.
(한 파일에 계속 쌓이므로 '몇 번 실행했는지'를 세기 쉽다)

기록 예:
  [2026-11-06 15:30:12] SESSION_START no=3
  [2026-11-06 15:31:05] ROUND match=1 round=1 winner=PLAYER time_left=23 hp_left=48
  [2026-11-06 15:31:40] MATCH no=1 player=KAI enemy=BOSS result=WIN score=2-0 duration_sec=88
  [2026-11-06 15:40:00] SESSION_END no=3 session_sec=588 matches=3 wins=2 losses=1

기록에 실패해도 게임은 절대 멈추지 않는다.
"""
from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "logs" / "play_log.txt"
_LINE = re.compile(r"^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\] (\w+)(.*)$")


class PlayLogger:
    def __init__(self, enabled: bool = True, path: Path | None = None):
        self.enabled = enabled
        self.path = Path(path) if path else DEFAULT_PATH
        self.t0 = time.monotonic()
        self.matches = 0
        self.wins = 0
        self.losses = 0
        self._ended = False
        self.session_no = 0
        if self.enabled:
            self.session_no = self._count_sessions() + 1
            self._write("SESSION_START", no=self.session_no)

    # ------------------------------------------------------------ 기록
    def round_end(self, match: int, rnd: int, winner: str,
                  time_left: int, hp_left: int) -> None:
        self._write("ROUND", match=match, round=rnd, winner=winner,
                    time_left=time_left, hp_left=hp_left)

    def match_end(self, no: int, player: str, enemy: str,
                  p_wins: int, e_wins: int, seconds: float) -> None:
        win = p_wins > e_wins
        self.matches += 1
        self.wins += 1 if win else 0
        self.losses += 0 if win else 1
        self._write("MATCH", no=no, player=player, enemy=enemy,
                    result="WIN" if win else "LOSE",
                    score=f"{p_wins}-{e_wins}", duration_sec=int(seconds))

    def match_abandoned(self, no: int, seconds: float) -> None:
        self._write("MATCH_ABANDONED", no=no, duration_sec=int(seconds))

    def end_session(self) -> None:
        if self._ended:
            return
        self._ended = True
        self._write("SESSION_END", no=self.session_no,
                    session_sec=int(time.monotonic() - self.t0),
                    matches=self.matches, wins=self.wins, losses=self.losses)

    # ------------------------------------------------------------ 집계
    def stats(self, recent: int = 5) -> dict:
        """로그 파일을 읽어 총계를 만든다 (게임 안 RECORD 화면용)"""
        res = dict(runs=0, total_sec=0, matches=0, wins=0, losses=0,
                   match_sec=0, recent=[])
        if not self.enabled:
            return res
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return res

        sessions, matches = [], []
        for raw in lines:
            m = _LINE.match(raw.strip())
            if not m:
                continue
            try:
                ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            ev = m.group(2)
            kv = dict(re.findall(r"(\w+)=(\S+)", m.group(3)))
            if ev == "SESSION_START":
                sessions.append({"no": kv.get("no"), "start": ts, "last": ts, "sec": None})
            elif sessions:
                sessions[-1]["last"] = ts
                if ev == "SESSION_END":
                    sessions[-1]["sec"] = int(kv.get("session_sec", 0))
                elif ev == "MATCH":
                    matches.append(kv)

        total = 0.0
        for i, ss in enumerate(sessions):
            if ss["sec"] is not None:
                total += ss["sec"]
            elif (i == len(sessions) - 1 and ss["no"] == str(self.session_no)
                  and not self._ended):
                total += time.monotonic() - self.t0      # 지금 실행 중인 판
            else:                                         # 비정상 종료: 추정
                total += (ss["last"] - ss["start"]).total_seconds()

        wins = sum(1 for k in matches if k.get("result") == "WIN")
        res.update(
            runs=len(sessions), total_sec=int(total), matches=len(matches),
            wins=wins, losses=len(matches) - wins,
            match_sec=sum(int(k.get("duration_sec", 0)) for k in matches),
            recent=[dict(player=k.get("player", "?"), enemy=k.get("enemy", "?"),
                         result=k.get("result", "?"), score=k.get("score", "-"))
                    for k in reversed(matches[-recent:])],
        )
        return res

    # ------------------------------------------------------------ 내부
    def _count_sessions(self) -> int:
        try:
            if not self.path.exists():
                return 0
            with open(self.path, encoding="utf-8") as f:
                return sum(1 for line in f if " SESSION_START " in line)
        except OSError:
            return 0

    def _write(self, event: str, **fields) -> None:
        if not self.enabled:
            return
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        body = " ".join(f"{k}={v}" for k, v in fields.items())
        line = f"[{stamp}] {event} {body}".rstrip() + "\n"
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass  # 기록 실패는 무시 (게임 진행이 우선)