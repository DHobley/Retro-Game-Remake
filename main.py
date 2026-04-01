"""
Snake: Cyber Edition  —  Python / pygame
Requirements: pip install pygame numpy
Run:          python main.py

Biome unlock thresholds (snake length):
  Easy   → length 7
  Medium → length 5
  Hard   → length 3
"""

import pygame, random, json, sys, math

# ── Constants ─────────────────────────────────────────────────────────────────
GRID    = 20
CELL    = 24
CANVAS  = GRID * CELL   # 480 px
HUD_H   = 80
WIN_W   = CANVAS
WIN_H   = CANVAS + HUD_H
FPS     = 60
HS_FILE = "snake_highscore.json"

BG      = (10,  12,  18)
GRID_C  = (20,  24,  32)
PRIMARY = (57,  255,  20)
ACCENT  = (255, 200,   0)
DIM     = (30,  80,   22)
TDIM    = (80,  80,   80)
RED     = (220,  50,  50)

BIOME_RGBA  = {"ice":(100,200,255,40),"wind":(180,100,255,40),
               "conveyor":(255,160,40,45),"low-gravity":(40,60,200,48)}
BIOME_LABEL = {"normal":"NORMAL","ice":"ICE ZONE","wind":"WIND ZONE",
               "conveyor":"CONVEYOR","low-gravity":"LOW-GRAV"}
BIOME_COL   = {"ice":(100,200,255),"wind":(180,100,255),
               "conveyor":(255,160,40),"low-gravity":(80,100,255)}
DIFFICULTY  = {"EASY":180,"MEDIUM":120,"HARD":100}

# Length at which biomes are inserted mid-game
BIOME_THRESHOLD = {"EASY": 7, "MEDIUM": 5, "HARD": 3}

DIRS     = {"UP":(0,-1),"DOWN":(0,1),"LEFT":(-1,0),"RIGHT":(1,0)}
OPPOSITE = {"UP":"DOWN","DOWN":"UP","LEFT":"RIGHT","RIGHT":"LEFT"}

# ── Helpers ───────────────────────────────────────────────────────────────────
def load_hs():
    try:
        with open(HS_FILE) as f: return json.load(f).get("hs", 0)
    except: return 0

def save_hs(v):
    try:
        with open(HS_FILE, "w") as f: json.dump({"hs": v}, f)
    except: pass

def rand_pos(exclude):
    while True:
        p = (random.randint(0, GRID-1), random.randint(0, GRID-1))
        if p not in exclude: return p

def txt(surf, text, font, col, cx, cy, anchor="center"):
    s = font.render(text, True, col); r = s.get_rect()
    if anchor == "center": r.center = (cx, cy)
    elif anchor == "left":  r.midleft  = (cx, cy)
    elif anchor == "right": r.midright = (cx, cy)
    surf.blit(s, r); return r

# ── Biome generation — one horizontal band per biome ─────────────────────────
def make_grid(enabled):
    """Return (grid, grid_dir) all-normal, then apply enabled biome bands."""
    grid     = [["normal"] * GRID for _ in range(GRID)]
    grid_dir = [[None]     * GRID for _ in range(GRID)]
    active = [b for b in enabled if b != "normal"]
    if not active:
        return grid, grid_dir
    shuffled = random.sample(active, len(active))
    spacing  = GRID / (len(shuffled) + 1)
    for i, biome in enumerate(shuffled):
        row = round(spacing * (i + 1))
        d = random.choice(["LEFT","RIGHT","UP","DOWN"]) if biome in ("wind","conveyor") else None
        for x in range(GRID):
            grid[row][x] = biome
            grid_dir[row][x] = d
    return grid, grid_dir

# ── Audio ─────────────────────────────────────────────────────────────────────
class Sound:
    def __init__(self):
        self.on = True
        try: pygame.mixer.init(44100, -16, 2, 512); self._ok = True
        except: self._ok = False

    def _tone(self, freq, ms, vol=0.22):
        if not self.on or not self._ok: return
        try:
            import numpy as np
            sr = 44100; n = int(sr * ms / 1000)
            t  = np.linspace(0, ms / 1000, n, False)
            w  = (np.sin(2 * np.pi * freq * t) * 32767 * vol).astype(np.int16)
            pygame.sndarray.make_sound(np.column_stack([w, w])).play()
        except: pass

    def eat(self):   self._tone(880, 80)
    def bonus(self): self._tone(1046, 70)
    def over(self):
        for f in [440, 349, 293, 220]: self._tone(f, 130)
    def biome(self, b):
        self._tone({"ice":523,"wind":659,"conveyor":349,"low-gravity":261}.get(b, 440), 160, 0.14)
    def unlock(self):
        """Rising arpeggio played when biomes first unlock."""
        for i, f in enumerate([392, 523, 659, 784]):
            pygame.time.set_timer(pygame.USEREVENT + 20 + i, 80 * i + 10, loops=1)
        self._tone(392, 90, 0.2)
    def click(self): self._tone(440, 60, 0.12)

