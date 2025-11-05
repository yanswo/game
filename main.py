"""Run the enhanced procedural pixel art platformer with power-ups and ranking."""

from __future__ import annotations

import json
import math
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pygame

from level import TILE_SIZE, Level, create_default_level

SCREEN_WIDTH = 960
SCREEN_HEIGHT = 540
FPS = 60
GRAVITY = 1650
MOVE_SPEED = 250
MOVE_ACCEL = 1850
MOVE_DECEL = 2400
JUMP_SPEED = 540
TERMINAL_VELOCITY = 980
JUMP_BUFFER_TIME = 0.14
COYOTE_TIME = 0.12
SCORE_FILE = Path(__file__).with_name("scores.json")
SCOREBOARD_LIMIT = 7

POWERUP_DEFINITIONS: Dict[str, Dict[str, object]] = {
    "double_jump": {"label": "Salto Duplo", "duration": 10.0, "color": (255, 194, 107)},
    "speed_boost": {"label": "Turbo", "duration": 6.0, "color": (106, 235, 214)},
    "magnet": {"label": "Ímã", "duration": 7.5, "color": (197, 135, 255)},
    "shield": {"label": "Escudo", "duration": 12.0, "color": (138, 212, 255)},
}


@dataclass
class AnimationFrame:
    surface: pygame.Surface
    duration: float


