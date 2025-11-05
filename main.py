"""Run the Tomb of the Mask inspired neon platformer."""
from __future__ import annotations

import json
import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pygame

from level import TILE_SIZE, NeonLevel

SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS = 60
GRAVITY = 1860.0
MOVE_SPEED = 320.0
ACCEL = 2600.0
DECEL = 3200.0
JUMP_SPEED = 640.0
TERMINAL_VELOCITY = 1220.0
AIR_DASH_SPEED = 580.0
SCORE_FILE = Path(__file__).with_name("scores.json")
SCORE_LIMIT = 12


POWERUP_DEFINITIONS: Dict[str, Dict[str, object]] = {
    "double_jump": {
        "label": "Salto Fantasma",
        "color": (241, 255, 134),
        "duration": 12.0,
        "max_air_jumps": 1,
    },
    "dash": {
        "label": "Rajada",
        "color": (109, 255, 247),
        "duration": 8.0,
        "dash_speed": AIR_DASH_SPEED,
    },
    "magnet": {
        "label": "Ímã Plasma",
        "color": (255, 154, 214),
        "duration": 9.5,
        "magnet_radius": 180,
    },
    "phase": {
        "label": "Fase Spectral",
        "color": (188, 132, 255),
        "duration": 6.5,
        "phase_opacity": 70,
    },
    "slow": {
        "label": "Dobra Temporal",
        "color": (255, 230, 124),
        "duration": 5.5,
        "time_scale": 0.55,
    },
}


@dataclass
class ScoreEntry:
    name: str
    score: int


