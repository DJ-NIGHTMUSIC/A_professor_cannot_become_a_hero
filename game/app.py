"""
게임 본체
=========
상태 흐름: TITLE → COUNTDOWN → FIGHT → ROUND_END → MATCH_END
P1 = 키보드, P2 = AI
"""
from __future__ import annotations

import os
import random

# Windows DPI awareness must be set before pygame/SDL initializes.
os.environ.setdefault("SDL_WINDOWS_DPI_AWARENESS", "permonitorv2")

import pygame

from .ai import AI
from .character import ARCHETYPES, roll_character
from .config import (
    CAMERA_SMOOTH, FPS, KEY_MAP, ROUND_TIME, SCREEN_H, SCREEN_W, TITLE, WINS_NEEDED,
)
from .fighter import ATTACK, IDLE, KO, HURT, Fighter, Intent, push_apart
from .stage import draw_banner, draw_hud, draw_stage, draw_text, text_width

TITLE_SCREEN, COUNTDOWN, FIGHT, ROUND_END, MATCH_END, PAUSED, VICTORY_IMG = range(7)

# 타이틀 화면 상태
TITLE_MENU, TITLE_NICKNAME = range(2)

# 로고 이미지 캐시
_logo_img = None

def _load_logo():
    """로고 이미지 로드 (캐시)"""
    global _logo_img
    if _logo_img is not None:
        return _logo_img
    from pathlib import Path
    logo_path = Path(__file__).parent.parent / "sprites" / "logo.png"
    if logo_path.exists():
        img = pygame.image.load(str(logo_path))
        # 로고 크기 조정 (최대 높이 80px)
        w, h = img.get_size()
        if h > 80:
            scale = 80 / h
            _logo_img = pygame.transform.scale(img, (int(w * scale), 80))
        else:
            _logo_img = img
    return _logo_img


# 승리 이미지 캐시 (sprites 폴더에 이 이름 중 하나로 넣으면 된다)
VICTORY_IMAGE_NAMES = ("victory.png", "victory.jpg", "victory.jpeg")
_victory_img = None
_victory_checked = False


def _load_victory_image():
    """승리 이미지 로드 (캐시). 없으면 None"""
    global _victory_img, _victory_checked
    if _victory_checked:
        return _victory_img
    _victory_checked = True
    from pathlib import Path
    root = Path(__file__).parent.parent / "sprites"
    for name in VICTORY_IMAGE_NAMES:
        path = root / name
        if path.exists():
            img = pygame.image.load(str(path)).convert_alpha()
            w, h = img.get_size()
            # 화면(아래 안내 문구 자리 제외)에 비율 유지하며 맞춤
            scale = min(SCREEN_W / w, (SCREEN_H - 30) / h)
            _victory_img = pygame.transform.scale(
                img, (max(1, int(w * scale)), max(1, int(h * scale))))
            break
    return _victory_img


def display_geometry(win_w: int, win_h: int) -> tuple[float, int, int]:
    """창 크기에 맞는 균등 배율と表示バッファ寸法を返す。"""
    ideal = min(max(1, win_w) / SCREEN_W, max(1, win_h) / SCREEN_H)
    if ideal < 1.0:
        scale = ideal
    else:
        whole = max(1, int(ideal))
        scale = float(whole) if ideal - whole < 0.05 else ideal
    return scale, max(1, round(SCREEN_W * scale)), max(1, round(SCREEN_H * scale))


