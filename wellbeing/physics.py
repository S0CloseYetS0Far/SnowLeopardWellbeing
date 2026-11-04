"""Jumping with squash and stretch, for one picture.

Plain Python with no Qt, so it can be tested on its own. A body's position
(x, y) is the bottom-centre of its box, so when it squashes on landing it
stays standing on the floor and when it stretches it grows upwards.

The life of a body: it falls (stretching as it speeds up), lands (compacts),
crouches for a moment, then jumps (stretches again) in a random direction.
Each body has its own random numbers, so every picture moves on its own.

With more than one monitor, each monitor's free area (above its taskbar) is
a room with its own floor. A side of a room that touches another monitor is
open: a picture walks, jumps or is thrown straight through into the next
room. Sides with nothing beyond them are walls it bounces off.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from . import config


@dataclass
class Bounds:
    """The area the pictures live in. ``bottom`` is the floor."""

    left: float
    top: float
    right: float
    bottom: float


LEFT, RIGHT, UP, DOWN = "left", "right", "up", "down"
EDGE_GAP = 8.0  # monitors this close count as touching
STEP_UP = 40.0  # a picture may hop onto a floor this much higher


class World:
    """Every monitor's area (in one shared coordinate space) and how they join."""

    def __init__(self, areas: list[Bounds]) -> None:
        self.areas = list(areas)

    def owns(self, area: Bounds) -> bool:
        return any(a is area for a in self.areas)

    def area_at(self, x: float, y: float) -> Bounds:
        """The area containing (x, y), or the nearest one."""
        best, best_distance = self.areas[0], math.inf
        for a in self.areas:
            dx = max(a.left - x, 0.0, x - a.right)
            dy = max(a.top - y, 0.0, y - a.bottom)
            distance = dx * dx + dy * dy
            if distance < best_distance:
                best, best_distance = a, distance
        return best

    def beyond(self, area: Bounds, side: str, x: float, y: float) -> Bounds | None:
        """The area through *area*'s *side* that a body standing at (x, y) fits into."""
        for a in self.areas:
            if a is area:
                continue
            if side == LEFT:
                touching = abs(a.right - area.left) <= EDGE_GAP
                fits = a.top < y <= a.bottom + STEP_UP
            elif side == RIGHT:
                touching = abs(a.left - area.right) <= EDGE_GAP
                fits = a.top < y <= a.bottom + STEP_UP
            elif side == DOWN:
                touching = abs(a.top - area.bottom) <= EDGE_GAP
                fits = a.left <= x <= a.right
            else:
                touching = abs(a.bottom - area.top) <= EDGE_GAP
                fits = a.left <= x <= a.right
            if touching and fits:
                return a
        return None