# ── Game ──────────────────────────────────────────────────────────────────────
class Game:
    IDLE = "IDLE"; PLAY = "PLAY"; PAUSE = "PAUSE"; OVER = "OVER"; SETT = "SETT"

    def __init__(self):
        pygame.init()
        self.scr   = pygame.display.set_mode((WIN_W, WIN_H))
        pygame.display.set_caption("Snake: Cyber Edition")
        self.clock = pygame.time.Clock()
        mono = "Courier New" if sys.platform == "win32" else "DejaVu Sans Mono"
        self.fxl = pygame.font.SysFont(mono, 42, bold=True)
        self.flg = pygame.font.SysFont(mono, 26, bold=True)
        self.fmd = pygame.font.SysFont(mono, 16, bold=True)
        self.fsm = pygame.font.SysFont(mono, 12)
        self.snd  = Sound()
        self.hs   = load_hs()
        self.diff = "MEDIUM"
        self.biomes = {"ice": True, "wind": True, "conveyor": True, "low-gravity": True}
        self.status   = self.IDLE
        self._bsurf   = {}
        self._trects  = {}
        self._prev    = self.IDLE
        self._sett_tab = 0   # 0 = settings, 1 = how to play
        self._reset()

    # ── Biome tint surface ────────────────────────────────────────────────────
    def _bsuf(self, b):
        if b not in self._bsurf:
            s = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
            s.fill(BIOME_RGBA[b])
            self._bsurf[b] = s
        return self._bsurf[b]

    # ── Reset ─────────────────────────────────────────────────────────────────
    def _reset(self):
        cx = cy = GRID // 2
        self.snake  = [(cx, cy), (cx, cy+1), (cx, cy+2)]
        self.dir    = "UP"; self.ndir = "UP"
        self.score  = 0;    self.ms   = 0;   self.tc = 0
        self.lgskip = False
        self.lbiome = "normal"; self.abiome = "normal"; self.adir = None
        self.sfood  = None;     self.sexp   = 0
        self.unlocked = False   # biomes not yet activated

        # Start with a fully normal grid — biomes appear at threshold
        self.grid, self.gdir = make_grid([])

    @property
    def speed(self):
        return max(40, int(DIFFICULTY[self.diff] * 0.98 ** (self.score // 50)))

    @property
    def threshold(self):
        return BIOME_THRESHOLD[self.diff]

    # ── Biome unlock check ────────────────────────────────────────────────────
    def _check_unlock(self):
        if self.unlocked: return
        if len(self.snake) >= self.threshold:
            self.unlocked = True
            enabled = [b for b, on in self.biomes.items() if on]
            self.grid, self.gdir = make_grid(enabled)
            self.lbiome = "normal"; self.abiome = "normal"; self.adir = None
            self.snd.unlock()

    # ── Input ─────────────────────────────────────────────────────────────────
    def _start(self, d=None):
        if d: self.diff = d
        self._reset(); self.status = self.PLAY

    def _pause(self):
        self.snd.click()
        self.status = self.PAUSE if self.status == self.PLAY else self.PLAY

    def _gameover(self):
        self.status = self.OVER; self.snd.over()
        if self.score > self.hs: self.hs = self.score; save_hs(self.hs)

    def _key(self, k):
        s = self.status
        if k in (pygame.K_SPACE, pygame.K_RETURN):
            if s in (self.IDLE, self.OVER): self._start()
            elif s in (self.PLAY, self.PAUSE): self._pause()
            return
        if k == pygame.K_ESCAPE:
            if s == self.SETT: self.status = self._prev
            elif s == self.PLAY: self._pause()
            return
        if k == pygame.K_TAB:
            if s != self.SETT:
                self._prev = s
                if s == self.PLAY: self.snd.click(); self.status = self.PAUSE
                self.status = self.SETT
            else: self.status = self._prev
            return
        if s == self.SETT:
            if k in (pygame.K_LEFT, pygame.K_RIGHT):
                self._sett_tab = 1 - self._sett_tab
            return
        if k == pygame.K_1: self.diff = "EASY"
        if k == pygame.K_2: self.diff = "MEDIUM"
        if k == pygame.K_3: self.diff = "HARD"
        if s == self.PLAY:
            M = {pygame.K_UP:"UP", pygame.K_w:"UP",
                 pygame.K_DOWN:"DOWN", pygame.K_s:"DOWN",
                 pygame.K_LEFT:"LEFT", pygame.K_a:"LEFT",
                 pygame.K_RIGHT:"RIGHT", pygame.K_d:"RIGHT"}
            if k in M:
                nd = M[k]
                if nd != OPPOSITE.get(self.dir): self.ndir = nd

    def _click_sett(self, pos):
        for k, r in self._trects.items():
            if r.collidepoint(pos):
                if k == "_tab0": self._sett_tab = 0
                elif k == "_tab1": self._sett_tab = 1
                elif k == "audio": self.snd.on = not self.snd.on
                else: self.biomes[k] = not self.biomes[k]

    # ── Game tick ─────────────────────────────────────────────────────────────
    def _tick(self, dt):
        if self.status != self.PLAY: return
        self.ms += dt
        if self.ms < self.speed: return
        self.ms -= self.speed; self.tc += 1

        hx, hy = self.snake[0]
        bm = self.grid[hy][hx]; bd = self.gdir[hy][hx]

        if bm == "low-gravity":
            self.lgskip = not self.lgskip
            if self.lgskip: return
        else: self.lgskip = False

        if   bm == "ice": ed = self.dir
        elif bm == "conveyor" and bd: ed = bd if bd != OPPOSITE.get(self.dir) else self.dir
        elif bm == "wind" and bd and self.tc % 3 == 0: ed = bd if bd != OPPOSITE.get(self.dir) else self.ndir
        else: ed = self.ndir
        self.dir = ed

        dx, dy = DIRS[ed]; nx, ny = hx + dx, hy + dy
        if not (0 <= nx < GRID and 0 <= ny < GRID): self._gameover(); return
        if (nx, ny) in self.snake: self._gameover(); return
        self.snake.insert(0, (nx, ny))

        # Biome change notification
        nb = self.grid[ny][nx]
        if nb != self.lbiome:
            self.lbiome = nb; self.abiome = nb; self.adir = self.gdir[ny][nx]
            self.snd.biome(nb)

        # Food
        ate = False
        if (nx, ny) == self.food:
            self.score += 10; self.food = rand_pos(self.snake); self.snd.eat(); ate = True
            if not self.sfood and random.random() < 0.15:
                self.sfood = rand_pos(self.snake + [self.food])
                self.sexp  = pygame.time.get_ticks() + 5000
        if self.sfood and (nx, ny) == self.sfood:
            self.score += 50; self.sfood = None; self.snd.eat(); ate = True
        if not ate: self.snake.pop()
        if self.sfood and pygame.time.get_ticks() > self.sexp: self.sfood = None

        # Check biome unlock AFTER snake may have grown
        self._check_unlock()

    # ── Draw canvas ───────────────────────────────────────────────────────────
    def _canvas(self):
        self.scr.fill(BG)
        for y in range(GRID):
            for x in range(GRID):
                pygame.draw.rect(self.scr, GRID_C, (x*CELL, HUD_H+y*CELL, CELL, CELL), 1)

        for y in range(GRID):
            for x in range(GRID):
                b = self.grid[y][x]
                if b != "normal":
                    self.scr.blit(self._bsuf(b), (x*CELL, HUD_H+y*CELL))
                bd = self.gdir[y][x]
                if b in ("conveyor","wind") and bd and x % 4 == 2:
                    a = {"UP":"↑","DOWN":"↓","LEFT":"←","RIGHT":"→"}.get(bd, "")
                    s = self.fsm.render(a, True, BIOME_COL.get(b, PRIMARY))
                    s.set_alpha(80); self.scr.blit(s, (x*CELL+7, HUD_H+y*CELL+5))

        # Food
        fx, fy = self.food
        pygame.draw.rect(self.scr, PRIMARY, (fx*CELL+3, HUD_H+fy*CELL+3, CELL-6, CELL-6), border_radius=2)
        # Special food
        if self.sfood:
            sx, sy = self.sfood; p = abs(math.sin(pygame.time.get_ticks()/250)) * 30
            pygame.draw.rect(self.scr, (255, int(180+p), 0), (sx*CELL+2, HUD_H+sy*CELL+2, CELL-4, CELL-4), border_radius=3)
        # Snake
        for i, (sx, sy) in enumerate(self.snake):
            ih = i == 0
            c  = PRIMARY if ih else (30, max(20, 180 - i), 18)
            pygame.draw.rect(self.scr, c, (sx*CELL+1, HUD_H+sy*CELL+1, CELL-2, CELL-2), border_radius=2 if ih else 1)
            if ih:
                pygame.draw.rect(self.scr, (200,255,180), (sx*CELL+1, HUD_H+sy*CELL+1, CELL-2, CELL-2), 1, border_radius=2)

    # ── HUD ───────────────────────────────────────────────────────────────────
    def _hud(self):
        pygame.draw.rect(self.scr, (14,16,24), (0, 0, WIN_W, HUD_H))
        pygame.draw.line(self.scr, (30,60,25), (0, HUD_H), (WIN_W, HUD_H))
        txt(self.scr, f"{self.score:04d}", self.flg, PRIMARY, 10, 24, "left")
        txt(self.scr, self.diff, self.fsm, DIM, 10, 48, "left")
        txt(self.scr, "HI-SCORE", self.fsm, TDIM, WIN_W//2, 16, "center")
        txt(self.scr, f"{self.hs:04d}",  self.flg, ACCENT, WIN_W//2, 40, "center")

        # Biome unlock progress or active zone
        if self.status == self.PLAY or self.status == self.PAUSE:
            if not self.unlocked:
                # Draw progress pips
                thr = self.threshold; ln = len(self.snake)
                txt(self.scr, "BIOMES", self.fsm, TDIM, WIN_W-120, 20, "left")
                for i in range(thr):
                    col = PRIMARY if i < ln else GRID_C
                    pygame.draw.rect(self.scr, col, (WIN_W-120 + i*10, 34, 8, 8))
                txt(self.scr, f"{ln}/{thr}", self.fsm, TDIM, WIN_W-10, 38, "right")
            elif self.abiome != "normal":
                c = BIOME_COL.get(self.abiome, PRIMARY)
                txt(self.scr, f"[ {BIOME_LABEL[self.abiome]} ]", self.fsm, c, WIN_W-8, 32, "right")

        txt(self.scr, "[TAB] Settings   [SPACE] Pause", self.fsm, TDIM, WIN_W//2, HUD_H-12, "center")

    # ── Overlay helpers ───────────────────────────────────────────────────────
    def _overlay(self, a=200):
        s = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        s.fill((10, 12, 18, a)); self.scr.blit(s, (0, 0))

    def _draw_idle(self):
        self._overlay(210)
        txt(self.scr, "SNAKE",        self.fxl, PRIMARY, WIN_W//2, 120, "center")
        txt(self.scr, "CYBER EDITION",self.fsm, (PRIMARY[0], PRIMARY[1]//2, 0), WIN_W//2, 168, "center")
        txt(self.scr, "SELECT DIFFICULTY", self.fsm, TDIM, WIN_W//2, 212, "center")
        for i, (lbl, key) in enumerate([("1  EASY","EASY"),("2  MEDIUM","MEDIUM"),("3  HARD","HARD")]):
            y = 245 + i * 52; sel = self.diff == key
            c = PRIMARY if sel else (40, 120, 35)
            r = pygame.Rect(WIN_W//2-110, y-17, 220, 36)
            if sel: pygame.draw.rect(self.scr, (10, 40, 8), r)
            pygame.draw.rect(self.scr, c, r, 2 if sel else 1)
            txt(self.scr, lbl, self.fmd, c, WIN_W//2, y, "center")

        # Show thresholds
        lines = [
            ("EASY:    biomes unlock at snake length 7", (40, 100, 35)),
            ("MEDIUM:  biomes unlock at snake length 5", (40, 100, 35)),
            ("HARD:    biomes unlock at snake length 3", (40, 100, 35)),
        ]
        for j, (line, col) in enumerate(lines):
            txt(self.scr, line, self.fsm, col, WIN_W//2, 413 + j*16, "center")

        txt(self.scr, "SPACE / ENTER to start", self.fsm, DIM,  WIN_W//2, 470, "center")
        txt(self.scr, "[TAB] Settings",         self.fsm, TDIM, WIN_W//2, 490, "center")

    def _draw_pause(self):
        self._overlay(180)
        a = abs(math.sin(pygame.time.get_ticks() / 700))
        c = tuple(int(v * (0.5 + 0.5*a)) for v in PRIMARY)
        txt(self.scr, "PAUSED",          self.fxl, c,   WIN_W//2, WIN_H//2-30, "center")
        txt(self.scr, "SPACE to resume", self.fsm, DIM,  WIN_W//2, WIN_H//2+28, "center")
        txt(self.scr, "[TAB] Settings",  self.fsm, TDIM, WIN_W//2, WIN_H//2+54, "center")

    def _draw_over(self):
        self._overlay(210)
        txt(self.scr, "GAME OVER", self.fxl, RED, WIN_W//2, 118, "center")
        r = pygame.Rect(WIN_W//2-120, 155, 240, 84)
        pygame.draw.rect(self.scr, (20,8,8), r); pygame.draw.rect(self.scr, (120,30,30), r, 1)
        txt(self.scr, f"SCORE:  {self.score:04d}", self.fmd, PRIMARY, WIN_W//2, 188, "center")
        txt(self.scr, f"BEST:   {self.hs:04d}",   self.fmd, ACCENT,  WIN_W//2, 222, "center")
        txt(self.scr, "SELECT DIFFICULTY", self.fsm, TDIM, WIN_W//2, 278, "center")
        for i, (lbl, key) in enumerate([("1  EASY","EASY"),("2  MEDIUM","MEDIUM"),("3  HARD","HARD")]):
            y = 308 + i * 46; sel = self.diff == key
            c = PRIMARY if sel else (40, 120, 35)
            r = pygame.Rect(WIN_W//2-100, y-15, 200, 32)
            if sel: pygame.draw.rect(self.scr, (10,40,8), r)
            pygame.draw.rect(self.scr, c, r, 2 if sel else 1)
            txt(self.scr, lbl, self.fmd, c, WIN_W//2, y, "center")
        txt(self.scr, "SPACE / ENTER to play again", self.fsm, DIM, WIN_W//2, 454, "center")

    def _draw_sett(self):
        self._overlay(230); self._trects = {}

        # ── Tab bar ───────────────────────────────────────────────────────────
        tab_labels = ["SETTINGS", "HOW TO PLAY"]
        tab_w = WIN_W // 2
        for i, lbl in enumerate(tab_labels):
            active = self._sett_tab == i
            r = pygame.Rect(i * tab_w, 0, tab_w, 44)
            pygame.draw.rect(self.scr, (18, 22, 14) if active else (10, 12, 18), r)
            pygame.draw.rect(self.scr, PRIMARY if active else (40, 60, 35), r, 1)
            txt(self.scr, lbl, self.fmd, PRIMARY if active else (60, 90, 55), r.centerx, r.centery, "center")
            self._trects[f"_tab{i}"] = r
        pygame.draw.line(self.scr, PRIMARY, (0, 44), (WIN_W, 44), 1)

        hint_y = WIN_H - 22
        txt(self.scr, "← → switch tabs   [ESC]/[TAB] close", self.fsm, TDIM, WIN_W//2, hint_y, "center")

        # ── TAB 0: Settings ───────────────────────────────────────────────────
        if self._sett_tab == 0:
            y = 66
            txt(self.scr, "BIOMES", self.fsm, TDIM, 28, y, "left"); y += 22
            items = [("ice",         "ICE ZONE",  "Slides straight — direction locked"),
                     ("wind",        "WIND ZONE", "Drift pushes every 3 ticks"),
                     ("conveyor",    "CONVEYOR",  "Belt overrides direction"),
                     ("low-gravity", "LOW-GRAV",  "Half-speed zone")]
            for key, lbl, hint in items:
                on = self.biomes[key]; c = PRIMARY if on else (50, 70, 50)
                box = pygame.Rect(28, y-9, 32, 18); pygame.draw.rect(self.scr, c, box, 2)
                if on: pygame.draw.rect(self.scr, PRIMARY, pygame.Rect(box.right-15, box.y+2, 11, 13))
                txt(self.scr, lbl,  self.fmd, c,    70, y,    "left")
                txt(self.scr, hint, self.fsm, TDIM, 70, y+15, "left")
                self._trects[key] = box; y += 46

            pygame.draw.line(self.scr, (30, 50, 25), (28, y), (WIN_W-28, y)); y += 14
            txt(self.scr, "BIOME UNLOCK THRESHOLDS", self.fsm, TDIM, 28, y, "left"); y += 18
            for diff, thr in [("EASY","7"),("MEDIUM","5"),("HARD","3")]:
                txt(self.scr, f"{diff}", self.fsm, (60, 120, 50), 28,  y, "left")
                txt(self.scr, f"snake length {thr}", self.fsm, TDIM, 110, y, "left")
                y += 16

            pygame.draw.line(self.scr, (30, 50, 25), (28, y+2), (WIN_W-28, y+2)); y += 18
            txt(self.scr, "AUDIO + HAPTICS", self.fsm, TDIM, 28, y, "left"); y += 22
            on = self.snd.on; c = PRIMARY if on else (50, 70, 50)
            ba = pygame.Rect(28, y-9, 32, 18); pygame.draw.rect(self.scr, c, ba, 2)
            if on: pygame.draw.rect(self.scr, PRIMARY, pygame.Rect(ba.right-15, ba.y+2, 11, 13))
            txt(self.scr, "AUDIO  (music + sound effects)", self.fmd, c, 70, y, "left")
            self._trects["audio"] = ba

        # ── TAB 1: How to Play ────────────────────────────────────────────────
        else:
            y = 66
            txt(self.scr, "CONTROLS", self.fsm, TDIM, 28, y, "left"); y += 20
            controls = [
                ("W  /  ↑",          "Move up"),
                ("S  /  ↓",          "Move down"),
                ("A  /  ←",          "Move left"),
                ("D  /  →",          "Move right"),
                ("SPACE / ENTER",     "Pause or start game"),
                ("TAB",               "Open / close settings"),
                ("1 / 2 / 3",         "Select difficulty"),
            ]
            for keys, action in controls:
                kb_r = pygame.Rect(28, y-8, 140, 17)
                pygame.draw.rect(self.scr, (18, 35, 14), kb_r, border_radius=2)
                pygame.draw.rect(self.scr, (40, 80, 35), kb_r, 1, border_radius=2)
                txt(self.scr, keys,   self.fsm, PRIMARY, 34,        y, "left")
                txt(self.scr, action, self.fsm, TDIM,    WIN_W-28,  y, "right")
                y += 20

            pygame.draw.line(self.scr, (30, 50, 25), (28, y+2), (WIN_W-28, y+2)); y += 18
            txt(self.scr, "HOW TO PLAY", self.fsm, TDIM, 28, y, "left"); y += 20
            tips = [
                ("🟩 +10 pts", "Eat green food — your snake grows"),
                ("✦  +50 pts", "Grab golden bonus before it expires (5s)"),
                ("💀 Avoid",   "Walls and your own tail end the run"),
                ("⚡ Speed",   "Gets faster as your score increases"),
                ("🗺  Biomes",  "Unlock mid-game and change how you move"),
            ]
            for icon, tip in tips:
                txt(self.scr, icon, self.fsm, ACCENT,   28,       y, "left")
                txt(self.scr, tip,  self.fsm, TDIM,     28+82,    y, "left")
                y += 20

            pygame.draw.line(self.scr, (30, 50, 25), (28, y+2), (WIN_W-28, y+2)); y += 18
            txt(self.scr, "SCORING", self.fsm, TDIM, 28, y, "left"); y += 20
            scoring = [
                ("Green food",   "+10 points per piece"),
                ("Golden bonus", "+50 points — appears at random"),
                ("High score",   "Saved automatically between runs"),
            ]
            for label, detail in scoring:
                txt(self.scr, label,  self.fsm, (80, 180, 70), 28,       y, "left")
                txt(self.scr, detail, self.fsm, TDIM,          WIN_W-28, y, "right")
                y += 18

    # ── Main loop ─────────────────────────────────────────────────────────────
    def run(self):
        while True:
            dt = self.clock.tick(FPS)
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT: pygame.quit(); sys.exit()
                if ev.type == pygame.KEYDOWN: self._key(ev.key)
                if ev.type == pygame.MOUSEBUTTONDOWN and self.status == self.SETT:
                    self._click_sett(ev.pos)

            self._tick(dt)
            self._canvas(); self._hud()
            if   self.status == self.IDLE:  self._draw_idle()
            elif self.status == self.PAUSE: self._draw_pause()
            elif self.status == self.OVER:  self._draw_over()
            elif self.status == self.SETT:  self._draw_sett()
            pygame.display.flip()


if __name__ == "__main__":
    Game().run()