class Game:
    def __init__(self, headless: bool = False, fullscreen: bool = True):
        self.headless = headless
        if headless:
            os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
            os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

        pygame.init()
        pygame.display.set_caption(TITLE)
        self.fullscreen = fullscreen

        # 창을 먼저 연다. convert() 를 쓰려면 영상 모드가 먼저 설정돼야 한다.
        self._open_window(fullscreen)

        # 중요: 내부 렌더 버퍼는 set_mode 로 만들지 않는다.
        # set_mode 를 두 번 부르면 화면 표면이 교체되어 첫 표면에는 그려지지
        # 않으므로(검은 화면) 오직 창에만 set_mode 를 쓴다.
        self.screen = pygame.Surface((SCREEN_W, SCREEN_H)).convert()
        self._apply_display(fullscreen)

        self.clock = pygame.time.Clock()
        self.rng = random.Random()

        self.difficulty = "normal"
        self.mode = TITLE_SCREEN
        self.mode_timer = 0
        self.frame = 0
        self.round_time = ROUND_TIME
        self.running = True
        self._resume_mode = FIGHT

        self.held: set[int] = set()
        self.pressed: set[int] = set()

        # 카메라
        self.camera_x = 0.0
        self.camera_target_x = 0.0

        # 타이틀 화면
        self.title_state = TITLE_MENU
        self.title_anim = 0.0  # 0~1 전환 애니메이션
        self.nickname = "PLAYER"
        self.nickname_cursor = 0
        self.enemy_name = "ENEMY"        # 적 이름
        self.editing_enemy = False       # False=내 이름, True=적 이름 편집 중
        self.menu_index = 0  # 0=플레이, 1=닉네임

        self.p1 = Fighter(roll_character(self.rng), 1, SCREEN_W * 0.35)
        self.p2 = Fighter(roll_character(self.rng), 2, SCREEN_W * 0.65)
        self.ai = AI(self.difficulty)
        # _new_round() 는 _new_match() 에서 호출됨 - 초기화 시 호출 안 함

    # ---------------------------------------------------------------- 표시
    def _open_window(self, fullscreen: bool) -> None:
        """열려 있는 데스크톱 크기에 맞는 창 또는 보더리스 전체화면을 연다."""
        if fullscreen:
            flags = getattr(pygame, "FULLSCREEN_DESKTOP", pygame.FULLSCREEN)
            try:
                self.window = pygame.display.set_mode((0, 0), flags)
            except pygame.error:
                self.fullscreen = False
                self.window = pygame.display.set_mode(
                    (SCREEN_W * 2, SCREEN_H * 2), pygame.RESIZABLE)
        else:
            info = pygame.display.Info()
            max_w = max(SCREEN_W, int(info.current_w * 0.95))
            max_h = max(SCREEN_H, int(info.current_h * 0.95))
            # 가능한 가장 큰 정수 배율 창을 선택한다. 작은 데스크톱에서도 최소 내부 크기.
            scale = max(1, min(max_w // SCREEN_W, max_h // SCREEN_H))
            self.window = pygame.display.set_mode(
                (SCREEN_W * scale, SCREEN_H * scale), pygame.RESIZABLE)

    def _apply_display(self, fullscreen: bool) -> None:
        """실제 창 크기에 맞춰 확대/축소 버퍼를 다시 계산한다."""
        self.window = pygame.display.get_surface() or self.window
        win_w, win_h = self.window.get_size()
        scale, vw, vh = display_geometry(win_w, win_h)
        self.view = pygame.Surface((vw, vh)).convert()
        self.view.fill((7, 5, 12))
        self.scale = scale

    def _sync_window(self) -> None:
        """화면 표면이 교체된 뒤 현재 디스플레이 표면과 뷰를 동기화한다."""
        current = pygame.display.get_surface()
        if current is not None and current is not self.window:
            self.window = current
            self._apply_display(self.fullscreen)

    def toggle_fullscreen(self) -> None:
        """전체화면 / 창 모드 전환"""
        self.fullscreen = not self.fullscreen
        self._open_window(self.fullscreen)
        self._sync_window()
        self._apply_display(self.fullscreen)

    def _blit_view(self) -> None:
        """내부 화면(640x360)을 균등 비율로 확대해 창 중앙에 표시"""
        win_w, win_h = self.window.get_size()
        vw, vh = self.view.get_size()

        self.window.fill((7, 5, 12))
        if self.scale == 1.0 and (win_w, win_h) == (SCREEN_W, SCREEN_H):
            self.window.blit(self.screen, (0, 0))
            return

        # 중간 버퍼를 거쳐 확대한다 (큰 크기 직접 스케일 대비 안정적)
        if self.view.get_size() != (vw, vh):
            self.view = pygame.Surface((vw, vh)).convert()
        pygame.transform.scale(self.screen, (vw, vh), self.view)
        self.window.blit(self.view, ((win_w - vw) // 2, (win_h - vh) // 2))

    # ---------------------------------------------------------------- 입력
    def _handle_events(self) -> None:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self.running = False
            elif e.type == pygame.VIDEORESIZE:
                # 창 모드에서 크기가 바뀌면 배율 재계산
                if not self.fullscreen:
                    self.window = pygame.display.set_mode(
                        (max(1, e.w), max(1, e.h)), pygame.RESIZABLE)
                    self._sync_window()
                    self._apply_display(False)
            elif e.type == pygame.WINDOWFOCUSLOST:
                self.held.clear()
                self.pressed.clear()
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_F11:
                    self.toggle_fullscreen()
                    continue
                self.pressed.add(e.key)
                self.held.add(e.key)
            elif e.type == pygame.KEYUP:
                self.held.discard(e.key)

    def _down(self, action: str) -> bool:
        return any(k in self.held for k in KEY_MAP[action])

    def _hit(self, action: str) -> bool:
        return any(k in self.pressed for k in KEY_MAP[action])

    def _player_intent(self) -> Intent:
        return Intent(
            left=self._down("left"),
            right=self._down("right"),
            up=self._down("up"),
            down=self._down("down"),
            block=self._down("block"),
            light=self._hit("light"),
            heavy=self._hit("heavy"),
            special=self._hit("special"),
            pressed_left=self._hit("left"),
            pressed_right=self._hit("right"),
        )

    # ---------------------------------------------------------------- 흐름
    def _new_match(self) -> None:
        # 두 캐릭터는 아키타입이 겹치지 않게
        keys = list(ARCHETYPES)
        self.rng.shuffle(keys)
        self.p1 = Fighter(roll_character(self.rng, keys[0]), 1, SCREEN_W * 0.35)
        self.p2 = Fighter(roll_character(self.rng, keys[1]), 2, SCREEN_W * 0.65)
        self.ai.difficulty = self.difficulty
        self.ai.reset()
        self._new_round()

    def _new_round(self) -> None:
        self.mode = COUNTDOWN
        self.mode_timer = 120
        self.round_time = ROUND_TIME
        for f, x in ((self.p1, SCREEN_W * 0.35), (self.p2, SCREEN_W * 0.65)):
            f.x, f.y = x, 300
            f.vx = f.vy = 0.0
            f.state = IDLE
            f.move = None
            f.hitstun = f.blockstun = f.hitstop = 0
            f.blocking = False
            f.particles.clear()
            f.facing = 1 if f.slot == 1 else -1
        self.p1.hp = float(self.p1.ch.max_hp)
        self.p2.hp = float(self.p2.ch.max_hp)
        self.ai.reset()
        self.pressed.clear()
        self.held.clear()
        for f in (self.p1, self.p2):
            f.state_frame = 0
            f.move_frame = 0
            f.hit_used = False
            f.cooldown = {"light": 0, "heavy": 0, "special": 0}
            f.flash = 0
            f.dash_timer = 0
            f.dash_dir = 0
            f.dash_cooldown = 0
            f.last_left_time = -999
            f.last_right_time = -999
            f.anim_name = "idle"
            f.anim_frame = f.anim_tick = 0
            f.attack_buffer = {"light": 0, "heavy": 0, "special": 0}
            f.jump_buffer = 0

    def _end_round(self, winner: int) -> None:
        if winner == 1:
            self.p1.wins += 1
        else:
            self.p2.wins += 1
        loser = self.p1 if winner == 2 else self.p2
        loser.hp = 0
        loser.state = KO
        self.mode = ROUND_END
        self.mode_timer = 150
        self.pressed.clear()

    # ---------------------------------------------------------------- 프레임
    def step(self) -> None:
        self.frame += 1
        self.mode_timer = max(0, self.mode_timer - 1)

        # 일시정지 (전투 중에만)
        if self._hit("pause"):
            if self.mode == FIGHT:
                self._resume_mode = FIGHT
                self.mode = PAUSED
            elif self.mode == PAUSED:
                self.mode = self._resume_mode

        if self.mode == TITLE_SCREEN:
            self._step_title()
        elif self.mode == COUNTDOWN:
            self._step_countdown()
        elif self.mode == FIGHT:
            self._step_fight()
        elif self.mode == ROUND_END:
            self._step_round_end()
        elif self.mode == MATCH_END:
            self._step_match_end()
        elif self.mode == VICTORY_IMG:
            self._step_victory_img()
        elif self.mode == PAUSED:
            if self._hit("confirm"):
                # ENTER GIVE UP: 경기 포기 후 타이틀로 돌아간다.
                self.mode = TITLE_SCREEN
                self.title_state = TITLE_MENU
                self.menu_index = 0
                self.held.clear()
                self.pressed.clear()

    def _step_title(self) -> None:
        self.p1.update(Intent(), self.p2)
        self.p2.update(Intent(), self.p1)

        # 메뉴 선택
        if self.title_state == TITLE_MENU:
            if self._hit("down") or self._hit("up"):
                self.menu_index = 1 - self.menu_index
            if self._hit("confirm"):
                if self.menu_index == 0:
                    # 플레이
                    self.difficulty = "normal"
                    self.ai.difficulty = self.difficulty
                    self._new_match()
                else:
                    # 닉네임 설정으로 전환
                    self.title_state = TITLE_NICKNAME
                    self.title_anim = 0.0
                    self.editing_enemy = False
                    self.nickname_cursor = len(self.nickname)
        elif self.title_state == TITLE_NICKNAME:
            # 지금 편집 중인 이름 (내 이름 / 적 이름)
            text = self.enemy_name if self.editing_enemy else self.nickname
            for k in self.pressed:
                if pygame.K_a <= k <= pygame.K_z:
                    if len(text) < 10:
                        text = text[:self.nickname_cursor] + chr(k).upper() + text[self.nickname_cursor:]
                        self.nickname_cursor += 1
                elif pygame.K_0 <= k <= pygame.K_9:
                    if len(text) < 10:
                        text = text[:self.nickname_cursor] + chr(k) + text[self.nickname_cursor:]
                        self.nickname_cursor += 1
                elif k == pygame.K_BACKSPACE and self.nickname_cursor > 0:
                    text = text[:self.nickname_cursor - 1] + text[self.nickname_cursor:]
                    self.nickname_cursor -= 1
                elif k == pygame.K_RETURN:
                    if not self.editing_enemy:
                        # 내 이름 완료 -> 적 이름 입력으로
                        self.nickname = text or "PLAYER"
                        self.editing_enemy = True
                        text = self.enemy_name
                        self.nickname_cursor = len(text)
                    else:
                        # 적 이름 완료 -> 메뉴로
                        self.enemy_name = text or "ENEMY"
                        self.editing_enemy = False
                        self.title_state = TITLE_MENU
                        self.title_anim = 0.0
                    break
                elif k == pygame.K_ESCAPE:
                    self.editing_enemy = False
                    self.title_state = TITLE_MENU
                    self.title_anim = 0.0
                    break

            # 편집한 내용을 다시 저장
            if self.title_state == TITLE_NICKNAME:
                if self.editing_enemy:
                    self.enemy_name = text
                else:
                    self.nickname = text

        # 전환 애니메이션 진행
        if self.title_anim < 1.0:
            self.title_anim = min(1.0, self.title_anim + 0.05)

    def _step_countdown(self) -> None:
        self.p1.update(Intent(), self.p2)
        self.p2.update(Intent(), self.p1)
        if self.mode_timer <= 0:
            self.mode = FIGHT
            self.pressed.clear()

    def _step_fight(self) -> None:
        pi = self._player_intent()
        ai = self.ai.act(self.p2, self.p1, self.frame)

        self.p1.update(pi, self.p2)
        self.p2.update(ai, self.p1)

        # 근접 판정
        self._resolve_pair()
        push_apart(self.p1, self.p2)

        self.round_time -= 1 / 60.0

        # KO 판정
        if not self.p1.alive or not self.p2.alive:
            self._end_round(1 if self.p2.hp <= 0 and self.p1.hp > 0 else 2)
            return

        if self.round_time <= 0:
            self.round_time = 0
            self._end_round(1 if self.p1.hp >= self.p2.hp else 2)

    def _step_round_end(self) -> None:
        self.p1.update(Intent(), self.p2)
        self.p2.update(Intent(), self.p1)
        if self.mode_timer <= 0:
            if self.p1.wins >= WINS_NEEDED or self.p2.wins >= WINS_NEEDED:
                self.mode = MATCH_END
                self.pressed.clear()
            else:
                self._new_round()

    def _step_match_end(self) -> None:
        self.p1.update(Intent(), self.p2)
        self.p2.update(Intent(), self.p1)
        if self._hit("confirm"):
            if self.p1.wins >= WINS_NEEDED:
                # 이겼을 때: 승리 이미지 화면으로
                self.mode = VICTORY_IMG
                self.pressed.clear()
            else:
                self._new_match()

    def _step_victory_img(self) -> None:
        # 이미지 화면에서 Enter -> 새 경기
        if self._hit("confirm"):
            self._new_match()

    def _resolve_pair(self) -> None:
        """양쪽 공격의 유효 판정을 먼저 수집한 뒤 피해를 적용해 트레이드를 보장한다."""
        fighters = ((self.p1, self.p2), (self.p2, self.p1))
        hits = []
        for atk, dfn in fighters:
            if atk.hit_used:
                continue
            box = atk.hitbox()
            if box is not None and box.colliderect(dfn.hurtbox()):
                hits.append((atk, dfn, atk.move, dfn.blocking))
        for atk, dfn, move, was_blocking in hits:
            if move is None:
                continue
            atk.hit_used = True
            if was_blocking:
                dfn.take_block(atk.x, move)
                atk.hitstop = max(atk.hitstop, 4)
            else:
                dfn.take_damage(atk.ch.damage(move.damage), atk.x, move)
                atk.hitstop = max(atk.hitstop, move.hitstop)

    def _resolve(self, atk: Fighter, dfn: Fighter) -> None:
        if atk.hit_used:
            return
        box = atk.hitbox()
        if box is None:
            return
        if not box.colliderect(dfn.hurtbox()):
            return

        m = atk.move
        atk.hit_used = True
        if dfn.blocking:
            dfn.take_block(atk.x, m)
            atk.hitstop = max(atk.hitstop, 4)
        else:
            dfn.take_damage(atk.ch.damage(m.damage), atk.x, m)
            atk.hitstop = m.hitstop

    # ---------------------------------------------------------------- 렌더
    def _update_camera(self) -> None:
        """카메라가 P1(ME)을 부드럽게 따라감"""
        if self.mode != FIGHT and self.mode != COUNTDOWN:
            self.camera_x = 0.0
            return

        # P1 기준으로 카메라 이동
        # P1이 화면 중앙에 오도록
        target = self.p1.x - SCREEN_W / 2

        # 카메라 이동 범위 제한 (무대 밖으로 못 나가게)
        stage_extra = 80  # WALL_L/R 확장분
        max_cam = stage_extra
        min_cam = -stage_extra
        
        target = max(min_cam, min(max_cam, target))

        # 부드럽게 이동 (lerp)
        self.camera_x += (target - self.camera_x) * CAMERA_SMOOTH

    def render(self) -> None:
        self._update_camera()
        s = self.screen

        # 카메라 오프셋을 월드 좌표에 적용
        cam = int(self.camera_x)

        # 화면을 카메라만큼 이동해서 그리기
        draw_stage(s, cam)
        # 아래쪽 캐릭터가 앞에 오도록 정렬
        for f in sorted((self.p1, self.p2), key=lambda f: f.y):
            f.draw(s, cam)

        # P1/P2 이름표: 항상 표시
        if self.mode == FIGHT or self.mode == COUNTDOWN:
            # P1: 노란색 닉네임
            draw_text(s, self.nickname, int(self.p1.x) - text_width(self.nickname) // 2 - cam,
                      int(self.p1.y - self.p1.body_h - 16), (255, 212, 71), 1)
            # P2: 빨간색 적 이름
            draw_text(s, self.enemy_name, int(self.p2.x) - text_width(self.enemy_name) // 2 - cam,
                      int(self.p2.y - self.p2.body_h - 16), (255, 107, 107), 1)

        if self.mode == TITLE_SCREEN:
            self._render_title(s)
            return

        draw_hud(s, self.p1, self.p2, int(self.round_time), self.difficulty)

        if self.mode == COUNTDOWN:
            self._render_countdown(s)
        elif self.mode == ROUND_END:
            win = self.p1.wins > self.p2.wins
            draw_banner(s, "VICTORY" if win else "DEFEAT",
                        (255, 212, 71) if win else (255, 107, 107))
        elif self.mode == MATCH_END:
            self._render_match_end(s)
        elif self.mode == VICTORY_IMG:
            self._render_victory_img(s)
        elif self.mode == PAUSED:
            self._render_paused(s)

    def _render_countdown(self, s) -> None:
        t = self.mode_timer
        if t > 92:
            txt = f"ROUND {3 - self.p1.wins - self.p2.wins}"
            draw_banner(s, txt, (255, 212, 71))
        elif t > 58:
            draw_banner(s, "READY", (232, 226, 240))
        else:
            n = int((t - 20) / 20 + 0.999)
            draw_banner(s, str(n) if n > 0 else "FIGHT!", (255, 212, 71))

    def _render_match_end(self, s) -> None:
        s.fill((10, 7, 16))
        win = self.p1.wins >= WINS_NEEDED
        draw_banner(s, "VICTORY" if win else "DEFEAT",
                    (255, 212, 71) if win else (255, 107, 107), 80)
        score = f"{self.p1.wins} - {self.p2.wins}"
        draw_banner(s, score, (232, 226, 240), 120, 2)
        hint = "ENTER CONTINUE" if win else "ENTER REMATCH"
        draw_text(s, hint, SCREEN_W // 2 - text_width(hint) // 2,
                  170, (141, 132, 165), 1)

    def _render_victory_img(self, s) -> None:
        s.fill((10, 7, 16))
        img = _load_victory_image()
        if img:
            iw, ih = img.get_size()
            s.blit(img, (SCREEN_W // 2 - iw // 2, (SCREEN_H - 30 - ih) // 2))
        else:
            # 이미지가 없을 때 안내
            msg = "PUT IMAGE IN SPRITES/VICTORY.PNG"
            draw_text(s, msg, SCREEN_W // 2 - text_width(msg) // 2,
                      SCREEN_H // 2 - 10, (255, 107, 107), 1)
        hint = "ENTER REMATCH"
        draw_text(s, hint, SCREEN_W // 2 - text_width(hint) // 2,
                  SCREEN_H - 20, (141, 132, 165), 1)

    def _render_paused(self, s) -> None:
        veil = pygame.Surface(s.get_size(), pygame.SRCALPHA)
        veil.fill((10, 7, 16, 190))
        s.blit(veil, (0, 0))
        draw_banner(s, "PAUSED", (232, 226, 240), 120, 3)
        t = "ESC RESUME   ENTER GIVE UP"
        draw_text(s, t, SCREEN_W // 2 - text_width(t) // 2, 150, (141, 132, 165), 1)

    def _render_title(self, s) -> None:
        s.fill((10, 7, 16))

        # 로고 이미지 로드 및 표시
        logo = _load_logo()
        if logo:
            lw, lh = logo.get_size()
            s.blit(logo, (SCREEN_W // 2 - lw // 2, 30))
        else:
            # 폴백: 텍스트로 표시
            draw_banner(s, TITLE, (255, 212, 71), 60, 4)

        # 도트 전환 애니메이션 (왼쪽에서 오른쪽으로 점차 나타남)
        dot_progress = int(self.title_anim * SCREEN_W * 1.5)

        if self.title_state == TITLE_MENU:
            # 메인 메뉴
            draw_text(s, "RANDOM 1V1 PIXEL FIGHTER", SCREEN_W // 2 - 78, 100, (232, 226, 240), 1)

            # 메뉴 버튼들
            y1, y2 = 140, 170
            sel_color = (255, 212, 71)
            normal_color = (141, 132, 165)

            # 플레이 버튼
            p_color = sel_color if self.menu_index == 0 else normal_color
            p_text = "> START <" if self.menu_index == 0 else "  START  "
            draw_text(s, p_text, SCREEN_W // 2 - text_width(p_text) // 2, y1, p_color, 2)

            # 닉네임 버튼
            n_color = sel_color if self.menu_index == 1 else normal_color
            n_text = "> NAME <" if self.menu_index == 1 else "  NAME  "
            draw_text(s, n_text, SCREEN_W // 2 - text_width(n_text) // 2, y2, n_color, 2)

            draw_text(s, "A D MOVE   W JUMP   S CROUCH   H BLOCK   J K L ATTACK",
                      SCREEN_W // 2 - text_width("A D MOVE   W JUMP   S CROUCH   H BLOCK   J K L ATTACK") // 2,
                      200, (141, 132, 165), 1)
            draw_text(s, "ESC PAUSE", SCREEN_W // 2 - text_width("ESC PAUSE") // 2, 220, (100, 92, 122), 1)

        elif self.title_state == TITLE_NICKNAME:
            # 닉네임 설정 화면
            label = "ENEMY NAME" if self.editing_enemy else "YOUR NAME"
            draw_text(s, label, SCREEN_W // 2 - text_width(label, 2) // 2, 100, (255, 212, 71), 2)

            # 이름 입력 필드
            cur = self.enemy_name if self.editing_enemy else self.nickname
            nick_display = cur + "_"
            draw_text(s, nick_display, SCREEN_W // 2 - text_width(nick_display, 2) // 2, 140, (232, 226, 240), 2)

            draw_text(s, "A-Z TYPE   BACKSPACE DELETE   ENTER DONE",
                      SCREEN_W // 2 - text_width("A-Z TYPE   BACKSPACE DELETE   ENTER DONE") // 2,
                      180, (141, 132, 165), 1)
            draw_text(s, "ESC BACK", SCREEN_W // 2 - text_width("ESC BACK") // 2, 200, (100, 92, 122), 1)

        # 도트 전환 효과 (픽셀 단위로 화면을 덮음)
        if self.title_anim < 1.0:
            for dy in range(0, SCREEN_H, 4):
                for dx in range(0, SCREEN_W, 4):
                    # 왼쪽에서 오른쪽으로 점차 사라짐
                    if dx < dot_progress - dy * 0.5:
                        continue
                    # 도트 그리기 (작은 사각형)
                    if (dx + dy) % 8 < 4:
                        surf_color = (10, 7, 16)
                        s.fill(surf_color, (dx, dy, 2, 2))

    # ---------------------------------------------------------------- 루프
    def run(self) -> None:
        while self.running:
            self._handle_events()
            self.step()
            self.render()
            self.pressed.clear()
            self._blit_view()
            pygame.display.flip()
            self.clock.tick(FPS)
        pygame.quit()