"""Tomb of the Mask inspired neon terrain and prop generation."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Iterable, Iterator, List, Sequence, Tuple

import pygame

from assets.neon_tiles import NEON_TILE_LIBRARY

TILE_SIZE = 16
GRID_STEP = TILE_SIZE


@dataclass(frozen=True)
class NeonPalette:
    """Palette describing neon tones used to paint the labyrinth."""

    name: str
    colors: Tuple[Tuple[int, int, int, int], ...]
    sky: Tuple[int, int, int]
    glow: Tuple[int, int, int]
    sparkle: Tuple[int, int, int]

    def color(self, index: int) -> Tuple[int, int, int, int]:
        return self.colors[index]


NEON_PALETTES: Tuple[NeonPalette, ...] = (
    NeonPalette(
        "aurora",
        (
            (0, 0, 0, 0),
            (9, 12, 36, 180),
            (232, 228, 88, 255),
            (255, 186, 41, 255),
            (255, 255, 184, 255),
            (76, 255, 215, 200),
            (122, 64, 255, 180),
            (17, 255, 236, 255),
        ),
        (14, 9, 38),
        (255, 227, 98),
        (94, 255, 214),
    ),
    NeonPalette(
        "subterraneo",
        (
            (0, 0, 0, 0),
            (11, 15, 44, 180),
            (255, 92, 147, 255),
            (255, 63, 90, 255),
            (255, 156, 199, 255),
            (114, 231, 250, 220),
            (60, 189, 249, 200),
            (246, 255, 173, 255),
        ),
        (16, 12, 53),
        (255, 92, 147),
        (252, 252, 198),
    ),
    NeonPalette(
        "oceano",
        (
            (0, 0, 0, 0),
            (7, 13, 40, 180),
            (121, 238, 255, 255),
            (83, 182, 255, 255),
            (215, 255, 255, 255),
            (255, 177, 54, 220),
            (255, 116, 109, 210),
            (0, 255, 191, 255),
        ),
        (8, 11, 32),
        (121, 238, 255),
        (255, 203, 118),
    ),
    NeonPalette(
        "cosmico",
        (
            (0, 0, 0, 0),
            (9, 10, 33, 190),
            (205, 118, 255, 255),
            (167, 83, 255, 255),
            (240, 222, 255, 255),
            (104, 209, 255, 220),
            (255, 108, 108, 210),
            (255, 255, 255, 255),
        ),
        (12, 10, 38),
        (205, 118, 255),
        (255, 255, 255),
    ),
    NeonPalette(
        "jungla",
        (
            (0, 0, 0, 0),
            (6, 15, 28, 180),
            (157, 255, 101, 255),
            (92, 206, 59, 255),
            (227, 255, 177, 255),
            (94, 245, 255, 220),
            (255, 148, 63, 210),
            (255, 255, 255, 255),
        ),
        (10, 18, 22),
        (157, 255, 101),
        (255, 211, 131),
    ),
)


@dataclass(frozen=True)
class TileKey:
    x: int
    y: int

    def rect(self) -> pygame.Rect:
        return pygame.Rect(self.x * TILE_SIZE, self.y * TILE_SIZE, TILE_SIZE, TILE_SIZE)


@dataclass
class TileDescriptor:
    key: TileKey
    mask: int
    variant: int


@dataclass(frozen=True)
class Hazard:
    rect: pygame.Rect
    damage: int
    color: Tuple[int, int, int]
    period: float
    phase: float


@dataclass(frozen=True)
class SparkleEmitter:
    origin: pygame.Vector2
    radius: float
    color: Tuple[int, int, int]
    intensity: float


@dataclass(frozen=True)
class SpawnPoint:
    position: pygame.Vector2
    tier: int


@dataclass
class AmbientStripe:
    rect: pygame.Rect
    speed: float
    opacity: float
    color: Tuple[int, int, int]

    def update(self, dt: float, level_width_px: int) -> None:
        self.rect.x -= int(self.speed * dt)
        if self.rect.right < 0:
            self.rect.x = level_width_px


class NeonTileAtlas:
    """Lazy surface builder for Tomb of the Mask inspired tiles."""

    def __init__(self, palette: NeonPalette) -> None:
        self.palette = palette
        self._cache: Dict[Tuple[int, int], pygame.Surface] = {}

    def surface(self, mask: int, variant: int) -> pygame.Surface:
        key = (mask, variant % 64)
        if key not in self._cache:
            mask_key = f"{mask:04b}"
            pattern = NEON_TILE_LIBRARY[(mask_key, key[1])]
            surf = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
            surf.lock()
            for y, row in enumerate(pattern):
                for x, char in enumerate(row):
                    color = self.palette.color(int(char))
                    if color[3] == 0:
                        continue
                    surf.set_at((x, y), color)
            surf.unlock()
            self._cache[key] = surf
        return self._cache[key]


class NeonBackground:
    """Animated gradient strips and glows behind the level."""

    def __init__(self, palette: NeonPalette, width_px: int, height_px: int, rng: random.Random) -> None:
        self.palette = palette
        self.width_px = width_px
        self.height_px = height_px
        self.gradient = self._build_gradient_surface()
        self.stripes: List[AmbientStripe] = []
        stripe_count = max(12, width_px // 64)
        for i in range(stripe_count):
            w = rng.randint(48, 140)
            h = rng.randint(4, 12)
            x = rng.randint(0, width_px)
            y = rng.randint(0, height_px)
            speed = rng.uniform(10.0, 45.0)
            opacity = rng.uniform(0.1, 0.45)
            color = tuple(min(255, int(c * rng.uniform(0.7, 1.15))) for c in self.palette.glow)
            self.stripes.append(AmbientStripe(pygame.Rect(x, y, w, h), speed, opacity, color))
        self.time = 0.0

    def _build_gradient_surface(self) -> pygame.Surface:
        surf = pygame.Surface((self.width_px, self.height_px))
        top_color = pygame.Color(*self.palette.sky)
        bottom_color = pygame.Color(
            min(255, int(self.palette.sky[0] * 0.45)),
            min(255, int(self.palette.sky[1] * 0.45)),
            min(255, int(self.palette.sky[2] * 0.55)),
        )
        for y in range(self.height_px):
            blend = y / max(1, self.height_px - 1)
            color = top_color.lerp(bottom_color, blend)
            pygame.draw.line(surf, color, (0, y), (self.width_px, y))
        return surf.convert()

    def update(self, dt: float) -> None:
        self.time += dt
        for stripe in self.stripes:
            stripe.update(dt, self.width_px)

    def draw(self, target: pygame.Surface, camera_rect: pygame.Rect) -> None:
        target.blit(self.gradient, (0, 0), camera_rect)
        overlay = pygame.Surface(camera_rect.size, pygame.SRCALPHA)
        for stripe in self.stripes:
            rect = stripe.rect.copy()
            rect.x -= camera_rect.x
            rect.y -= camera_rect.y
            pygame.draw.rect(overlay, (*stripe.color, int(255 * stripe.opacity)), rect)
        pulse = (math.sin(self.time * 0.7) + 1) * 0.5
        aura_color = pygame.Color(*self.palette.glow)
        aura_color.a = int(60 + 30 * pulse)
        pygame.draw.rect(overlay, aura_color, overlay.get_rect(), border_radius=12)
        target.blit(overlay, (0, 0))


class NeonParticleField:
    """Generates trailing neon sparks around collectibles and vents."""

    def __init__(self, palette: NeonPalette, rng: random.Random) -> None:
        self.palette = palette
        self.rng = rng
        self.emitters: List[SparkleEmitter] = []

    def seed_emitters(self, centers: Iterable[Tuple[float, float]]) -> None:
        for x, y in centers:
            self.emitters.append(
                SparkleEmitter(
                    pygame.Vector2(x, y),
                    self.rng.uniform(22.0, 48.0),
                    tuple(min(255, int(c * self.rng.uniform(0.8, 1.3))) for c in self.palette.sparkle),
                    self.rng.uniform(0.35, 0.75),
                )
            )

    def draw(self, surface: pygame.Surface, camera: pygame.Rect, time: float) -> None:
        for emitter in self.emitters:
            center = emitter.origin - pygame.Vector2(camera.x, camera.y)
            flicker = (math.sin(time * emitter.intensity) + 1) * 0.5
            radius = emitter.radius * (0.8 + 0.2 * flicker)
            gradient = pygame.Surface((int(radius * 2), int(radius * 2)), pygame.SRCALPHA)
            for r in range(int(radius), 0, -1):
                alpha = max(0, int(180 * (1 - r / radius) * flicker))
                color = (*emitter.color, alpha)
                pygame.draw.circle(
                    gradient,
                    color,
                    (int(radius), int(radius)),
                    r,
                )
            surface.blit(gradient, (center.x - radius, center.y - radius), special_flags=pygame.BLEND_ADD)


class NeonLevel:
    """High-fidelity neon labyrinth level used by the platformer."""

    def __init__(
        self,
        width: int,
        height: int,
        *,
        seed: int | None = None,
        palette: NeonPalette | None = None,
        difficulty: float = 1.0,
    ) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("Level dimensions must be positive")
        self.width = width
        self.height = height
        self.seed = seed or random.randint(0, 999_999)
        self.difficulty = difficulty
        self.random = random.Random(self.seed)
        self.palette = palette or self.random.choice(NEON_PALETTES)
        self.tile_atlas = NeonTileAtlas(self.palette)
        self.tiles: Dict[Tuple[int, int], TileDescriptor] = {}
        self.hazards: List[Hazard] = []
        self.collectible_spawns: List[SpawnPoint] = []
        self.powerup_spawns: List[SpawnPoint] = []
        self.background = NeonBackground(self.palette, width * TILE_SIZE, height * TILE_SIZE, self.random)
        self.particle_field = NeonParticleField(self.palette, self.random)
        self._generate()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def colliders_for_rect(self, rect: pygame.Rect) -> List[pygame.Rect]:
        tiles: List[pygame.Rect] = []
        min_tx = max(0, rect.left // TILE_SIZE - 1)
        max_tx = min(self.width - 1, rect.right // TILE_SIZE + 1)
        min_ty = max(0, rect.top // TILE_SIZE - 1)
        max_ty = min(self.height - 1, rect.bottom // TILE_SIZE + 1)
        for tx in range(min_tx, max_tx + 1):
            for ty in range(min_ty, max_ty + 1):
                descriptor = self.tiles.get((tx, ty))
                if descriptor:
                    tiles.append(descriptor.key.rect())
        return tiles

    def iter_solid_tiles(self) -> Iterator[pygame.Rect]:
        for tile in self.tiles.values():
            yield tile.key.rect()

    def iter_hazards(self) -> Iterator[Hazard]:
        return iter(self.hazards)

    def iter_collectible_spawns(self) -> Iterator[SpawnPoint]:
        return iter(self.collectible_spawns)

    def iter_powerup_spawns(self) -> Iterator[SpawnPoint]:
        return iter(self.powerup_spawns)

    def draw(self, surface: pygame.Surface, camera_rect: pygame.Rect, time: float) -> None:
        self.background.draw(surface, camera_rect)
        tile_surface = pygame.Surface(camera_rect.size, pygame.SRCALPHA)
        for tile in self.tiles.values():
            world_rect = tile.key.rect()
            if not camera_rect.colliderect(world_rect):
                continue
            dest = world_rect.move(-camera_rect.x, -camera_rect.y)
            tile_surface.blit(self.tile_atlas.surface(tile.mask, tile.variant), dest)
        surface.blit(tile_surface, (0, 0))
        self._draw_hazards(surface, camera_rect, time)
        self.particle_field.draw(surface, camera_rect, time)

    def update(self, dt: float) -> None:
        self.background.update(dt)

    def random_spawn(self) -> pygame.Vector2:
        if not self.collectible_spawns:
            return pygame.Vector2(0, 0)
        spawn = self.random.choice(self.collectible_spawns)
        return spawn.position

    # ------------------------------------------------------------------
    # Generation internals
    # ------------------------------------------------------------------
    def _generate(self) -> None:
        self.tiles.clear()
        self.hazards.clear()
        self.collectible_spawns.clear()
        self.powerup_spawns.clear()
        heightmap = self._build_heightmap()
        self._stamp_ground(heightmap)
        self._sprinkle_columns(heightmap)
        self._carve_caverns(heightmap)
        self._finalize_masks()
        self._generate_hazards()
        self._seed_spawns()
        hazard_centers = [
            (hazard.rect.centerx, hazard.rect.y) for hazard in self.hazards
        ]
        collectible_centers = [
            (spawn.position.x, spawn.position.y) for spawn in self.collectible_spawns
        ]
        self.particle_field.seed_emitters(hazard_centers + collectible_centers)

    def _build_heightmap(self) -> List[int]:
        base = self.height // 3
        noise: List[float] = []
        period = max(8, self.width // 6)
        for x in range(self.width + 1):
            value = 0.0
            for octave in range(4):
                frequency = 2 ** octave
                amplitude = 1 / (2 ** octave)
                value += amplitude * math.sin((x / period) * frequency + self.random.uniform(-1, 1))
            noise.append(value)
        heights: List[int] = []
        for x in range(self.width):
            h = base + int((noise[x] + noise[x + 1]) * 3)
            modifier = int(self.difficulty * 2)
            h += self.random.randint(-2 - modifier, 2 + modifier)
            h = max(3, min(self.height - 3, h))
            heights.append(h)
        return heights

    def _stamp_ground(self, heightmap: Sequence[int]) -> None:
        for x, depth in enumerate(heightmap):
            variant_seed = self.random.randint(0, 63)
            for y in range(self.height - depth, self.height):
                self.tiles[(x, y)] = TileDescriptor(TileKey(x, y), 0, variant_seed + y)

    def _sprinkle_columns(self, heightmap: Sequence[int]) -> None:
        column_budget = max(12, self.width // 4)
        for _ in range(column_budget):
            base_x = self.random.randint(0, self.width - 2)
            height = self.random.randint(3, min(self.height // 2, 9))
            base_y = self.height - heightmap[base_x] - self.random.randint(2, 5)
            for y in range(base_y, min(self.height, base_y + height)):
                if y < 0:
                    continue
                variant = self.random.randint(0, 63)
                self.tiles[(base_x, y)] = TileDescriptor(TileKey(base_x, y), 0, variant)
                self.tiles[(base_x + 1, y)] = TileDescriptor(TileKey(base_x + 1, y), 0, variant + 3)

    def _carve_caverns(self, heightmap: Sequence[int]) -> None:
        cavern_budget = max(6, self.width // 6)
        for _ in range(cavern_budget):
            width = self.random.randint(3, 7)
            height = self.random.randint(2, 4)
            start_x = self.random.randint(1, self.width - width - 1)
            ground = self.height - heightmap[start_x] - self.random.randint(4, 9)
            for y in range(ground, ground + height):
                for x in range(start_x, start_x + width):
                    self.tiles.pop((x, y), None)

    def _finalize_masks(self) -> None:
        for (x, y), descriptor in list(self.tiles.items()):
            mask = 0
            if (x, y - 1) in self.tiles:
                mask |= 1
            if (x + 1, y) in self.tiles:
                mask |= 2
            if (x, y + 1) in self.tiles:
                mask |= 4
            if (x - 1, y) in self.tiles:
                mask |= 8
            descriptor.mask = mask
        # remove floating tiles without support
        for (x, y) in list(self.tiles.keys()):
            if (x, y + 1) not in self.tiles and y < self.height - 1:
                below_count = sum(1 for dy in range(1, 4) if (x, y + dy) in self.tiles)
                if below_count == 0 and self.random.random() < 0.35:
                    self.tiles.pop((x, y), None)

    def _generate_hazards(self) -> None:
        hazard_color = tuple(min(255, int(c * 0.9)) for c in self.palette.glow)
        for (x, y), tile in self.tiles.items():
            if tile.mask & 4:
                continue
            if (x, y - 1) not in self.tiles and self.random.random() < 0.28:
                rect = pygame.Rect(
                    x * TILE_SIZE,
                    y * TILE_SIZE - TILE_SIZE // 2,
                    TILE_SIZE,
                    TILE_SIZE // 2,
                )
                hazard = Hazard(rect, damage=1, color=hazard_color, period=self.random.uniform(1.2, 3.6), phase=self.random.random())
                self.hazards.append(hazard)
        # Add vertical laser beams on columns
        beam_budget = max(4, self.width // 8)
        for _ in range(beam_budget):
            x = self.random.randint(2, self.width - 3)
            column = [y for (tx, y) in self.tiles.keys() if tx == x]
            if not column:
                continue
            top = min(column)
            bottom = max(column)
            beam_rect = pygame.Rect(
                x * TILE_SIZE + TILE_SIZE // 3,
                top * TILE_SIZE - TILE_SIZE * 2,
                TILE_SIZE // 3,
                (bottom - top + 3) * TILE_SIZE,
            )
            hazard = Hazard(
                beam_rect,
                damage=2,
                color=tuple(min(255, int(c * 1.1)) for c in self.palette.sparkle),
                period=self.random.uniform(2.4, 5.5),
                phase=self.random.random(),
            )
            self.hazards.append(hazard)

    def _seed_spawns(self) -> None:
        surfaces = [tile for tile in self.tiles.values() if (tile.mask & 1) == 0]
        self.random.shuffle(surfaces)
        collectible_budget = max(18, len(surfaces) // 3)
        used_columns: set[int] = set()
        for tile in surfaces:
            if len(self.collectible_spawns) >= collectible_budget:
                break
            if tile.key.x in used_columns:
                continue
            rect = tile.key.rect()
            spawn = SpawnPoint(
                pygame.Vector2(rect.centerx, rect.top - TILE_SIZE * 0.4),
                tier=self.random.randint(1, 3),
            )
            self.collectible_spawns.append(spawn)
            used_columns.add(tile.key.x)
        power_budget = max(6, collectible_budget // 4)
        high_tiles = sorted(surfaces, key=lambda t: t.key.y)
        for tile in high_tiles[:power_budget * 2]:
            spawn = SpawnPoint(
                pygame.Vector2(tile.key.rect().centerx, tile.key.rect().top - TILE_SIZE * 0.7),
                tier=self.random.randint(2, 4),
            )
            self.powerup_spawns.append(spawn)

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------
    def _draw_hazards(self, surface: pygame.Surface, camera_rect: pygame.Rect, time: float) -> None:
        overlay = pygame.Surface(camera_rect.size, pygame.SRCALPHA)
        for hazard in self.hazards:
            if not camera_rect.colliderect(hazard.rect):
                continue
            rect = hazard.rect.move(-camera_rect.x, -camera_rect.y)
            pulse = (math.sin((time + hazard.phase) * (1.0 / max(0.01, hazard.period))) + 1) * 0.5
            color = (*hazard.color, int(120 + 120 * pulse))
            pygame.draw.rect(overlay, color, rect)
            if hazard.rect.width < TILE_SIZE:
                pygame.draw.rect(overlay, (*hazard.color, 220), rect.inflate(6, 0), 2)
        surface.blit(overlay, (0, 0), special_flags=pygame.BLEND_ADD)