class Scoreboard:
    """Manage persistent neon leaderboards."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries: List[ScoreEntry] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self.entries = []
            return
        try:
            data = json.loads(self.path.read_text("utf8"))
            self.entries = [ScoreEntry(item["name"], int(item["score"])) for item in data]
        except Exception:
            self.entries = []

    def record(self, name: str, score: int) -> None:
        self.entries.append(ScoreEntry(name=name[:12].strip() or "Jogador", score=score))
        self.entries.sort(key=lambda entry: entry.score, reverse=True)
        self.entries = self.entries[:SCORE_LIMIT]
        self._save()

    def _save(self) -> None:
        payload = [entry.__dict__ for entry in self.entries]
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf8")


@dataclass
class GlowTrailSegment:
    position: pygame.Vector2
    life: float
    radius: float


class GlowTrail:
    def __init__(self, color: Tuple[int, int, int]) -> None:
        self.color = color
        self.segments: List[GlowTrailSegment] = []

    def emit(self, position: pygame.Vector2) -> None:
        self.segments.append(
            GlowTrailSegment(position=position.copy(), life=0.35, radius=random.uniform(6.0, 14.0))
        )

    def update(self, dt: float) -> None:
        for segment in list(self.segments):
            segment.life -= dt
            segment.radius *= 0.98
            if segment.life <= 0:
                self.segments.remove(segment)

    def draw(self, surface: pygame.Surface, camera: pygame.Rect) -> None:
        glow_surface = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        for segment in self.segments:
            pos = segment.position - pygame.Vector2(camera.topleft)
            alpha = max(0, min(255, int(255 * (segment.life / 0.35))))
            color = (*self.color, alpha)
            pygame.draw.circle(glow_surface, color, (int(pos.x), int(pos.y)), int(segment.radius))
        surface.blit(glow_surface, (0, 0), special_flags=pygame.BLEND_ADD)


@dataclass
class FloatingText:
    text: str
    position: pygame.Vector2
    velocity: pygame.Vector2
    time_to_live: float
    color: Tuple[int, int, int]

    def update(self, dt: float) -> None:
        self.position += self.velocity * dt
        self.time_to_live -= dt
        self.velocity.y -= 60 * dt


class FloatingTextManager:
    def __init__(self, font: pygame.font.Font) -> None:
        self.font = font
        self.texts: List[FloatingText] = []

    def spawn(self, text: str, position: pygame.Vector2, color: Tuple[int, int, int]) -> None:
        jitter = pygame.Vector2(random.uniform(-10, 10), random.uniform(-5, 5))
        velocity = pygame.Vector2(0, -38) + jitter
        self.texts.append(
            FloatingText(text, position.copy(), velocity, 1.2, color)
        )

    def update(self, dt: float) -> None:
        for floating in list(self.texts):
            floating.update(dt)
            if floating.time_to_live <= 0:
                self.texts.remove(floating)

    def draw(self, surface: pygame.Surface, camera: pygame.Rect) -> None:
        for floating in self.texts:
            pos = floating.position - pygame.Vector2(camera.topleft)
            alpha = max(0, min(255, int(255 * (floating.time_to_live / 1.2))))
            text_surf = self.font.render(floating.text, True, floating.color)
            text_surf.set_alpha(alpha)
            surface.blit(text_surf, pos)


@dataclass
class Particle:
    position: pygame.Vector2
    velocity: pygame.Vector2
    color: Tuple[int, int, int]
    life: float
    size: float

    def update(self, dt: float) -> None:
        self.position += self.velocity * dt
        self.velocity.y += GRAVITY * 0.1 * dt
        self.life -= dt
        self.size *= 0.96


class ParticleSystem:
    def __init__(self) -> None:
        self.particles: List[Particle] = []

    def emit(self, position: pygame.Vector2, color: Tuple[int, int, int], amount: int = 6) -> None:
        for _ in range(amount):
            velocity = pygame.Vector2(random.uniform(-90, 90), random.uniform(-220, -60))
            self.particles.append(
                Particle(position.copy(), velocity, color, life=random.uniform(0.35, 0.7), size=random.uniform(3, 5))
            )

    def update(self, dt: float) -> None:
        for particle in list(self.particles):
            particle.update(dt)
            if particle.life <= 0:
                self.particles.remove(particle)

    def draw(self, surface: pygame.Surface, camera: pygame.Rect) -> None:
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        for particle in self.particles:
            pos = particle.position - pygame.Vector2(camera.topleft)
            alpha = max(0, min(255, int(255 * (particle.life / 0.7))))
            pygame.draw.circle(
                overlay,
                (*particle.color, alpha),
                (int(pos.x), int(pos.y)),
                int(max(1, particle.size)),
            )
        surface.blit(overlay, (0, 0), special_flags=pygame.BLEND_ADD)


@dataclass
class PowerUpState:
    key: str
    remaining: float


class Player:
    def __init__(self, position: Tuple[float, float]) -> None:
        self.position = pygame.Vector2(position)
        self.velocity = pygame.Vector2(0, 0)
        self.rect = pygame.Rect(0, 0, 24, 28)
        self.on_ground = False
        self.jump_buffer = 0.0
        self.coyote_timer = 0.0
        self.max_air_jumps = 0
        self.air_jumps_used = 0
        self.active_powerups: Dict[str, PowerUpState] = {}
        self.glow_trail = GlowTrail((255, 226, 120))
        self.sprite_frames = self._build_sprite_frames()
        self.frame_time = 0.0
        self.frame_index = 0
        self.dash_cooldown = 0.0
        self.time_scale = 1.0
        self.phase_opacity = 255
        self.invulnerable_time = 0.0

    def _build_sprite_frames(self) -> List[pygame.Surface]:
        palette = {
            "mask": (255, 230, 120),
            "body": (36, 14, 42),
            "outline": (0, 0, 0),
            "glow": (118, 255, 200),
        }
        width, height = self.rect.width, self.rect.height
        frames = []
        for phase in range(4):
            surf = pygame.Surface((width, height), pygame.SRCALPHA)
            surf.fill((0, 0, 0, 0))
            pygame.draw.rect(surf, palette["outline"], (4, 2, width - 8, height - 4))
            pygame.draw.rect(surf, palette["body"], (6, 4, width - 12, height - 8))
            pygame.draw.rect(surf, palette["mask"], (8, 6, width - 16, 16))
            eye_color = (255, 255, 255)
            pygame.draw.rect(surf, eye_color, (width // 2 - 5 + phase % 2, 10, 3, 3))
            pygame.draw.rect(surf, eye_color, (width // 2 + 2 + phase % 2, 10, 3, 3))
            glow = pygame.Surface((width, height), pygame.SRCALPHA)
            pygame.draw.ellipse(glow, (*palette["glow"], 120), glow.get_rect().inflate(16, 12))
            glow.blit(surf, (0, 0), special_flags=pygame.BLEND_ADD)
            surf.blit(glow, (0, 0), special_flags=pygame.BLEND_ADD)
            frames.append(surf)
        return frames

    def update(self, dt: float, level: NeonLevel, inputs: Sequence[bool]) -> None:
        dt *= self.time_scale
        self.glow_trail.update(dt)
        self._tick_powerups(dt)
        self._handle_input(dt, level, inputs)
        self._apply_gravity(dt)
        self._move(level, dt)
        self._update_animation(dt)
        if self.invulnerable_time > 0:
            self.invulnerable_time = max(0.0, self.invulnerable_time - dt)

    def _handle_input(self, dt: float, level: NeonLevel, inputs: Sequence[bool]) -> None:
        left, right, jump, dash = inputs
        movement = 0.0
        if left:
            movement -= 1.0
        if right:
            movement += 1.0
        accel = ACCEL * dt
        if movement != 0:
            target = movement * MOVE_SPEED
            if abs(self.velocity.x - target) < accel:
                self.velocity.x = target
            else:
                self.velocity.x += accel * math.copysign(1.0, target - self.velocity.x)
        else:
            if self.velocity.x > 0:
                self.velocity.x = max(0, self.velocity.x - DECEL * dt)
            elif self.velocity.x < 0:
                self.velocity.x = min(0, self.velocity.x + DECEL * dt)
        self.jump_buffer = min(0.25, self.jump_buffer + dt) if jump else 0.0
        if self.on_ground:
            self.air_jumps_used = 0
            self.coyote_timer = 0.1
        else:
            self.coyote_timer = max(0.0, self.coyote_timer - dt)
        if jump and (self.on_ground or self.coyote_timer > 0 or self.air_jumps_used < self.max_air_jumps):
            self.velocity.y = -JUMP_SPEED
            if not self.on_ground and self.coyote_timer <= 0:
                self.air_jumps_used += 1
            self.on_ground = False
            self.jump_buffer = 0.0
            self.coyote_timer = 0.0
        if dash and self.dash_cooldown <= 0 and "dash" in self.active_powerups:
            direction = math.copysign(1.0, self.velocity.x or movement or 1.0)
            self.velocity.x = direction * POWERUP_DEFINITIONS["dash"]["dash_speed"]
            self.dash_cooldown = 0.9
            self.glow_trail.emit(self.position + pygame.Vector2(self.rect.width / 2, self.rect.height / 2))
        if self.dash_cooldown > 0:
            self.dash_cooldown = max(0.0, self.dash_cooldown - dt)

    def _apply_gravity(self, dt: float) -> None:
        self.velocity.y = min(TERMINAL_VELOCITY, self.velocity.y + GRAVITY * dt)

    def _move(self, level: NeonLevel, dt: float) -> None:
        start = self.rect.copy()
        self.position.x += self.velocity.x * dt
        self.rect.topleft = (int(self.position.x), int(self.position.y))
        self._collide(level, axis=0)
        self.position.y += self.velocity.y * dt
        self.rect.topleft = (int(self.position.x), int(self.position.y))
        self._collide(level, axis=1)
        if self.phase_opacity < 255 and "phase" not in self.active_powerups:
            self.phase_opacity = min(255, self.phase_opacity + dt * 240)
        if self.position.distance_to(pygame.Vector2(start.center)) > 4:
            self.glow_trail.emit(pygame.Vector2(self.rect.center))

    def _collide(self, level: NeonLevel, axis: int) -> None:
        colliders = level.colliders_for_rect(self.rect)
        for rect in colliders:
            if not self.rect.colliderect(rect):
                continue
            if axis == 0:
                if self.velocity.x > 0:
                    self.rect.right = rect.left
                elif self.velocity.x < 0:
                    self.rect.left = rect.right
                self.velocity.x = 0
                self.position.x = self.rect.x
            else:
                if self.velocity.y > 0:
                    self.rect.bottom = rect.top
                    self.on_ground = True
                elif self.velocity.y < 0:
                    self.rect.top = rect.bottom
                self.velocity.y = 0
                self.position.y = self.rect.y
        if axis == 1 and not colliders:
            self.on_ground = False

    def _update_animation(self, dt: float) -> None:
        self.frame_time += dt
        if self.on_ground:
            if abs(self.velocity.x) > 30:
                if self.frame_time >= 0.08:
                    self.frame_index = (self.frame_index + 1) % len(self.sprite_frames)
                    self.frame_time = 0.0
            else:
                self.frame_index = 0
        else:
            self.frame_index = min(len(self.sprite_frames) - 1, self.frame_index)

    def draw(self, surface: pygame.Surface, camera: pygame.Rect) -> None:
        self.glow_trail.draw(surface, camera)
        sprite = self.sprite_frames[self.frame_index]
        sprite = sprite.copy()
        if self.phase_opacity < 255:
            sprite.set_alpha(self.phase_opacity)
        surface.blit(sprite, (self.rect.x - camera.x, self.rect.y - camera.y))

    def apply_powerup(self, key: str) -> None:
        definition = POWERUP_DEFINITIONS[key]
        self.active_powerups[key] = PowerUpState(key, remaining=float(definition["duration"]))
        if key == "double_jump":
            self.max_air_jumps = max(self.max_air_jumps, int(definition["max_air_jumps"]))
        elif key == "dash":
            self.dash_cooldown = 0.0
        elif key == "magnet":
            pass
        elif key == "phase":
            self.phase_opacity = int(definition["phase_opacity"])
            self.invulnerable_time = max(self.invulnerable_time, float(definition["duration"]))
        elif key == "slow":
            self.time_scale = min(self.time_scale, float(definition["time_scale"]))

    def _tick_powerups(self, dt: float) -> None:
        for key in list(self.active_powerups.keys()):
            state = self.active_powerups[key]
            state.remaining -= dt
            if state.remaining <= 0:
                self.active_powerups.pop(key)
                if key == "double_jump":
                    self.max_air_jumps = 0
                elif key == "slow":
                    self.time_scale = 1.0
                elif key == "phase":
                    self.phase_opacity = min(255, self.phase_opacity + 120)


@dataclass
class Collectible:
    position: pygame.Vector2
    value: int
    color: Tuple[int, int, int]
    radius: float = 6.0

    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.position.x - self.radius), int(self.position.y - self.radius), int(self.radius * 2), int(self.radius * 2))


@dataclass
class PowerUp:
    key: str
    position: pygame.Vector2
    color: Tuple[int, int, int]
    radius: float = 9.0

    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.position.x - self.radius), int(self.position.y - self.radius), int(self.radius * 2), int(self.radius * 2))


class NeonHUD:
    def __init__(self, font_large: pygame.font.Font, font_small: pygame.font.Font) -> None:
        self.font_large = font_large
        self.font_small = font_small

    def draw(self, surface: pygame.Surface, score: int, combo: float, powerups: Dict[str, PowerUpState]) -> None:
        hud_surface = pygame.Surface((surface.get_width(), 80), pygame.SRCALPHA)
        pygame.draw.rect(hud_surface, (15, 12, 45, 190), hud_surface.get_rect(), border_radius=12)
        score_text = self.font_large.render(f"Pontuação: {score}", True, (255, 238, 136))
        hud_surface.blit(score_text, (20, 20))
        combo_text = self.font_small.render(f"Combo x{combo:.1f}", True, (120, 255, 240))
        hud_surface.blit(combo_text, (20, 50))
        offset_x = surface.get_width() - 220
        for key, state in powerups.items():
            label = POWERUP_DEFINITIONS[key]["label"]
            color = POWERUP_DEFINITIONS[key]["color"]
            text = self.font_small.render(f"{label}: {state.remaining:04.1f}s", True, color)
            hud_surface.blit(text, (offset_x, 20))
            offset_x -= text.get_width() + 18
        surface.blit(hud_surface, (20, 20))


class NeonCamera:
    def __init__(self, width: int, height: int) -> None:
        self.rect = pygame.Rect(0, 0, width, height)

    def update(self, target: pygame.Rect, level: NeonLevel) -> None:
        self.rect.centerx = int(target.centerx)
        self.rect.centery = int(target.centery)
        max_x = level.width * TILE_SIZE - self.rect.width
        max_y = level.height * TILE_SIZE - self.rect.height
        self.rect.x = max(0, min(max_x, self.rect.x))
        self.rect.y = max(0, min(max_y, self.rect.y))


class NeonGame:
    def __init__(self) -> None:
        pygame.init()
        pygame.mixer.quit()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Neon Mask: Ascensão")
        self.clock = pygame.time.Clock()
        self.font_large = pygame.font.Font(None, 48)
        self.font_small = pygame.font.Font(None, 28)
        self.hud = NeonHUD(self.font_large, self.font_small)
        self.floating_texts = FloatingTextManager(self.font_small)
        self.scoreboard = Scoreboard(SCORE_FILE)
        self.score = 0
        self.combo = 1.0
        self.combo_timer = 0.0
        self.level = NeonLevel(180, 60)
        self.player = Player((TILE_SIZE * 3, TILE_SIZE * 4))
        self.camera = NeonCamera(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.collectibles: List[Collectible] = []
        self.powerups: List[PowerUp] = []
        self.particle_system = ParticleSystem()
        self.time_elapsed = 0.0
        self.game_over = False
        self.player_name = ""
        self._populate_level_objects()

    def _populate_level_objects(self) -> None:
        self.collectibles.clear()
        self.powerups.clear()
        rng = random.Random(self.level.seed)
        for spawn in self.level.iter_collectible_spawns():
            self.collectibles.append(
                Collectible(spawn.position + pygame.Vector2(0, -6), 50 * spawn.tier, color=(255, 214, 92))
            )
        spawn_keys = list(POWERUP_DEFINITIONS.keys())
        for spawn in self.level.iter_powerup_spawns():
            key = rng.choice(spawn_keys)
            color = POWERUP_DEFINITIONS[key]["color"]
            self.powerups.append(PowerUp(key, spawn.position + pygame.Vector2(0, -12), color))

    def run(self) -> None:
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit(0)
                if self.game_over and event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN and self.player_name:
                        self.scoreboard.record(self.player_name, int(self.score))
                        self.restart()
                    elif event.key == pygame.K_ESCAPE:
                        self.restart()
                    elif event.key == pygame.K_BACKSPACE:
                        self.player_name = self.player_name[:-1]
                    elif 32 <= event.key <= 126:
                        self.player_name += event.unicode
            keys = pygame.key.get_pressed()
            if not self.game_over:
                self._update(dt, keys)
            self._draw()

    def _update(self, dt: float, keys: Sequence[bool]) -> None:
        self.time_elapsed += dt
        inputs = (
            keys[pygame.K_LEFT] or keys[pygame.K_a],
            keys[pygame.K_RIGHT] or keys[pygame.K_d],
            keys[pygame.K_z] or keys[pygame.K_SPACE] or keys[pygame.K_w],
            keys[pygame.K_x] or keys[pygame.K_LSHIFT],
        )
        self.level.update(dt)
        self.player.update(dt, self.level, inputs)
        self.camera.update(self.player.rect, self.level)
        self._handle_collectibles(dt)
        self._handle_powerups(dt)
        self._check_hazards(dt)
        self.floating_texts.update(dt)
        self.particle_system.update(dt)
        if self.combo_timer > 0:
            self.combo_timer = max(0.0, self.combo_timer - dt)
        else:
            self.combo = max(1.0, self.combo * 0.96)

    def _handle_collectibles(self, dt: float) -> None:
        for collectible in list(self.collectibles):
            if collectible.rect().colliderect(self.player.rect):
                self.score += int(collectible.value * self.combo)
                self.combo = min(10.0, self.combo + 0.25)
                self.combo_timer = 3.0
                self.floating_texts.spawn(f"+{collectible.value}", collectible.position, collectible.color)
                self.particle_system.emit(collectible.position, collectible.color)
                self.collectibles.remove(collectible)
            elif "magnet" in self.player.active_powerups:
                radius = POWERUP_DEFINITIONS["magnet"]["magnet_radius"]
                if collectible.position.distance_to(self.player.position) < radius:
                    direction = (self.player.position - collectible.position).normalize()
                    collectible.position += direction * dt * 180

    def _handle_powerups(self, dt: float) -> None:
        for powerup in list(self.powerups):
            if powerup.rect().colliderect(self.player.rect):
                self.player.apply_powerup(powerup.key)
                self.floating_texts.spawn(POWERUP_DEFINITIONS[powerup.key]["label"], powerup.position, powerup.color)
                self.particle_system.emit(powerup.position, powerup.color)
                self.powerups.remove(powerup)

    def _check_hazards(self, dt: float) -> None:
        if self.player.invulnerable_time > 0:
            return
        player_rect = self.player.rect
        for hazard in self.level.iter_hazards():
            if hazard.rect.colliderect(player_rect):
                self._trigger_game_over()
                break

    def _trigger_game_over(self) -> None:
        self.game_over = True
        self.player_name = ""

    def restart(self) -> None:
        self.score = 0
        self.combo = 1.0
        self.combo_timer = 0.0
        self.level = NeonLevel(180, 60, seed=random.randint(0, 999_999))
        self.player = Player((TILE_SIZE * 3, TILE_SIZE * 4))
        self.camera = NeonCamera(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.particle_system = ParticleSystem()
        self.collectibles.clear()
        self.powerups.clear()
        self._populate_level_objects()
        self.game_over = False

    def _draw(self) -> None:
        self.screen.fill((0, 0, 0))
        self.level.draw(self.screen, self.camera.rect, self.time_elapsed)
        for collectible in self.collectibles:
            rect = collectible.rect()
            draw_pos = (rect.x - self.camera.rect.x, rect.y - self.camera.rect.y)
            pygame.draw.circle(self.screen, collectible.color, (draw_pos[0] + rect.width // 2, draw_pos[1] + rect.height // 2), int(collectible.radius))
        for powerup in self.powerups:
            rect = powerup.rect()
            draw_pos = (rect.x - self.camera.rect.x, rect.y - self.camera.rect.y)
            pygame.draw.rect(
                self.screen,
                powerup.color,
                pygame.Rect(draw_pos[0], draw_pos[1], rect.width, rect.height),
                border_radius=6,
            )
        self.player.draw(self.screen, self.camera.rect)
        self.particle_system.draw(self.screen, self.camera.rect)
        self.floating_texts.draw(self.screen, self.camera.rect)
        self.hud.draw(self.screen, int(self.score), self.combo, self.player.active_powerups)
        if self.game_over:
            self._draw_game_over()
        pygame.display.flip()

    def _draw_game_over(self) -> None:
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((14, 8, 32, 210))
        self.screen.blit(overlay, (0, 0))
        title = self.font_large.render("FIM DE CORRIDA", True, (255, 228, 150))
        prompt = self.font_small.render("Digite seu nome e pressione Enter", True, (200, 255, 240))
        scoreboard_title = self.font_small.render("Ranking Neon", True, (255, 218, 121))
        self.screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 200))
        self.screen.blit(prompt, (SCREEN_WIDTH // 2 - prompt.get_width() // 2, 250))
        name_surface = self.font_large.render(self.player_name or "_", True, (255, 255, 255))
        pygame.draw.rect(
            self.screen,
            (255, 230, 140),
            (
                SCREEN_WIDTH // 2 - 220,
                300,
                440,
                60,
            ),
            width=3,
            border_radius=10,
        )
        self.screen.blit(name_surface, (SCREEN_WIDTH // 2 - name_surface.get_width() // 2, 310))
        self.screen.blit(scoreboard_title, (SCREEN_WIDTH // 2 - scoreboard_title.get_width() // 2, 390))
        for index, entry in enumerate(self.scoreboard.entries):
            line = self.font_small.render(f"{index + 1:02d}º {entry.name} - {entry.score}", True, (255, 240, 190))
            self.screen.blit(line, (SCREEN_WIDTH // 2 - line.get_width() // 2, 420 + index * 28))


def main() -> None:
    game = NeonGame()
    game.run()


if __name__ == "__main__":
    main()