class Player:
    """A controllable player character with fluid platformer physics."""

    def __init__(self, position: Tuple[float, float]) -> None:
        self.position = pygame.Vector2(position)
        self.velocity = pygame.Vector2(0, 0)
        self.on_ground = False
        self.facing_right = True
        self._build_sprites()
        self.animation_time = 0.0
        self.current_frame_index = 0
        self.jump_buffer = 0.0
        self.coyote_timer = 0.0
        self.jump_key_down = False
        self.max_air_jumps = 0
        self.air_jumps_used = 0
        self.speed_bonus = 0.0
        self.active_effects: Dict[str, float] = {}
        self.shield_charges = 0

    def _build_sprites(self) -> None:
        palette = {
            "skin": (239, 211, 150),
            "shirt": (74, 132, 252),
            "pants": (58, 58, 72),
            "boots": (36, 32, 48),
            "outline": (24, 28, 46),
            "accent": (255, 116, 104),
        }
        width, height = 18, 26
        idle = pygame.Surface((width, height), pygame.SRCALPHA)
        run1 = pygame.Surface((width, height), pygame.SRCALPHA)
        run2 = pygame.Surface((width, height), pygame.SRCALPHA)
        jump = pygame.Surface((width, height), pygame.SRCALPHA)

        def draw_base(surface: pygame.Surface) -> None:
            surface.fill((0, 0, 0, 0))
            pygame.draw.rect(surface, palette["outline"], (4, 5, 10, 20))
            pygame.draw.rect(surface, palette["shirt"], (5, 6, 8, 9))
            pygame.draw.rect(surface, palette["pants"], (5, 15, 8, 8))
            pygame.draw.rect(surface, palette["boots"], (5, 21, 4, 3))
            pygame.draw.rect(surface, palette["boots"], (9, 21, 4, 3))
            pygame.draw.rect(surface, palette["skin"], (7, 1, 4, 5))
            pygame.draw.rect(surface, palette["skin"], (5, 13, 3, 3))
            pygame.draw.rect(surface, palette["skin"], (10, 13, 3, 3))
            pygame.draw.rect(surface, palette["accent"], (11, 10, 2, 2))

        def draw_run(surface: pygame.Surface, left_offset: int, right_offset: int) -> None:
            draw_base(surface)
            pygame.draw.rect(surface, palette["pants"], (4 + left_offset, 20, 4, 4))
            pygame.draw.rect(surface, palette["pants"], (10 + right_offset, 18, 4, 4))

        def draw_jump(surface: pygame.Surface) -> None:
            draw_base(surface)
            pygame.draw.rect(surface, palette["pants"], (4, 18, 4, 4))
            pygame.draw.rect(surface, palette["pants"], (10, 20, 4, 4))

        draw_base(idle)
        draw_run(run1, -2, 2)
        draw_run(run2, 2, -2)
        draw_jump(jump)

        self.idle_frames = [AnimationFrame(idle, 0.55)]
        self.run_frames = [AnimationFrame(run1, 0.08), AnimationFrame(run2, 0.08)]
        self.jump_frame = AnimationFrame(jump, 0.1)

    def update(self, dt: float, level: Level, pressed: pygame.key.ScancodeWrapper) -> None:
        was_on_ground = self.on_ground
        self._update_effects(dt)
        self._handle_input(pressed, dt, was_on_ground)
        self._apply_gravity(dt)
        self._move_and_collide(dt, level)
        self._update_animation(dt)

    def _handle_input(
        self, pressed: pygame.key.ScancodeWrapper, dt: float, was_on_ground: bool
    ) -> None:
        move = 0
        if pressed[pygame.K_LEFT] or pressed[pygame.K_a]:
            move -= 1
        if pressed[pygame.K_RIGHT] or pressed[pygame.K_d]:
            move += 1

        if move != 0:
            self.facing_right = move > 0

        target_speed = MOVE_SPEED * self.speed_multiplier * move
        if move != 0:
            if self.velocity.x < target_speed:
                self.velocity.x = min(target_speed, self.velocity.x + MOVE_ACCEL * dt)
            elif self.velocity.x > target_speed:
                self.velocity.x = max(target_speed, self.velocity.x - MOVE_ACCEL * dt)
        else:
            slow = MOVE_DECEL * dt
            if abs(self.velocity.x) <= slow:
                self.velocity.x = 0
            else:
                self.velocity.x -= slow * math.copysign(1, self.velocity.x)

        jumping = pressed[pygame.K_SPACE] or pressed[pygame.K_UP] or pressed[pygame.K_w]
        if jumping:
            if not self.jump_key_down:
                self.jump_buffer = JUMP_BUFFER_TIME
            self.jump_key_down = True
        else:
            if self.jump_key_down and self.velocity.y < -JUMP_SPEED * 0.55:
                self.velocity.y = -JUMP_SPEED * 0.55
            self.jump_key_down = False

        self.jump_buffer = max(0.0, self.jump_buffer - dt)
        if was_on_ground:
            self.coyote_timer = COYOTE_TIME
        else:
            self.coyote_timer = max(0.0, self.coyote_timer - dt)

        can_jump = self.jump_buffer > 0 and (
            self.on_ground or self.coyote_timer > 0 or self.air_jumps_used < self.max_air_jumps
        )
        if can_jump:
            self._do_jump()
            self.jump_buffer = 0.0

    def _do_jump(self) -> None:
        if not self.on_ground:
            self.air_jumps_used += 1
        self.velocity.y = -JUMP_SPEED
        self.on_ground = False
        self.coyote_timer = 0.0

    def _apply_gravity(self, dt: float) -> None:
        self.velocity.y = min(self.velocity.y + GRAVITY * dt, TERMINAL_VELOCITY)

    def _move_and_collide(self, dt: float, level: Level) -> None:
        self.position.x += self.velocity.x * dt
        player_rect = self.rect
        colliders = [tile.rect for tile in level.tiles_in_region(player_rect)]
        for collider in colliders:
            if player_rect.colliderect(collider):
                if self.velocity.x > 0:
                    self.position.x = collider.left - player_rect.width
                elif self.velocity.x < 0:
                    self.position.x = collider.right
                player_rect = self.rect

        self.position.y += self.velocity.y * dt
        player_rect = self.rect
        colliders = [tile.rect for tile in level.tiles_in_region(player_rect)]
        was_grounded = self.on_ground
        self.on_ground = False
        for collider in colliders:
            if player_rect.colliderect(collider):
                if self.velocity.y > 0:
                    self.position.y = collider.top - player_rect.height
                    self.velocity.y = 0
                    self.on_ground = True
                    self.air_jumps_used = 0
                elif self.velocity.y < 0:
                    self.position.y = collider.bottom
                    self.velocity.y = 0
                player_rect = self.rect
        if was_grounded and not self.on_ground:
            self.coyote_timer = COYOTE_TIME

    def _update_animation(self, dt: float) -> None:
        frames = list(self._get_animation_frames())
        self.animation_time += dt
        if len(frames) == 1:
            self.current_frame_index = 0
            self.animation_time = 0
        else:
            frame_duration = frames[self.current_frame_index].duration
            if self.animation_time >= frame_duration:
                self.animation_time -= frame_duration
                self.current_frame_index = (self.current_frame_index + 1) % len(frames)

    def _get_animation_frames(self) -> Iterable[AnimationFrame]:
        if not self.on_ground:
            return [self.jump_frame]
        if abs(self.velocity.x) > 30:
            return self.run_frames
        return self.idle_frames

    def _update_effects(self, dt: float) -> None:
        expired = []
        for effect, remaining in list(self.active_effects.items()):
            remaining -= dt
            if remaining <= 0:
                expired.append(effect)
            else:
                self.active_effects[effect] = remaining
        for effect in expired:
            del self.active_effects[effect]
            if effect == "double_jump":
                self.max_air_jumps = 0
                self.air_jumps_used = 0
            elif effect == "speed_boost":
                self.speed_bonus = 0.0
            elif effect == "shield":
                self.shield_charges = 0

    def apply_powerup(self, power_type: str, duration: float) -> None:
        self.active_effects[power_type] = duration
        if power_type == "double_jump":
            self.max_air_jumps = 1
            self.air_jumps_used = 0
        elif power_type == "speed_boost":
            self.speed_bonus = 0.45
        elif power_type == "shield":
            self.shield_charges = 1
        elif power_type == "magnet":
            pass

    def consume_shield(self) -> bool:
        if self.shield_charges > 0:
            self.shield_charges = 0
            self.active_effects.pop("shield", None)
            return True
        return False

    def has_effect(self, effect: str) -> bool:
        return effect in self.active_effects

    @property
    def speed_multiplier(self) -> float:
        return 1.0 + self.speed_bonus

    @property
    def rect(self) -> pygame.Rect:
        surface = self.current_surface
        return surface.get_rect(topleft=(int(self.position.x), int(self.position.y)))

    @property
    def current_surface(self) -> pygame.Surface:
        frames = list(self._get_animation_frames())
        frame = frames[self.current_frame_index % len(frames)]
        return frame.surface

    def draw(self, surface: pygame.Surface, offset: pygame.Vector2) -> None:
        sprite = self.current_surface
        if not self.facing_right:
            sprite = pygame.transform.flip(sprite, True, False)
        position = self.position - offset
        surface.blit(sprite, position)
        if self.shield_charges > 0 or self.has_effect("shield"):
            radius = max(sprite.get_width(), sprite.get_height())
            overlay = pygame.Surface((radius + 12, radius + 12), pygame.SRCALPHA)
            pygame.draw.circle(
                overlay,
                (140, 220, 255, 90),
                overlay.get_rect().center,
                max(10, (radius + 6) // 2),
                3,
            )
            offset_pos = position - pygame.Vector2(
                (overlay.get_width() - sprite.get_width()) / 2,
                (overlay.get_height() - sprite.get_height()) / 2,
            )
            surface.blit(overlay, offset_pos)


@dataclass
class Collectible:
    base_position: pygame.Vector2
    frames: List[pygame.Surface]
    phase: float
    value: int = 120
    position: pygame.Vector2 = field(init=False)

    def __post_init__(self) -> None:
        self.position = self.base_position.copy()

    def update(self, dt: float, player: Player) -> None:
        self.phase += dt * 4.5
        self.position.y = self.base_position.y + math.sin(self.phase) * 6
        if player.has_effect("magnet"):
            player_center = pygame.Vector2(player.rect.center)
            diff = player_center - self.position
            distance = diff.length()
            if 0 < distance < 240:
                pull = max(140, 320 - distance)
                self.position += diff.normalize() * pull * dt

    def sprite(self) -> pygame.Surface:
        index = int(self.phase * 5) % len(self.frames)
        return self.frames[index]

    def collides_with(self, rect: pygame.Rect) -> bool:
        radius = self.frames[0].get_width() * 0.35
        closest_x = max(rect.left, min(self.position.x, rect.right))
        closest_y = max(rect.top, min(self.position.y, rect.bottom))
        diff_x = self.position.x - closest_x
        diff_y = self.position.y - closest_y
        return diff_x * diff_x + diff_y * diff_y <= radius * radius


@dataclass
class PowerUpItem:
    power_type: str
    position: pygame.Vector2
    sprite: pygame.Surface
    rotation: float = 0.0

    def update(self, dt: float) -> None:
        self.rotation = (self.rotation + dt * 120) % 360

    def draw(self, surface: pygame.Surface, offset: pygame.Vector2) -> None:
        rotated = pygame.transform.rotozoom(self.sprite, self.rotation, 1.0)
        rect = rotated.get_rect(center=self.position - offset)
        surface.blit(rotated, rect)

    def collides_with(self, rect: pygame.Rect) -> bool:
        hitbox = pygame.Rect(0, 0, self.sprite.get_width(), self.sprite.get_height())
        hitbox.center = self.position
        return rect.colliderect(hitbox)


@dataclass
class FloatingText:
    text: str
    position: pygame.Vector2
    color: Tuple[int, int, int]
    lifetime: float = 1.2
    elapsed: float = 0.0

    def update(self, dt: float) -> None:
        self.elapsed += dt
        self.position.y -= 28 * dt

    def alpha(self) -> int:
        return max(0, min(255, int(255 * (1 - self.elapsed / self.lifetime))))


@dataclass(order=True)
class ScoreEntry:
    score: int
    name: str = field(compare=False)
    distance: float = field(compare=False)
    crystals: int = field(compare=False)
    duration: float = field(compare=False)
    result: str = field(compare=False)

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "score": self.score,
            "distance": self.distance,
            "crystals": self.crystals,
            "duration": self.duration,
            "result": self.result,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "ScoreEntry":
        return cls(
            score=int(data.get("score", 0)),
            name=str(data.get("name", "Jogador")),
            distance=float(data.get("distance", 0.0)),
            crystals=int(data.get("crystals", 0)),
            duration=float(data.get("duration", 0.0)),
            result=str(data.get("result", "")),
        )


class ScoreManager:
    def __init__(self, path: Path, limit: int = SCOREBOARD_LIMIT) -> None:
        self.path = path
        self.limit = limit
        self.entries: List[ScoreEntry] = []
        self.load()

    def load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.entries = [ScoreEntry.from_dict(item) for item in data]
            except (json.JSONDecodeError, OSError):
                self.entries = []
        else:
            self.path.write_text("[]", encoding="utf-8")

    def save(self) -> None:
        try:
            data = [entry.to_dict() for entry in self.entries[: self.limit]]
            self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def add_entry(self, entry: ScoreEntry) -> None:
        self.entries.append(entry)
        self.entries.sort(reverse=True)
        self.entries = self.entries[: self.limit]
        self.save()

    def top_entries(self) -> List[ScoreEntry]:
        return list(self.entries)


@dataclass
class GameSession:
    level: Level
    player: Player
    collectibles: List[Collectible]
    powerups: List[PowerUpItem]
    floating_texts: List[FloatingText]
    rng: random.Random
    base_score: int = 0
    crystals: int = 0
    max_distance: float = 0.0
    elapsed: float = 0.0
    result: str = ""

    def final_score(self) -> int:
        distance_bonus = int(self.max_distance / TILE_SIZE) * 10
        time_bonus = int(self.elapsed * 3)
        return self.base_score + distance_bonus + time_bonus


class GameState:
    def __init__(self, score_manager: ScoreManager) -> None:
        self.mode = "title"
        self.session: GameSession | None = None
        self.score_manager = score_manager
        self.pending_entry: ScoreEntry | None = None
        self.awaiting_name = False
        self.name_input = ""

    def start_new_session(self) -> None:
        level = create_default_level()
        spawn_y = level.pixel_height - (level.base_ground_height + 6) * TILE_SIZE
        player = Player((80, max(64, spawn_y)))
        rng = random.Random()
        collectible_frames = build_collectible_frames()
        collectibles = [
            Collectible(spawn.to_vector(), collectible_frames, rng.random() * math.tau)
            for spawn in level.collectible_spawns
        ]
        powerup_types = list(POWERUP_DEFINITIONS.keys())
        powerups: List[PowerUpItem] = []
        for spawn in level.powerup_spawns:
            power_type = rng.choice(powerup_types)
            sprite = build_powerup_sprite(tuple(POWERUP_DEFINITIONS[power_type]["color"]))
            powerups.append(PowerUpItem(power_type, spawn.to_vector(), sprite))
        self.session = GameSession(level, player, collectibles, powerups, [], rng)
        self.mode = "running"
        self.pending_entry = None
        self.awaiting_name = False
        self.name_input = ""

    def finish_session(self, result: str) -> None:
        if not self.session:
            return
        self.session.result = result
        entry = ScoreEntry(
            score=self.session.final_score(),
            name="Jogador",
            distance=self.session.max_distance / TILE_SIZE,
            crystals=self.session.crystals,
            duration=self.session.elapsed,
            result=result,
        )
        self.pending_entry = entry
        self.awaiting_name = True
        self.mode = "game_over"

    def finalize_score(self) -> None:
        if not self.pending_entry:
            return
        name = self.name_input.strip() or "Jogador"
        finalized = ScoreEntry(
            score=self.pending_entry.score,
            name=name[:16],
            distance=self.pending_entry.distance,
            crystals=self.pending_entry.crystals,
            duration=self.pending_entry.duration,
            result=self.pending_entry.result,
        )
        self.score_manager.add_entry(finalized)
        self.pending_entry = finalized
        self.awaiting_name = False
        self.name_input = ""


def create_tile_surface(color_top: Tuple[int, int, int], color_bottom: Tuple[int, int, int]) -> pygame.Surface:
    tile = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
    for y in range(TILE_SIZE):
        t = y / TILE_SIZE
        color = [int(color_top[i] * (1 - t) + color_bottom[i] * t) for i in range(3)]
        pygame.draw.line(tile, color, (0, y), (TILE_SIZE, y))
    return tile


def build_ground_tile() -> pygame.Surface:
    tile = create_tile_surface((108, 82, 60), (58, 38, 26))
    pygame.draw.rect(tile, (36, 24, 19), (0, TILE_SIZE - 3, TILE_SIZE, 3))
    for x in range(0, TILE_SIZE, 4):
        pygame.draw.line(tile, (78, 56, 44), (x, TILE_SIZE - 6), (x + 1, TILE_SIZE - 2))
    return tile


def build_ground_top() -> pygame.Surface:
    tile = build_ground_tile().copy()
    pygame.draw.rect(tile, (74, 156, 88), (0, 0, TILE_SIZE, 6))
    pygame.draw.line(tile, (192, 232, 146), (0, 1), (TILE_SIZE, 1))
    for x in range(0, TILE_SIZE, 4):
        pygame.draw.line(tile, (62, 132, 72), (x, 4), (x + 1, 6))
    return tile


def build_platform_tile() -> pygame.Surface:
    tile = create_tile_surface((122, 142, 170), (72, 88, 122))
    pygame.draw.rect(tile, (52, 64, 92), (0, TILE_SIZE - 3, TILE_SIZE, 3))
    return tile


def build_platform_top() -> pygame.Surface:
    tile = build_platform_tile().copy()
    pygame.draw.rect(tile, (196, 212, 238), (0, 0, TILE_SIZE, 4))
    pygame.draw.line(tile, (255, 255, 255), (0, 1), (TILE_SIZE, 1))
    return tile


def build_spike_surface(width: int, height: int) -> pygame.Surface:
    surface = pygame.Surface((width, height), pygame.SRCALPHA)
    points = [
        (0, height),
        (width * 0.25, 0),
        (width * 0.5, height),
        (width * 0.75, 0),
        (width, height),
    ]
    pygame.draw.polygon(surface, (225, 86, 98), points)
    pygame.draw.lines(surface, (34, 18, 24), True, points, 2)
    return surface


def build_collectible_frames() -> List[pygame.Surface]:
    frames: List[pygame.Surface] = []
    for i in range(6):
        surface = pygame.Surface((18, 18), pygame.SRCALPHA)
        angle = i / 6 * math.tau
        radius = 7
        points = [
            (9 + math.cos(angle + math.tau * k / 4) * radius, 9 + math.sin(angle + math.tau * k / 4) * radius)
            for k in range(4)
        ]
        pygame.draw.polygon(surface, (255, 204, 94), points)
        pygame.draw.polygon(surface, (255, 246, 198), points, 2)
        frames.append(surface)
    return frames


def build_powerup_sprite(color: Tuple[int, int, int]) -> pygame.Surface:
    surface = pygame.Surface((24, 24), pygame.SRCALPHA)
    pygame.draw.circle(surface, color, (12, 12), 10)
    pygame.draw.circle(surface, (255, 255, 255), (12, 12), 6, 2)
    return surface


def build_goal_surface(width: int, height: int) -> pygame.Surface:
    surface = pygame.Surface((width, height), pygame.SRCALPHA)
    pole_rect = pygame.Rect(width // 2 - 3, height - 6 * TILE_SIZE, 6, 6 * TILE_SIZE)
    pygame.draw.rect(surface, (102, 82, 62), pole_rect)
    flag = [
        (pole_rect.right, pole_rect.top + TILE_SIZE),
        (pole_rect.right + TILE_SIZE * 1.5, pole_rect.top + TILE_SIZE * 1.5),
        (pole_rect.right, pole_rect.top + TILE_SIZE * 2),
    ]
    pygame.draw.polygon(surface, (255, 128, 110), flag)
    pygame.draw.polygon(surface, (255, 242, 230), flag, 2)
    return surface


def build_tile_palette() -> Dict[str, pygame.Surface]:
    return {
        "ground": build_ground_tile(),
        "ground_top": build_ground_top(),
        "platform": build_platform_tile(),
        "platform_top": build_platform_top(),
    }


def draw_tiles(
    surface: pygame.Surface,
    level: Level,
    camera_offset: pygame.Vector2,
    tile_palette: Dict[str, pygame.Surface],
) -> None:
    camera_rect = pygame.Rect(
        int(camera_offset.x),
        int(camera_offset.y),
        SCREEN_WIDTH,
        SCREEN_HEIGHT,
    )
    for tile in level.tiles_in_region(camera_rect.inflate(128, 128)):
        position = (tile.x * TILE_SIZE - camera_offset.x, tile.y * TILE_SIZE - camera_offset.y)
        if level.is_ground_surface(tile):
            base = tile_palette["ground"]
            top = tile_palette["ground_top"] if level.is_surface_tile(tile) else None
        else:
            base = tile_palette["platform"]
            top = tile_palette["platform_top"] if level.is_surface_tile(tile) else None
        surface.blit(base, position)
        if top is not None:
            surface.blit(top, position)


def draw_hazards(surface: pygame.Surface, level: Level, camera_offset: pygame.Vector2, spike_surface: pygame.Surface) -> None:
    for hazard in level.hazards:
        position = pygame.Vector2(hazard.x, hazard.y) - camera_offset
        scaled = pygame.transform.smoothscale(spike_surface, (hazard.width, hazard.height))
        surface.blit(scaled, position)


def draw_collectibles(surface: pygame.Surface, collectibles: Iterable[Collectible], camera_offset: pygame.Vector2) -> None:
    for collectible in collectibles:
        sprite = collectible.sprite()
        rect = sprite.get_rect(center=collectible.position - camera_offset)
        surface.blit(sprite, rect)


def draw_powerups(surface: pygame.Surface, powerups: Iterable[PowerUpItem], camera_offset: pygame.Vector2) -> None:
    for powerup in powerups:
        powerup.draw(surface, camera_offset)


def draw_goal(surface: pygame.Surface, level: Level, camera_offset: pygame.Vector2, goal_surface: pygame.Surface) -> None:
    rect = level.goal_rect.move(-camera_offset.x, -camera_offset.y)
    scaled = pygame.transform.smoothscale(goal_surface, rect.size)
    surface.blit(scaled, rect)


def draw_floating_texts(
    surface: pygame.Surface, texts: Iterable[FloatingText], camera_offset: pygame.Vector2, font: pygame.font.Font
) -> None:
    for text in texts:
        rendered = font.render(text.text, True, text.color)
        rendered.set_alpha(text.alpha())
        surface.blit(rendered, text.position - camera_offset)


def draw_hud(
    surface: pygame.Surface,
    session: GameSession,
    font: pygame.font.Font,
    small_font: pygame.font.Font,
) -> None:
    score_text = font.render(f"Pontuação: {session.final_score():04d}", True, (255, 255, 255))
    crystals_text = small_font.render(f"Cristais: {session.crystals}", True, (230, 220, 250))
    distance_text = small_font.render(f"Distância: {int(session.max_distance / TILE_SIZE)}m", True, (230, 220, 250))
    surface.blit(score_text, (20, 16))
    surface.blit(crystals_text, (24, 56))
    surface.blit(distance_text, (24, 80))

    x = 24
    y = 110
    for effect, remaining in session.player.active_effects.items():
        definition = POWERUP_DEFINITIONS.get(effect)
        if not definition:
            continue
        label = f"{definition['label']}: {remaining:0.1f}s"
        color = tuple(definition["color"])
        text_surface = small_font.render(label, True, color)
        surface.blit(text_surface, (x, y))
        y += 22


def draw_rankings(surface: pygame.Surface, font: pygame.font.Font, scores: List[ScoreEntry], start_y: int = 120) -> None:
    header = font.render("Ranking", True, (255, 255, 255))
    surface.blit(header, (SCREEN_WIDTH / 2 - header.get_width() / 2, start_y))
    for index, entry in enumerate(scores, start=1):
        line = f"{index:02d}. {entry.name:<12} {entry.score:05d} pts  {entry.distance:.0f}m  {entry.crystals}x"
        text_surface = font.render(line, True, (220, 220, 240))
        surface.blit(text_surface, (SCREEN_WIDTH / 2 - text_surface.get_width() / 2, start_y + 30 + index * 24))


def draw_title_screen(surface: pygame.Surface, font: pygame.font.Font, small_font: pygame.font.Font, scores: List[ScoreEntry]) -> None:
    title = font.render("Corrida Procedural", True, (255, 239, 200))
    subtitle = small_font.render("Pressione Enter para começar", True, (230, 220, 255))
    surface.blit(title, (SCREEN_WIDTH / 2 - title.get_width() / 2, 140))
    surface.blit(subtitle, (SCREEN_WIDTH / 2 - subtitle.get_width() / 2, 190))
    draw_rankings(surface, small_font, scores, start_y=240)


def draw_game_over(
    surface: pygame.Surface,
    state: GameState,
    font: pygame.font.Font,
    small_font: pygame.font.Font,
) -> None:
    if not state.session or not state.pending_entry:
        return
    overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    overlay.fill((18, 22, 38, 210))
    surface.blit(overlay, (0, 0))
    title = font.render("Fim da Corrida", True, (255, 239, 200))
    surface.blit(title, (SCREEN_WIDTH / 2 - title.get_width() / 2, 120))

    entry = state.pending_entry
    stats = [
        f"Resultado: {state.session.result}",
        f"Pontuação: {entry.score}",
        f"Distância: {entry.distance:.0f} m",
        f"Cristais: {entry.crystals}",
        f"Tempo: {entry.duration:0.1f}s",
    ]
    for i, text in enumerate(stats):
        surface.blit(small_font.render(text, True, (235, 230, 255)), (SCREEN_WIDTH / 2 - 140, 180 + i * 26))

    if state.awaiting_name:
        prompt = small_font.render("Digite seu nome e pressione Enter", True, (255, 240, 180))
        surface.blit(prompt, (SCREEN_WIDTH / 2 - prompt.get_width() / 2, 320))
        name_box = pygame.Surface((360, 40))
        name_box.fill((34, 40, 68))
        pygame.draw.rect(name_box, (150, 180, 255), name_box.get_rect(), 2)
        name_text = font.render(state.name_input or "Jogador", True, (255, 255, 255))
        name_box.blit(name_text, (16, 6))
        surface.blit(name_box, (SCREEN_WIDTH / 2 - name_box.get_width() / 2, 360))
    else:
        surface.blit(
            small_font.render("Pressione R para tentar novamente", True, (220, 215, 255)),
            (SCREEN_WIDTH / 2 - 170, 330),
        )

    draw_rankings(surface, small_font, state.score_manager.top_entries(), start_y=400)


def update_session(session: GameSession, dt: float, pressed: pygame.key.ScancodeWrapper) -> str | None:
    player = session.player
    player.update(dt, session.level, pressed)
    session.elapsed += dt
    session.max_distance = max(session.max_distance, player.position.x)

    player_rect = player.rect

    collected: List[Collectible] = []
    for collectible in session.collectibles:
        collectible.update(dt, player)
        if collectible.collides_with(player_rect):
            collected.append(collectible)
    for item in collected:
        session.collectibles.remove(item)
        session.base_score += item.value
        session.crystals += 1
        session.floating_texts.append(
            FloatingText(f"+{item.value}", pygame.Vector2(item.position.x, item.position.y - 12), (255, 226, 146))
        )

    grabbed: List[PowerUpItem] = []
    for powerup in session.powerups:
        powerup.update(dt)
        if powerup.collides_with(player_rect):
            grabbed.append(powerup)
    for item in grabbed:
        definition = POWERUP_DEFINITIONS[item.power_type]
        player.apply_powerup(item.power_type, float(definition["duration"]))
        session.floating_texts.append(
            FloatingText(str(definition["label"]), item.position.copy(), tuple(definition["color"]))
        )
        session.powerups.remove(item)

    for text in list(session.floating_texts):
        text.update(dt)
        if text.elapsed >= text.lifetime:
            session.floating_texts.remove(text)

    expanded_rect = player_rect.inflate(-6, -4)
    for hazard in session.level.hazards:
        if hazard.rect.colliderect(expanded_rect):
            if player.consume_shield():
                session.floating_texts.append(
                    FloatingText("Escudo!", pygame.Vector2(player_rect.center), (140, 220, 255))
                )
            else:
                session.result = "Atingido pelos espinhos"
                return "fail"

    if player.position.y > session.level.pixel_height + 100:
        session.result = "Caiu no abismo"
        return "fail"

    if player.rect.colliderect(session.level.goal_rect):
        session.result = "Chegou ao portal"
        return "success"

    return None


def run() -> None:
    pygame.init()
    pygame.display.set_caption("Procedural Pixel Platformer")
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    clock = pygame.time.Clock()

    background = ParallaxBackground((SCREEN_WIDTH, SCREEN_HEIGHT))
    tile_palette = build_tile_palette()
    spike_surface = build_spike_surface(TILE_SIZE, TILE_SIZE // 2)
    goal_surface = build_goal_surface(TILE_SIZE * 3, TILE_SIZE * 6)
    large_font = pygame.font.Font(None, 52)
    medium_font = pygame.font.Font(None, 32)

    score_manager = ScoreManager(SCORE_FILE)
    state = GameState(score_manager)

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0
        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif state.mode == "title" and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    state.start_new_session()
                elif state.mode == "game_over":
                    if state.awaiting_name:
                        if event.key == pygame.K_RETURN:
                            state.finalize_score()
                        elif event.key == pygame.K_BACKSPACE:
                            state.name_input = state.name_input[:-1]
                        elif event.unicode and event.unicode.isprintable():
                            state.name_input += event.unicode
                    else:
                        if event.key in (pygame.K_r, pygame.K_SPACE, pygame.K_RETURN):
                            state.mode = "title"
                            state.session = None
                elif state.mode == "running" and event.key == pygame.K_r:
                    state.mode = "title"
                    state.session = None

        screen.fill((18, 20, 32))

        if state.mode == "title":
            background.draw(screen, 0)
            draw_title_screen(screen, large_font, medium_font, score_manager.top_entries())
        elif state.mode == "running" and state.session:
            session = state.session
            pressed = pygame.key.get_pressed()
            outcome = update_session(session, dt, pressed)
            camera_x = max(0, min(session.level.pixel_width - SCREEN_WIDTH, session.player.position.x - SCREEN_WIDTH / 2))
            camera_y = max(0, min(session.level.pixel_height - SCREEN_HEIGHT, session.player.position.y - SCREEN_HEIGHT / 2))
            camera_offset = pygame.Vector2(camera_x, camera_y)

            background.draw(screen, camera_x)
            draw_tiles(screen, session.level, camera_offset, tile_palette)
            draw_hazards(screen, session.level, camera_offset, spike_surface)
            draw_goal(screen, session.level, camera_offset, goal_surface)
            draw_collectibles(screen, session.collectibles, camera_offset)
            draw_powerups(screen, session.powerups, camera_offset)
            session.player.draw(screen, camera_offset)
            draw_floating_texts(screen, session.floating_texts, camera_offset, medium_font)
            draw_hud(screen, session, large_font, medium_font)

            if outcome:
                result_text = session.result or ("Vitória" if outcome == "success" else "")
                state.finish_session(result_text)
        elif state.mode == "game_over":
            if state.session:
                session = state.session
                camera_x = max(0, min(session.level.pixel_width - SCREEN_WIDTH, session.player.position.x - SCREEN_WIDTH / 2))
                camera_y = max(0, min(session.level.pixel_height - SCREEN_HEIGHT, session.player.position.y - SCREEN_HEIGHT / 2))
                camera_offset = pygame.Vector2(camera_x, camera_y)
                background.draw(screen, camera_x)
                draw_tiles(screen, session.level, camera_offset, tile_palette)
                draw_goal(screen, session.level, camera_offset, goal_surface)
                draw_collectibles(screen, session.collectibles, camera_offset)
                draw_powerups(screen, session.powerups, camera_offset)
                session.player.draw(screen, camera_offset)
            draw_game_over(screen, state, large_font, medium_font)

        pygame.display.flip()

    pygame.quit()


class ParallaxBackground:
    """A layered parallax background made from pixel art gradients."""

    def __init__(self, screen_size: Tuple[int, int]) -> None:
        self.screen_width, self.screen_height = screen_size
        self.layers = [self._create_layer(i) for i in range(4)]

    def _create_layer(self, index: int) -> pygame.Surface:
        layer = pygame.Surface((self.screen_width, self.screen_height))
        palettes = [
            [(16, 18, 28), (28, 30, 48)],
            [(22, 32, 52), (48, 64, 102)],
            [(30, 52, 90), (80, 120, 162)],
            [(56, 86, 132), (142, 188, 226)],
        ]
        colors = palettes[min(index, len(palettes) - 1)]
        for y in range(self.screen_height):
            t = y / self.screen_height
            color = [int(colors[0][i] * (1 - t) + colors[1][i] * t) for i in range(3)]
            pygame.draw.line(layer, color, (0, y), (self.screen_width, y))
        if index == 0:
            for n in range(180):
                x = int((n * 127) % self.screen_width)
                y = int((n * 53) % (self.screen_height // 2))
                layer.fill((255, 255, 255), ((x, y), (1, 1)))
        elif index == 1:
            for n in range(40):
                base_x = (n * 87) % self.screen_width
                base_y = self.screen_height // 2 + n % 40
                width = 120 + (n % 5) * 40
                points = [
                    (base_x, base_y + 50),
                    (base_x + width // 2, base_y - 30),
                    (base_x + width, base_y + 50),
                ]
                pygame.draw.polygon(layer, (28, 36, 58), points)
        return layer

    def draw(self, surface: pygame.Surface, camera_x: float) -> None:
        parallax_strengths = [0.15, 0.25, 0.45, 0.75]
        for layer, strength in zip(self.layers, parallax_strengths):
            offset_x = int(camera_x * strength) % self.screen_width
            surface.blit(layer, (-offset_x, 0))
            if offset_x > 0:
                surface.blit(layer, (self.screen_width - offset_x, 0))


if __name__ == "__main__":
    try:
        run()
    except pygame.error as exc:  # pragma: no cover - surfaces errors in headless environments
        sys.stderr.write(f"Failed to initialize the game window: {exc}\n")