class Body:
    def __init__(
        self,
        width: float,
        height: float,
        x: float,
        y: float,
        bounds: Bounds | World,
        *,
        vx: float = 0.0,
        vy: float = 0.0,
        rng: random.Random | None = None,
    ) -> None:
        self.width = float(width)  # size at rest, before squash or stretch
        self.height = float(height)
        self.x = float(x)
        self.y = float(y)
        self.vx = float(vx)
        self.vy = float(vy)
        if isinstance(bounds, World):
            self.world = bounds
            self.bounds = bounds.area_at(x, y)
        else:
            self.world = World([bounds])
            self.bounds = bounds  # the area (monitor) it is in now
        self.rng = rng or random.Random()

        self.squash = 0.0  # > 0 stretched (taller, thinner), < 0 compacted
        self.squash_speed = 0.0
        self.on_floor = False
        self.held = False
        self._crouch_left = 0.0
        self._next_jump = 0.5  # 0..1, how big the coming jump will be
        self._direction = self.rng.choice((-1.0, 1.0))

    # --- shape ---------------------------------------------------------------
    @property
    def scale(self) -> tuple[float, float]:
        """(width factor, height factor). Their product is always 1."""
        sy = 1.0 + self.squash
        return 1.0 / sy, sy

    def rect(self) -> tuple[int, int, int, int]:
        """Window geometry (x, y, width, height) for the current shape."""
        sx, sy = self.scale
        width = self.width * sx
        height = self.height * sy
        return (
            round(self.x - width / 2),
            round(self.y - height),
            max(1, round(width)),
            max(1, round(height)),
        )

    # --- the mouse -------------------------------------------------------------
    def grab(self) -> None:
        self.held = True
        self.on_floor = False
        self.vx = self.vy = 0.0

    def move_to(self, x: float, y: float) -> None:
        self.x, self.y = float(x), float(y)

    def throw(self, vx: float, vy: float) -> None:
        limit = config.MAX_THROW_SPEED
        self.held = False
        self.bounds = self.world.area_at(self.x, self.y - self.height / 2)
        self.vx = max(-limit, min(limit, float(vx)))
        self.vy = max(-limit, min(limit, float(vy)))

    # --- simulation ------------------------------------------------------------
    def step(self, dt: float) -> None:
        """Advance the body by *dt* seconds."""
        while dt > 1e-9:
            h = min(dt, config.MAX_STEP)
            self._step(h)
            dt -= h

    def _step(self, dt: float) -> None:
        if not self.world.owns(self.bounds):  # the monitors changed
            self.bounds = self.world.area_at(self.x, self.y - self.height / 2)
        if self.held:
            target = 0.0
        elif self.on_floor:
            self.y = self.bounds.bottom
            self.vx *= math.exp(-config.FLOOR_FRICTION * dt)
            self.x += self.vx * dt
            target = -self._crouch_depth()
            self._crouch_left -= dt
            if self._crouch_left <= 0:
                self._jump()
                target = self._flying_stretch()
        else:
            self.vy += config.GRAVITY * dt
            self.x += self.vx * dt
            self.y += self.vy * dt
            target = self._flying_stretch()
        self._spring(target, dt)
        if not self.held:
            self._collide()
            self._change_rooms()

    def _flying_stretch(self) -> float:
        return min(abs(self.vy) * config.STRETCH_PER_SPEED, config.MAX_STRETCH)

    def _crouch_depth(self) -> float:
        low, high = config.CROUCH_SQUASH
        return low + (high - low) * self._next_jump

    def _spring(self, target: float, dt: float) -> None:
        accel = (
            config.SPRING_STIFFNESS * (target - self.squash)
            - config.SPRING_DAMPING * self.squash_speed
        )
        self.squash_speed += accel * dt
        self.squash += self.squash_speed * dt
        if self.squash > config.MAX_STRETCH:
            self.squash = config.MAX_STRETCH
            self.squash_speed = min(self.squash_speed, 0.0)
        elif self.squash < -config.MAX_SQUASH:
            self.squash = -config.MAX_SQUASH
            self.squash_speed = max(self.squash_speed, 0.0)

    def _collide(self) -> None:
        b, world = self.bounds, self.world
        sx, sy = self.scale
        half_width = self.width * sx / 2
        if self.x - half_width < b.left and not world.beyond(b, LEFT, self.x, self.y):
            self.x = b.left + half_width
            if self.vx < 0:
                self.squash_speed += -self.vx * config.WALL_SQUASH
                self.vx = -self.vx * config.WALL_BOUNCE
        elif self.x + half_width > b.right and not world.beyond(b, RIGHT, self.x, self.y):
            self.x = b.right - half_width
            if self.vx > 0:
                self.squash_speed += self.vx * config.WALL_SQUASH
                self.vx = -self.vx * config.WALL_BOUNCE

        if self.on_floor:
            return
        height = self.height * sy
        if self.y - height < b.top and self.vy < 0 and not world.beyond(b, UP, self.x, self.y):
            self.y = b.top + height
            self.squash_speed -= -self.vy * config.LANDING_SQUASH
            self.vy = -self.vy * config.CEILING_BOUNCE
        if self.y >= b.bottom and not world.beyond(b, DOWN, self.x, self.y):
            self.y = b.bottom
            if self.vy >= 0:
                self._land()

    def _change_rooms(self) -> None:
        """Move into the next monitor's area once the middle of the body is in it."""
        b = self.bounds
        cx, cy = self.x, self.y - self.height * self.scale[1] / 2
        if b.left <= cx <= b.right and b.top <= cy <= b.bottom:
            return
        for side, outside in ((LEFT, cx < b.left), (RIGHT, cx > b.right), (UP, cy < b.top), (DOWN, cy > b.bottom)):
            if not outside:
                continue
            area = self.world.beyond(b, side, self.x, self.y)
            if area is None:
                continue
            self.bounds = area
            if self.y > area.bottom:  # a slightly higher floor: hop up onto it
                self.y = area.bottom
            elif self.on_floor and self.y < area.bottom:  # walked off a ledge
                self.on_floor = False
            return

    def _land(self) -> None:
        self.squash_speed -= self.vy * config.LANDING_SQUASH
        self.vy = 0.0
        self.vx *= config.LANDING_SLIDE
        self.on_floor = True
        self._next_jump = self.rng.random()
        self._crouch_left = self.rng.uniform(*config.CROUCH_TIME)

    def _jump(self) -> None:
        b = self.bounds
        low, high = config.JUMP_HEIGHT
        room = max(b.bottom - b.top - self.height, 1.0)
        rise = room * (low + (high - low) * self._next_jump)
        self.vy = -math.sqrt(2 * config.GRAVITY * rise)

        if self.rng.random() > config.KEEP_DIRECTION:
            self._direction = -self._direction
        margin = self.width  # near a wall, always jump away from it
        if self.x - self.width / 2 < b.left + margin and not self.world.beyond(b, LEFT, self.x, self.y):
            self._direction = 1.0
        elif self.x + self.width / 2 > b.right - margin and not self.world.beyond(b, RIGHT, self.x, self.y):
            self._direction = -1.0
        self.vx = self._direction * self.rng.uniform(*config.JUMP_SIDEWAYS)

        self.on_floor = False
        self.squash_speed += config.LAUNCH_STRETCH
