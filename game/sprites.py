"""
스프라이트 로딩 / 측정 / 애니메이션
==================================
- 픽셀이 각져 보이도록 로드 시 PIL NEAREST 로 정확히 목표 크기를 만든다
  (pygame 기본 scale 은 선형 보간이라 픽셀이 뭉개진다)
- 알파 실루엣을 측정해 각 프레임의 앵커(머리 중심 x)와 지면(최하단 y)을 구한다
- 프레임 간 해상도가 달라도 (30x56 vs 162x122) 실루엣 높이를 기준으로
  같은 크기로 정규화하므로 캐릭터 크기가 흔들리지 않는다

폴더 규약
----------
폴더마다 metadata.json 을 두면 그걸 따르고, 없으면 파일명 순으로 쓴다.

  {
    "kind": "idle" | "walk" | ...,
    "cycle": ["a", "b", "c"],        # 재생 순서 (없으면 파일명 순)
    "exclude": ["a"],                # 제외할 프레임
    "ticks": {"a": 2, "b": 1}        # 프레임별 유지 틱 (없으면 보폭 기반 자동)
  }
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pygame
from PIL import Image

SPRITE_ROOT = Path(__file__).resolve().parent.parent / "sprites"


@dataclass
class FrameInfo:
    """프레임 1장의 측정값 (스케일 적용 후 픽셀 좌표)"""

    name: str
    surface: pygame.Surface
    head_px: float      # 정렬 앵커 x (머리 중심)
    foot_px: float      # 지면 앵커 y (최하단 픽셀)
    phase: str = "unknown"


class Animation:
    """프레임 시퀀스"""

    def __init__(self, name: str, paths: list[Path], char_h: int,
                 meta: dict | None = None):
        self.name = name
        meta = meta or {}
        self.frames: list[FrameInfo] = []

        # sit은 높이가 낮은 스프라이트이므로 너비 기준 스케일
        scale_by_width = (name == "sit")
        raw = [_measure(p, char_h, scale_by_width) for p in paths]
        max_stride = max((r["stride"] for r in raw), default=0.0)

        for r, p in zip(raw, paths):
            phase = _phase(r["planted"], r["stride"], max_stride)
            surf = _load_scaled(p, r["size"])
            self.frames.append(FrameInfo(
                name=p.stem,
                surface=surf,
                head_px=r["head_cx"] * r["scale"],
                foot_px=r["foot_y"] * r["scale"],
                phase=phase,
            ))

        # 틱 결정: metadata 우선, 없으면 종류별 기본값 사용
        fixed = meta.get("ticks") or {}
        # 기본 틱: idle은 느리게(12), walk는 보통(5), contact 프레임은 좀 더 길게
        if self.name == "idle":
            default_tick = 12
        elif self.name == "walk":
            default_tick = 5
        else:
            default_tick = 4
        self.ticks = [
            int(fixed.get(f.name, default_tick if f.phase != "contact" else default_tick + 2))
            for f in self.frames
        ]

    def __len__(self) -> int:
        return len(self.frames)

    @property
    def total_ticks(self) -> int:
        return sum(self.ticks)


# ---------------------------------------------------------------- 측정
def _measure(path: Path, char_h: int, scale_by_width: bool = False) -> dict:
    arr = np.array(Image.open(path).convert("RGBA"))
    mask = arr[:, :, 3] > 32
    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        raise ValueError(f"빈 스프라이트: {path}")

    h, w = arr.shape[:2]
    y0, y1 = int(ys.min()), int(ys.max())

    # 머리 중심 = 상단 45% 영역의 가중 중심 (프레임 간 가장 안정적)
    head_end = y0 + int((y1 - y0) * 0.45)
    head_xs = np.nonzero(mask[y0 : head_end + 1])[1]
    head_cx = float(head_xs.mean()) if len(head_xs) else w / 2

    # 지면에 닿은 발 = 열별 최하단 픽셀이 바닥 행에 닿는 열
    bottom = np.full(w, -1, dtype=int)
    for x in np.nonzero(mask.any(axis=0))[0]:
        nz = np.nonzero(mask[:, x])[0]
        if len(nz):
            bottom[x] = int(nz[-1])
    cols = np.nonzero(bottom >= y1 - 1)[0]

    runs: list[list[int]] = []
    if len(cols):
        runs = [[int(cols[0])]]
        for v in cols[1:]:
            if v - runs[-1][-1] > 3:
                runs.append([int(v)])
            else:
                runs[-1].append(int(v))

    if len(runs) >= 2:
        centers = [float(np.mean(r)) for r in runs]
        stride = max(centers) - min(centers)
        planted = len(runs)
    else:
        stride, planted = 0.0, (1 if runs else 0)

    body_h = max(1, y1 - y0)
    body_w = max(1, xs.max() - xs.min())
    if scale_by_width:
        # 너비 기준 스케일: 앉은 자세 등 높이가 낮은 스프라이트용
        # standing 캐릭터 너비가 char_h의 약 42%이므로 비율 맞춤
        scale = (char_h * 0.42) / body_w
    else:
        scale = char_h / body_h
    return {
        "name": path.stem,
        "head_cx": head_cx,
        "foot_y": y1,
        "stride": stride,
        "planted": planted,
        "scale": scale,
        "size": (max(1, round(w * scale)), max(1, round(h * scale))),
    }


def _phase(planted: int, stride: float, max_stride: float) -> str:
    if planted >= 2 and stride >= max_stride * 0.8:
        return "contact"
    if planted >= 2:
        return "passing"
    if planted == 1:
        return "support"
    return "flight"


def _load_scaled(path: Path, size: tuple[int, int]) -> pygame.Surface:
    img = Image.open(path).convert("RGBA")
    if img.size != size:
        img = img.resize(size, Image.NEAREST)
    return pygame.image.frombuffer(img.tobytes(), size, "RGBA").convert_alpha()


# ---------------------------------------------------------------- 메타데이터
def load_meta(folder: Path) -> dict:
    p = folder / "metadata.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


# ---------------------------------------------------------------- 로더
_cache: dict[tuple[int, str], Animation] = {}


def get_animation(folder: str, char_h: int) -> Animation:
    """폴더 → Animation (char_h 별 캐시)"""
    key = (char_h, folder)
    if key in _cache:
        return _cache[key]

    folder_path = SPRITE_ROOT / folder
    if not folder_path.is_dir():
        raise FileNotFoundError(f"스프라이트 폴더 없음: {folder_path}")

    meta = load_meta(folder_path)
    by_name = {p.stem: p for p in folder_path.glob("*.png")}

    order: list[str] = []
    for n in meta.get("cycle", []):
        if n in by_name:
            order.append(n)
    if not order:
        order = sorted(by_name)

    skip = set(meta.get("exclude", []))
    paths = [by_name[n] for n in order if n not in skip]

    if not paths:
        raise ValueError(f"사용할 프레임 없음: {folder_path}")

    anim = Animation(folder, paths, char_h, meta)
    _cache[key] = anim
    return anim


def available_folders() -> list[str]:
    if not SPRITE_ROOT.is_dir():
        return []
    return sorted(p.name for p in SPRITE_ROOT.iterdir() if p.is_dir())