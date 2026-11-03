import math
import random
import unittest

from wellbeing import config
from wellbeing.physics import Body, Bounds

FRAME = 1 / 60


def screen():
    return Bounds(left=0, top=0, right=1920, bottom=1032)


def make_body(x=960, y=300, seed=1, **kwargs):
    return Body(200, 150, x, y, screen(), rng=random.Random(seed), **kwargs)


def run(body, seconds, frame=FRAME):
    """Step the body like the app does; return (squash, vy, on_floor) per frame."""
    history = []
    for _ in range(round(seconds / frame)):
        body.step(frame)
        history.append((body.squash, body.vy, body.on_floor))
    return history


class FallingTest(unittest.TestCase):
    def test_gravity_pulls_a_resting_body_down(self):
        body = make_body()
        start_y = body.y

        run(body, 0.2)

        self.assertGreater(body.vy, 0)
        self.assertGreater(body.y, start_y)

    def test_it_stretches_while_falling_fast(self):
        body = make_body(y=200)
        history = run(body, 0.4)
        self.assertGreater(max(s for s, _, floor in history if not floor), 0.1)

    def test_it_never_sinks_below_the_floor(self):
        body = make_body(y=100, vy=3000)
        for _ in range(600):
            body.step(FRAME)
            self.assertLessEqual(body.y, body.bounds.bottom + 1e-9)


class JumpCycleTest(unittest.TestCase):
    def test_it_lands_compacted_then_jumps_stretched(self):
        body = make_body(y=200)
        history = run(body, 3.0)

        landed = [i for i, (_, _, floor) in enumerate(history) if floor]
        self.assertTrue(landed, "never landed")
        squash_on_floor = min(s for s, _, floor in history if floor)
        self.assertLess(squash_on_floor, -0.1, "did not compact on landing")

        first_landing = landed[0]
        after = history[first_landing:]
        jumps = [i for i, (_, vy, floor) in enumerate(after) if not floor and vy < 0]
        self.assertTrue(jumps, "never jumped again")
        self.assertGreater(max(after[i][0] for i in jumps), 0.2, "did not stretch on the jump")

    def test_it_keeps_jumping_forever(self):
        body = make_body()
        history = run(body, 30.0)
        launches = sum(
            1 for (_, _, was), (_, _, now) in zip(history, history[1:]) if was and not now
        )
        self.assertGreater(launches, 10)

    def test_jumps_stay_below_the_top_of_the_screen(self):
        for seed in range(20):
            body = make_body(seed=seed)
            for _ in range(round(10 / FRAME)):
                body.step(FRAME)
                _, top, _, _ = body.rect()
                # Only the stretch may poke a little past the top edge.
                self.assertGreater(top, body.bounds.top - body.height * config.MAX_STRETCH)

    def test_bodies_with_their_own_random_numbers_move_independently(self):
        a, b = make_body(seed=1), make_body(seed=2)
        run(a, 5.0)
        run(b, 5.0)
        self.assertNotAlmostEqual(a.x, b.x, places=0)


class ShapeTest(unittest.TestCase):
    def test_squash_and_stretch_keep_the_area(self):
        body = make_body()
        for squash in (-config.MAX_SQUASH, -0.2, 0.0, 0.3, config.MAX_STRETCH):
            body.squash = squash
            sx, sy = body.scale
            self.assertAlmostEqual(sx * sy, 1.0)

    def test_shape_stays_within_its_limits(self):
        for seed in range(20):
            body = make_body(seed=seed, vy=-2500, vx=3000)
            for squash, _, _ in run(body, 10.0):
                self.assertGreaterEqual(squash, -config.MAX_SQUASH - 1e-9)
                self.assertLessEqual(squash, config.MAX_STRETCH + 1e-9)

    def test_window_rect_stands_on_the_floor_when_squashed(self):
        body = make_body(y=1032)
        body.squash = -0.4
        x, y, w, h = body.rect()
        self.assertAlmostEqual(y + h, 1032, delta=1)
        self.assertGreater(w, body.width)
        self.assertLess(h, body.height)


class WallsTest(unittest.TestCase):
    def test_it_bounces_off_the_walls_and_stays_on_screen(self):
        for seed in range(20):
            body = make_body(seed=seed, vx=-3000)
            for _ in range(round(20 / FRAME)):
                body.step(FRAME)
                x, _, w, _ = body.rect()
                self.assertGreaterEqual(x, body.bounds.left - 1)
                self.assertLessEqual(x + w, body.bounds.right + 1)

    def test_hitting_a_wall_squeezes_it_sideways(self):
        body = make_body(x=150, y=500, vx=-2000)
        peak = max(s for s, _, _ in run(body, 0.15))
        self.assertGreater(body.vx, 0, "did not bounce")
        self.assertGreater(peak, 0.15)


class MouseTest(unittest.TestCase):
    def test_a_held_body_stays_where_the_mouse_puts_it(self):
        body = make_body()
        body.grab()
        body.move_to(500, 400)
        run(body, 1.0)
        self.assertEqual((body.x, body.y), (500, 400))

    def test_a_thrown_body_flies_and_speed_is_capped(self):
        body = make_body()
        body.grab()
        body.throw(99999, -99999)
        self.assertEqual(body.vx, config.MAX_THROW_SPEED)
        self.assertEqual(body.vy, -config.MAX_THROW_SPEED)
        x0 = body.x
        body.step(FRAME)
        self.assertGreater(body.x, x0)


class RobustnessTest(unittest.TestCase):
    def test_long_frames_and_odd_timing_never_break_it(self):
        body = make_body()
        rng = random.Random(7)
        for _ in range(3000):
            body.step(rng.choice((0.0, 0.001, FRAME, 0.05, config.MAX_FRAME_TIME)))
            for value in (body.x, body.y, body.vx, body.vy, body.squash):
                self.assertTrue(math.isfinite(value))

    def test_a_body_spawned_outside_the_screen_comes_back(self):
        body = make_body(x=-500, y=5000)
        run(body, 1.0)
        x, y, w, h = body.rect()
        self.assertGreaterEqual(x, -1)
        self.assertLessEqual(y + h, 1033)


if __name__ == "__main__":
    unittest.main()
