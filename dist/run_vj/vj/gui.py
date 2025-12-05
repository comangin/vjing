"""Module GUI: rendering du visualizer avec pygame.

La GUI lit `analyzer.latest_spectrum` et `analyzer.latest_rms` et les
affiche. L'API principale est `VisualGUI(analyzer).run()`.
"""
import math
from collections import deque
from typing import Optional


class VisualGUI:
    def __init__(self, analyzer, width: int = 800, height: int = 600, title: Optional[str] = None,
                 primary_color: Optional[tuple] = None, secondary_color: Optional[tuple] = None,
                 bg_color: Optional[tuple] = None, glitch_enabled: bool = True):
        self.analyzer = analyzer
        self.width = width
        self.height = height
        self.title = title or "VJ Visualizer"
        self._stop = False
        # Pour fond animé et particules
        self._bg_phase = 0.0
        self._particles = []  # chaque particule: [x, y, vx, vy, color, life]
        # lasers: chaque laser [x1,y1,x2,y2, vx, vy, color, life]
        self._lasers = []
        # glitch / overlays
        self._glitch_timer = 0
        self._glitch_enabled = bool(glitch_enabled)
        # backgrounds parameters (populated at run-time)
        self._bg_surfaces = []
        self._bg_sel_phase = 0.0
        # beat / rhythm helpers
        self._rms_history = deque(maxlen=60)
        self._beat_cooldown = 0
        self._last_beat = False
        # scene and smoothing
        self._scene_index = 0
        self._scene_timer = 0
        self._band_ema = {"low": 0.0, "mid": 0.0, "high": 0.0}
        self._ema_alpha = 0.18
        # performance caps
        self._max_particles = 800
        self._max_lasers = 120
        # visibility multiplier for lasers (can be changed per scene)
        self._laser_vis = 1.0
        # color palettes and background cycling
        self._palettes = [
            ((255, 90, 110), (40, 220, 140), (100, 120, 255)),  # neon red/green/blue
            ((200, 120, 255), (80, 240, 200), (255, 200, 80)),  # purple/cyan/orange
            ((30, 200, 120), (255, 90, 140), (180, 180, 255)),  # green/pink/soft-blue
            ((255, 240, 120), (160, 60, 200), (140, 255, 180)), # warm neon mix
        ]
        self._palette_index = 0
        self._palette_timer = 0
        # apply user-specified colors if present (primary/secondary/background)
        if primary_color or secondary_color or bg_color:
            p = (
                tuple(primary_color) if primary_color else self._palettes[0][0],
                tuple(secondary_color) if secondary_color else self._palettes[0][1],
                tuple(bg_color) if bg_color else self._palettes[0][2],
            )
            # put user palette first
            self._palettes.insert(0, p)

    def _draw(self, screen):
        import pygame
        import random
        with self.analyzer._spec_lock:
            spec = self.analyzer.latest_spectrum.copy()
            rms = float(self.analyzer.latest_rms)

        n = len(spec)
        center = (self.width // 2, self.height // 2)
        max_radius = min(self.width, self.height) // 2 - 20

        # --- compute band energies (bass/mid/high) ---
        # split spectrum into three bands
        b1 = max(1, n // 8)
        b2 = max(1, n // 3)
        low_energy = float(spec[:b1].sum()) / b1
        mid_energy = float(spec[b1:b2].sum()) / max(1, (b2 - b1))
        high_energy = float(spec[b2:].sum()) / max(1, (n - b2))
        total = low_energy + mid_energy + high_energy + 1e-9
        # normalized
        low_norm = low_energy / total
        mid_norm = mid_energy / total
        high_norm = high_energy / total

        # simple beat detection on RMS: detect when RMS jumps above running mean+std
        self._rms_history.append(rms)
        mean_rms = sum(self._rms_history) / len(self._rms_history)
        var = sum((x - mean_rms) ** 2 for x in self._rms_history) / len(self._rms_history)
        std_rms = math.sqrt(var)
        is_beat = False
        if self._beat_cooldown <= 0 and rms > mean_rms + max(0.002, 1.5 * std_rms):
            is_beat = True
            self._beat_cooldown = 10  # frames cooldown
        if self._beat_cooldown > 0:
            self._beat_cooldown -= 1

        # If we detected a beat, trigger some strong visual reactions
        if is_beat:
            # bass-directed laser burst
            burst_count = 3 + int(low_norm * 6)
            for j in range(burst_count):
                a = random.random() * math.tau
                x1 = center[0] + int((max_radius * 0.15) * math.cos(a))
                y1 = center[1] + int((max_radius * 0.15) * math.sin(a))
                x2 = center[0] + int((max_radius) * math.cos(a))
                y2 = center[1] + int((max_radius) * math.sin(a))
                # alternate red/green lasers based on index
                if j % 2 == 0:
                    color = (255, 30 + int(220 * low_norm), 60)
                else:
                    color = (30, 200, 30 + int(120 * low_norm))
                self._lasers.append([x1, y1, x2, y2, math.cos(a) * (6 + low_norm * 6), math.sin(a) * (6 + low_norm * 6), color, 30 + int(low_norm * 40)])
            # punch visual accents (no text) and extend scene timer
            self._scene_timer = max(self._scene_timer, 40)

        # --- FOND MULTI-IMAGE ANIMÉ ---
        # compute a low-frequency energy to drive background transitions
        k = max(1, n // 8)
        try:
            low_energy = float(spec[:k].sum()) / k
        except Exception:
            low_energy = float(sum(spec[:k])) / k
        # advance bg phases (faster, beat-influenced)
        self._bg_phase += 0.02 + rms * 0.08
        self._bg_sel_phase += 0.02 + low_energy * 0.12
        # force occasional immediate bg jump on strong beats
        if is_beat and random.random() < 0.5:
            # jump between 1 and 3 steps to change scene quickly
            self._bg_sel_phase += 1.0 + random.random() * 2.0

        # --- update EMA smoothed band values ---
        self._band_ema['low'] = (1.0 - self._ema_alpha) * self._band_ema['low'] + self._ema_alpha * low_norm
        self._band_ema['mid'] = (1.0 - self._ema_alpha) * self._band_ema['mid'] + self._ema_alpha * mid_norm
        self._band_ema['high'] = (1.0 - self._ema_alpha) * self._band_ema['high'] + self._ema_alpha * high_norm

        # --- scene manager: change scene occasionally on beats or phase ---
        if is_beat and random.random() < 0.33:
            self._scene_index = (self._scene_index + 1) % 4
            self._scene_timer = 90
        if self._scene_timer > 0:
            self._scene_timer -= 1

        # adjust scene-based parameters
        if self._scene_index == 0:
            self._laser_vis = 1.0 + self._band_ema['low'] * 1.6
        elif self._scene_index == 1:
            self._laser_vis = 1.6 + self._band_ema['low'] * 2.2
        elif self._scene_index == 2:
            self._laser_vis = 0.6 + self._band_ema['mid'] * 2.6
        else:
            self._laser_vis = 1.2 + self._band_ema['high'] * 2.0

        if not self._bg_surfaces:
            # fallback: draw a simple banded gradient if backgrounds missing
            bg = pygame.Surface((self.width, self.height))
            for i in range(10):
                frac = i / 10.0
                hue = (self._bg_phase + frac * 2.0 + rms * 2) % 1.0
                val = max(0, 1.0 - frac)
                r = int(30 + 180 * val * abs(math.sin(hue * math.pi)))
                g = int(20 + 140 * val * abs(math.sin((hue+0.33) * math.pi)))
                b = int(40 + 200 * val * abs(math.sin((hue+0.66) * math.pi)))
                radius = int(max_radius * (1.0 - frac) + 10)
                pygame.draw.circle(bg, (r, g, b), center, radius)
            screen.blit(bg, (0, 0))
        else:
            # choose two backgrounds and crossfade between them
            L = len(self._bg_surfaces)
            idx = int(self._bg_sel_phase) % L
            idx2 = (idx + 1) % L
            # animate offsets/rotation
            a1 = (self._bg_phase * 10) % 360
            a2 = (-self._bg_phase * 8) % 360
            s1 = self._bg_surfaces[idx]
            s2 = self._bg_surfaces[idx2]
            r1 = pygame.transform.rotozoom(s1, a1, 1.0 + 0.02 * math.sin(self._bg_phase))
            r2 = pygame.transform.rotozoom(s2, a2, 1.0 + 0.02 * math.cos(self._bg_phase))
            # center-blit and crossfade according to low_energy
            bx = (self.width - r1.get_width()) // 2
            by = (self.height - r1.get_height()) // 2
            screen.blit(r1, (bx, by))
            fade = min(1.0, low_energy * 3.5)
            overlay = r2.copy()
            overlay.set_alpha(int(255 * fade))
            bx2 = (self.width - overlay.get_width()) // 2
            by2 = (self.height - overlay.get_height()) // 2
            screen.blit(overlay, (bx2, by2), special_flags=pygame.BLEND_RGBA_ADD)
            # apply a palette tint overlay to make backgrounds change color more dramatically
            pal = self._palettes[self._palette_index]
            # choose tint intensity based on low and mid energy
            tint_strength = min(200, int(60 + 380 * (0.6 * self._band_ema['low'] + 0.4 * self._band_ema['mid'])))
            tint_col = pal[int((self._bg_sel_phase) % len(pal))]
            tint_surf = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            tint_surf.fill((tint_col[0], tint_col[1], tint_col[2], tint_strength))
            screen.blit(tint_surf, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

        # --- FLASH SYNCHRO BEAT --- (colored) using palette
        if rms > 0.12:
            alpha = min(255, int((rms - 0.12) * 1200))
            overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            pal = self._palettes[self._palette_index]
            # pulse between palette entries for variety (use scene/phase)
            cidx = (self._scene_index + int(self._bg_phase)) % len(pal)
            pc = pal[cidx]
            overlay.fill((pc[0], pc[1]//2, pc[2], alpha))
            screen.blit(overlay, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

        # --- PARTICULES RÉACTIVES AU SPECTRE + LASERS ---
        for i, mag in enumerate(spec):
            if mag > 0.65 and random.random() < mag * 0.25:
                angle = 2 * math.pi * i / n
                speed = 4 + mag * 10
                vx = math.cos(angle) * speed
                vy = math.sin(angle) * speed
                color = (random.randint(200,255), random.randint(100,230), random.randint(120,255))
                self._particles.append([
                    center[0], center[1], vx, vy, color, 30 + int(mag*30)
                ])
            # spawn lasers on strong peaks
            if mag > 0.9 and random.random() < 0.12:
                angle = 2 * math.pi * i / n
                x1 = center[0] + int((max_radius * 0.2) * math.cos(angle))
                y1 = center[1] + int((max_radius * 0.2) * math.sin(angle))
                x2 = center[0] + int((max_radius) * math.cos(angle))
                y2 = center[1] + int((max_radius) * math.sin(angle))
                # color from current palette with slight variance
                pal = self._palettes[self._palette_index]
                base = pal[i % len(pal)]
                color = (min(255, base[0] + random.randint(-30, 30)), min(255, base[1] + random.randint(-30, 30)), min(255, base[2] + random.randint(-30, 30)))
                self._lasers.append([x1, y1, x2, y2, math.cos(angle)*6, math.sin(angle)*6, color, 25])
        # Mid-energy driven particle burst (adds movement related to rhythm)
        spawn_mid = int(2 + mid_norm * 28)
        for _ in range(spawn_mid):
            a = random.random() * math.tau
            speed = 2 + mid_norm * 12
            vx = math.cos(a) * speed
            vy = math.sin(a) * speed
            color = (200 + int(55 * high_norm), 120 + int(100 * mid_norm), 180 + int(60 * high_norm))
            self._particles.append([center[0], center[1], vx, vy, color, 25 + int(mid_norm*40)])

        # Met à jour et dessine les particules
        new_particles = []
        for p in self._particles:
            p[0] += p[2]
            p[1] += p[3]
            p[5] -= 1
            if 0 <= p[0] < self.width and 0 <= p[1] < self.height and p[5] > 0:
                pygame.draw.circle(screen, p[4], (int(p[0]), int(p[1])), 3)
                new_particles.append(p)
        self._particles = new_particles

        # Met à jour et dessine les lasers
        new_lasers = []
        for L in self._lasers:
            # update position & life
            L[0] += L[4]
            L[1] += L[5]
            L[2] += L[4]
            L[3] += L[5]
            L[7] -= 1
            # render a glowy laser with multiple stacked strokes for bloom
            self._render_laser(screen, L)
            if -200 < L[0] < self.width + 200 and -200 < L[1] < self.height + 200 and L[7] > 0:
                new_lasers.append(L)
        self._lasers = new_lasers

        # Glitch effect occasionally (slice shifts)
        # glitch probability increased by high-frequency energy
        glitch_prob = min(0.02 + rms * 0.15 + high_norm * 0.45, 0.6)
        if self._glitch_timer <= 0 and random.random() < glitch_prob:
            self._glitch_timer = 6 + int(rms * 25 + high_norm * 30)
        if self._glitch_timer > 0:
            self._glitch_timer -= 1
            temp = screen.copy()
            for _ in range(6):
                h = random.randint(4, max(6, self.height//8))
                y0 = random.randint(0, max(0, self.height - h))
                shift = random.randint(-40, 40)
                rect = pygame.Rect(0, y0, self.width, h)
                slice_surf = temp.subsurface(rect).copy()
                screen.blit(slice_surf, (shift, y0))
                if random.random() < 0.4:
                    rsurf = slice_surf.copy()
                    rsurf.fill((255,0,0,80), special_flags=pygame.BLEND_RGBA_MULT)
                    screen.blit(rsurf, (shift//2, y0))

            # random glitch shapes / filters when enabled
            if self._glitch_enabled:
                pal = self._palettes[self._palette_index]
                shape_count = 2 + int(high_norm * 10)
                for _ in range(shape_count):
                    sx = random.randint(0, self.width)
                    sy = random.randint(0, self.height)
                    sw = random.randint(20, min(self.width//2, 200))
                    sh = random.randint(20, min(self.height//2, 200))
                    color = pal[random.randint(0, len(pal)-1)]
                    alpha = 40 + int(200 * random.random() * high_norm)
                    s = pygame.Surface((sw, sh), pygame.SRCALPHA)
                    # draw random rectangle or circle
                    if random.random() < 0.5:
                        s.fill((color[0], color[1], color[2], alpha))
                    else:
                        pygame.draw.ellipse(s, (color[0], color[1], color[2], alpha), s.get_rect())
                    blend = pygame.BLEND_RGBA_ADD if random.random() < 0.6 else 0
                    screen.blit(s, (sx - sw//2, sy - sh//2), special_flags=blend)

        # --- VISU RADIAL (amélioré, plus épais, couleurs dynamiques) ---
        for i in range(n):
            angle = 2 * math.pi * i / n
            mag = float(spec[i])
            inner = int(60 + (max_radius * 0.2))
            outer = int(inner + mag * (max_radius - inner))
            x1 = center[0] + int(inner * math.cos(angle))
            y1 = center[1] + int(inner * math.sin(angle))
            x2 = center[0] + int(outer * math.cos(angle))
            y2 = center[1] + int(outer * math.sin(angle))
            # Couleur dynamique selon l'angle et l'énergie
            hue = (self._bg_phase + angle/(2*math.pi)) % 1.0
            col = (
                min(255, int(120 + mag * 135 + 100 * abs(math.sin(hue * math.pi)))),
                min(255, int(30 + mag * 180 + 80 * abs(math.sin((hue+0.33) * math.pi)))),
                min(255, int(100 + mag * 155 + 80 * abs(math.sin((hue+0.66) * math.pi))))
            )
            pygame.draw.line(screen, col, (x1, y1), (x2, y2), 4)

        # Text overlay removed per user request; visuals use scenes and shapes instead.

        # scanlines overlay
        sl = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        for y in range(0, self.height, 4):
            alpha = 10 if (y//4) % 2 == 0 else 4
            sl.fill((0,0,0,alpha), rect=pygame.Rect(0, y, self.width, 2))
        screen.blit(sl, (0,0))

        pygame.display.flip()

    def _make_bg(self, seed_index: int):
        """Create a procedural background surface (called after pygame.init).

        Uses different patterns depending on seed_index to provide variety.
        """
        import pygame
        import random
        random.seed(seed_index + 7)
        surf = pygame.Surface((self.width, self.height)).convert_alpha()
        # base radial
        cx, cy = self.width // 2, self.height // 2
        max_r = int(min(self.width, self.height) * 0.8)
        for i in range(8, 0, -1):
            frac = i / 8.0
            hue = (seed_index * 0.21 + frac * 1.3) % 1.0
            r = int(20 + 220 * frac * abs(math.sin(hue * math.pi)))
            g = int(10 + 140 * frac * abs(math.cos((hue+0.33) * math.pi)))
            b = int(40 + 200 * frac * abs(math.sin((hue+0.66) * math.pi)))
            pygame.draw.circle(surf, (r, g, b, 140), (cx, cy), int(max_r * frac))

        # add some radial streaks
        for t in range(40):
            a = random.random() * math.tau
            rr = random.randint(int(max_r*0.3), max_r)
            x2 = cx + int(math.cos(a) * rr)
            y2 = cy + int(math.sin(a) * rr)
            col = (random.randint(80,200), random.randint(40,180), random.randint(80,240), 30)
            pygame.draw.line(surf, col, (cx, cy), (x2, y2), random.randint(1,3))

        # overlay some soft noise (random small circles)
        for _ in range(800):
            x = random.randrange(0, self.width)
            y = random.randrange(0, self.height)
            rr = random.randint(1, 3)
            c = (random.randint(0,60), random.randint(0,60), random.randint(0,60), 15)
            pygame.draw.circle(surf, c, (x, y), rr)

        # slight vignette
        vign = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        for i in range(100):
            a = int(200 * (i / 100.0))
            pygame.draw.circle(vign, (0, 0, 0, a//20), (cx, cy), int(max_r * (i/100.0)))
        surf.blit(vign, (0,0), special_flags=pygame.BLEND_RGBA_SUB)
        return surf

    def _render_laser(self, screen, laser):
        """Render a laser with glow layers. laser: [x1,y1,x2,y2, vx, vy, color, life]"""
        import pygame
        x1, y1, x2, y2, vx, vy, color, life = laser
        # intensity scales with life and laser_vis
        t = max(0.2, min(1.0, life / 40.0)) * self._laser_vis
        base_w = int(2 + 6 * t)
        # glow layers (outer -> inner)
        glow_colors = [
            (min(255, int(color[0]*0.6)), min(255, int(color[1]*0.6)), min(255, int(color[2]*0.6)), int(40 * t)),
            (min(255, int(color[0]*0.9)), min(255, int(color[1]*0.9)), min(255, int(color[2]*0.9)), int(80 * t)),
        ]
        # helper to coerce any color-like input to an RGB tuple (r,g,b) and alpha
        def _coerce_color(col, default=(255, 255, 255)):
            try:
                if col is None:
                    return default, 255
                # if it's a sequence (tuple/list/ndarray)
                if hasattr(col, '__len__'):
                    if len(col) >= 3:
                        r = int(col[0])
                        g = int(col[1])
                        b = int(col[2])
                        a = int(col[3]) if len(col) >= 4 else 255
                        r = max(0, min(255, r))
                        g = max(0, min(255, g))
                        b = max(0, min(255, b))
                        a = max(0, min(255, a))
                        return (r, g, b), a
                # single numeric grayscale
                v = int(col)
                v = max(0, min(255, v))
                return (v, v, v), 255
            except Exception:
                return default, 255

        # draw outer glows with additive blending, using safe color coercion
        for i, gc in enumerate(glow_colors):
            surf = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            w = base_w + (6 - i*3)
            (r, g, b), a = _coerce_color(gc)
            try:
                pygame.draw.line(surf, (r, g, b), (int(x1), int(y1)), (int(x2), int(y2)), max(1, w))
            except Exception:
                # fallback: draw a thinner white line if color failed
                pygame.draw.line(surf, (255, 255, 255), (int(x1), int(y1)), (int(x2), int(y2)), max(1, w))
            if a < 255:
                try:
                    surf.set_alpha(int(a))
                except Exception:
                    pass
            screen.blit(surf, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

        # core bright line (ensure color is valid RGB)
        rgb_color, _ = _coerce_color(color, default=(255, 255, 200))
        pygame.draw.line(screen, rgb_color, (int(x1), int(y1)), (int(x2), int(y2)), max(1, base_w // 2))
        # end caps
        pygame.draw.circle(screen, rgb_color, (int(x2), int(y2)), max(2, base_w // 2))

    def run(self):
        try:
            import pygame
        except Exception as e:
            raise RuntimeError(f"pygame requis pour la GUI: {e}")

        pygame.init()
        screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption(self.title)
        clock = pygame.time.Clock()

        # create procedural backgrounds now that pygame is initialized
        try:
            self._bg_surfaces = [self._make_bg(i) for i in range(4)]
        except Exception:
            # if something fails, leave _bg_surfaces empty and fallback is used in _draw
            self._bg_surfaces = []

        try:
            while not self._stop:
                for evt in pygame.event.get():
                    if evt.type == pygame.QUIT:
                        self._stop = True
                        break
                    if evt.type == pygame.KEYDOWN and evt.key == pygame.K_q:
                        self._stop = True
                        break

                self._draw(screen)
                clock.tick(30)
        finally:
            pygame.quit()
