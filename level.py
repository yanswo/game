"""Procedural level generation utilities for the pixel-art platformer."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Iterator, Sequence, Set

import pygame

TILE_SIZE = 16


@dataclass(frozen=True)
class Tile:
    """Represents a single solid tile within the level grid."""

    x: int
    y: int

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(self.x * TILE_SIZE, self.y * TILE_SIZE, TILE_SIZE, TILE_SIZE)


@dataclass(frozen=True)
class Hazard:
    """Simple rectangular hazard (such as spikes)."""

    x: float
    y: float
    width: int
    height: int
    kind: str = "spike"

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.width, self.height)


@dataclass(frozen=True)
class SpawnPoint:
    """Spawn location for collectibles or power-ups."""

    x: float
    y: float

    def to_vector(self) -> pygame.Vector2:
        return pygame.Vector2(self.x, self.y)


@dataclass
class Level:
    """A procedurally generated 2D tile-based level with hazards and pickups."""

    width: int
    height: int
    base_ground_height: int = 5
    platform_attempts: int = 75
    seed: int | None = None
    random: random.Random = field(init=False, repr=False)
    _tiles: Set[Tile] = field(init=False, default_factory=set, repr=False)
    _surface_tiles: Set[Tile] = field(init=False, default_factory=set, repr=False)
    _ground_surface_tiles: Set[Tile] = field(init=False, default_factory=set, repr=False)
    _platform_surface_tiles: Set[Tile] = field(init=False, default_factory=set, repr=False)
    hazards: list[Hazard] = field(init=False, default_factory=list)
    collectible_spawns: list[SpawnPoint] = field(init=False, default_factory=list)
    powerup_spawns: list[SpawnPoint] = field(init=False, default_factory=list)
    goal_rect: pygame.Rect = field(init=False)

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Level dimensions must be positive")
        self.random = random.Random(self.seed)
        self._generate()

    def _generate(self) -> None:
        self._tiles.clear()

        # Generate a rolling ground that varies slightly per column.
        previous_ground_depth = self.base_ground_height
        for x in range(self.width):
            if x == 0:
                ground_depth = previous_ground_depth
            else:
                change = self.random.randint(-1, 1)
                occasional_hill = 1 if self.random.random() < 0.05 else 0
                ground_depth = max(
                    3,
                    min(self.height // 2, previous_ground_depth + change + occasional_hill),
                )
            previous_ground_depth = ground_depth
            for y in range(self.height - ground_depth, self.height):
                self._tiles.add(Tile(x, y))

        # Scatter floating platforms across the level.
        for _ in range(self.platform_attempts):
            platform_width = self.random.randint(3, 7)
            x = self.random.randint(0, max(0, self.width - platform_width - 1))
            y = self.random.randint(3, max(3, self.height - self.base_ground_height - 6))
            vertical_noise = self.random.choice([-1, 0, 0, 1])
            y = max(2, min(self.height - 6, y + vertical_noise))
            for offset in range(platform_width):
                self._tiles.add(Tile(x + offset, y))
                # Add some decorative support tiles.
                if self.random.random() < 0.18:
                    self._tiles.add(Tile(x + offset, y + 1))

        self._build_surface_cache()
        self._generate_hazards_and_pickups()
        self._build_goal_rect()

    def _build_surface_cache(self) -> None:
        self._surface_tiles.clear()
        self._ground_surface_tiles.clear()
        self._platform_surface_tiles.clear()
        for tile in self._tiles:
            above = Tile(tile.x, tile.y - 1)
            if above not in self._tiles:
                self._surface_tiles.add(tile)
                below = Tile(tile.x, tile.y + 1)
                if below in self._tiles:
                    self._ground_surface_tiles.add(tile)
                else:
                    self._platform_surface_tiles.add(tile)

    def _generate_hazards_and_pickups(self) -> None:
        self.hazards = []
        self.collectible_spawns = []
        self.powerup_spawns = []

        # Generate spikes on exposed ground.
        for tile in self._ground_surface_tiles:
            if tile.y <= 1:
                continue
            if self.random.random() < 0.065:
                spike_height = TILE_SIZE // 2
                spike_y = tile.y * TILE_SIZE + TILE_SIZE - spike_height
                hazard = Hazard(tile.x * TILE_SIZE, spike_y, TILE_SIZE, spike_height)
                self.hazards.append(hazard)

        # Choose candidate positions for collectibles and power-ups.
        all_surfaces = list(self._surface_tiles)
        self.random.shuffle(all_surfaces)

        used_columns: Set[int] = set()
        collectible_budget = max(12, self.width // 4)
        for tile in all_surfaces:
            if len(self.collectible_spawns) >= collectible_budget:
                break
            if tile.x in used_columns:
                continue
            if any(h.rect.colliderect(pygame.Rect(tile.x * TILE_SIZE, tile.y * TILE_SIZE, TILE_SIZE, TILE_SIZE)) for h in self.hazards):
                continue
            used_columns.add(tile.x)
            spawn_y = tile.y * TILE_SIZE - TILE_SIZE * 0.35
            self.collectible_spawns.append(
                SpawnPoint(tile.x * TILE_SIZE + TILE_SIZE / 2, spawn_y)
            )

        # Power-ups appear more rarely and only on ground columns with some spacing.
        powerup_candidates = [tile for tile in self._ground_surface_tiles if tile.x % 9 in (2, 5, 7)]
        self.random.shuffle(powerup_candidates)
        powerup_target = min(6, max(2, self.width // 45))
        for tile in powerup_candidates:
            if len(self.powerup_spawns) >= powerup_target:
                break
            if tile.x in used_columns:
                continue
            used_columns.add(tile.x)
            spawn_y = tile.y * TILE_SIZE - TILE_SIZE * 0.5
            self.powerup_spawns.append(
                SpawnPoint(tile.x * TILE_SIZE + TILE_SIZE / 2, spawn_y)
            )

    def _build_goal_rect(self) -> None:
        # Place a finish area near the end of the level on solid ground.
        goal_column = max(self.width - 8, 1)
        candidate_columns = range(goal_column, self.width - 1)
        goal_y = self.height - self.base_ground_height - 4
        for column in candidate_columns:
            surface_tiles = [tile for tile in self._ground_surface_tiles if tile.x == column]
            if surface_tiles:
                top_tile = min(surface_tiles, key=lambda t: t.y)
                goal_y = top_tile.y - 3
                goal_column = column
                break
        goal_x = goal_column * TILE_SIZE
        goal_y_pixels = max(1, goal_y) * TILE_SIZE
        goal_width = TILE_SIZE * 3
        goal_height = TILE_SIZE * 5
        self.goal_rect = pygame.Rect(goal_x, goal_y_pixels, goal_width, goal_height)

    @property
    def tiles(self) -> Sequence[Tile]:
        return tuple(self._tiles)

    def tiles_in_region(self, rect: pygame.Rect) -> Iterator[Tile]:
        """Return tiles that intersect the given rectangle."""

        min_x = max(0, rect.left // TILE_SIZE - 1)
        max_x = min(self.width - 1, rect.right // TILE_SIZE + 1)
        min_y = max(0, rect.top // TILE_SIZE - 1)
        max_y = min(self.height - 1, rect.bottom // TILE_SIZE + 1)
        for x in range(min_x, max_x + 1):
            for y in range(min_y, max_y + 1):
                tile = Tile(x, y)
                if tile in self._tiles:
                    yield tile

    def is_surface_tile(self, tile: Tile) -> bool:
        return tile in self._surface_tiles

    def is_ground_surface(self, tile: Tile) -> bool:
        return tile in self._ground_surface_tiles

    @property
    def pixel_width(self) -> int:
        return self.width * TILE_SIZE

    @property
    def pixel_height(self) -> int:
        return self.height * TILE_SIZE


def create_default_level(seed: int | None = None) -> Level:
    """Convenience helper to build a standard sized level."""

    return Level(width=220, height=64, base_ground_height=6, platform_attempts=90, seed=seed)
