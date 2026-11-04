"""Pictures moving between monitors."""

import random
import unittest

from wellbeing.physics import Body, Bounds, World

# Two 1920-wide monitors side by side; the right one sits 3 px lower,
# like a real desk where the screens do not line up exactly.
LEFT_SCREEN = Bounds(0, 0, 1920, 1032)
RIGHT_SCREEN = Bounds(1920, 3, 3840, 1035)


def two_monitors():
    return World([Bounds(0, 0, 1920, 1032), Bounds(1920, 3, 3840, 1035)])


def walker(world, x, vx, y=1032.0):
    body = Body(200, 150, x, y, world, rng=random.Random(1))
    body.vx = vx
    return body


class WorldTest(unittest.TestCase):
    def test_area_at_finds_the_monitor_or_the_nearest(self):
        world = two_monitors()
        self.assertIs(world.area_at(100, 500), world.areas[0])
        self.assertIs(world.area_at(3000, 500), world.areas[1])
        self.assertIs(world.area_at(9999, 500), world.areas[1])

    def test_touching_sides_are_open_and_outer_sides_are_walls(self):
        world = two_monitors()
        left, right = world.areas
        self.assertIs(world.beyond(left, "right", 1900, 1032), right)
        self.assertIs(world.beyond(right, "left", 1940, 1035), left, "a 3 px step is no wall")
        self.assertIsNone(world.beyond(left, "left", 10, 1032))
        self.assertIsNone(world.beyond(right, "right", 3830, 1035))

    def test_a_thrown_picture_flies_into_the_next_monitor(self):
        world = two_monitors()
        body = walker(world, 1700, 0, y=600)
        body.grab()
        body.throw(3000, -200)
        for _ in range(40):
            body.step(1 / 60)
        self.assertIs(body.bounds, world.areas[1])
        self.assertGreater(body.x, 1920)

    def test_it_can_come_back_the_other_way(self):
        world = two_monitors()
        body = walker(world, 2100, 0, y=600)
        body.grab()
        body.throw(-3000, -200)
        for _ in range(40):
            body.step(1 / 60)
        self.assertIs(body.bounds, world.areas[0])
        self.assertLess(body.x, 1920)

    def test_on_its_own_it_wanders_across_both_monitors(self):
        world = two_monitors()
        visited = set()
        for seed in range(6):
            body = Body(250, 180, 960, 500, world, rng=random.Random(seed))
            for _ in range(60 * 60):
                body.step(1 / 60)
                visited.add(world.areas.index(body.bounds))
        self.assertEqual(visited, {0, 1})

    def test_it_always_stays_inside_the_desktop(self):
        world = two_monitors()
        body = Body(250, 180, 960, 500, world, rng=random.Random(4))
        for _ in range(60 * 120):
            body.step(1 / 60)
            b = body.bounds
            self.assertGreaterEqual(body.x, 0)
            self.assertLessEqual(body.x, 3840)
            self.assertLessEqual(body.y, b.bottom + 1e-6)

    def test_it_lands_on_the_floor_of_the_monitor_it_is_on(self):
        world = two_monitors()
        body = Body(200, 150, 3000, 400, world, rng=random.Random(2))
        for _ in range(120):
            body.step(1 / 120)
            if body.on_floor:
                break
        self.assertTrue(body.on_floor)
        self.assertAlmostEqual(body.y, 1035)

    def test_a_monitor_below_lets_it_fall_through(self):
        world = World([Bounds(0, 0, 1920, 1080), Bounds(0, 1080, 1920, 2160)])
        body = Body(200, 150, 960, 900, world, rng=random.Random(3))
        for _ in range(240):
            body.step(1 / 120)
        self.assertIs(body.bounds, world.areas[1])
        self.assertGreater(body.y, 1080)

    def test_unplugging_a_monitor_brings_its_pictures_back(self):
        world = two_monitors()
        body = Body(200, 150, 3000, 600, world, rng=random.Random(5))
        world.areas[:] = [Bounds(0, 0, 1920, 1032)]
        for _ in range(120):
            body.step(1 / 60)
        self.assertIs(body.bounds, world.areas[0])
        self.assertLessEqual(body.x + body.width / 2, 1920 + 1)


if __name__ == "__main__":
    unittest.main()
