"""Jumping with squash and stretch, for one picture.

Plain Python with no Qt, so it can be tested on its own. A body's position
(x, y) is the bottom-centre of its box, so when it squashes on landing it
stays standing on the floor and when it stretches it grows upwards.

The life of a body: it falls (stretching as it speeds up), lands (compacts),
crouches for a moment, then jumps (stretches again) in a random direction.
Each body has its own random numbers, so every picture moves on its own.
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


class Body:
    def __init__(
        self,
        width: float,
        height: float,
        x: float,
        y: float,
        bounds: Bounds,
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
        self.bounds = bounds
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
        b = self.bounds
        sx, sy = self.scale
        half_width = self.width * sx / 2
        if self.x - half_width < b.left:
            self.x = b.left + half_width
            if self.vx < 0:
                self.squash_speed += -self.vx * config.WALL_SQUASH
                self.vx = -self.vx * config.WALL_BOUNCE
        elif self.x + half_width > b.right:
            self.x = b.right - half_width
            if self.vx > 0:
                self.squash_speed += self.vx * config.WALL_SQUASH
                self.vx = -self.vx * config.WALL_BOUNCE

        if self.on_floor:
            return
        height = self.height * sy
        if self.y - height < b.top and self.vy < 0:
            self.y = b.top + height
            self.squash_speed -= -self.vy * config.LANDING_SQUASH
            self.vy = -self.vy * config.CEILING_BOUNCE
        if self.y >= b.bottom:
            self.y = b.bottom
            if self.vy >= 0:
                self._land()

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
        if self.x - self.width / 2 < b.left + margin:
            self._direction = 1.0
        elif self.x + self.width / 2 > b.right - margin:
            self._direction = -1.0
        self.vx = self._direction * self.rng.uniform(*config.JUMP_SIDEWAYS)

        self.on_floor = False
        self.squash_speed += config.LAUNCH_STRETCH
