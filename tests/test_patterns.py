"""Background pattern seeds, density, scale, rotation and opacity."""

import hashlib
import unittest

from PIL import Image, ImageChops

from jamshoot.core.project import load_schema
from jamshoot.render.background import render_background


def coverage(
    pattern: str,
    seed: str = "audit",
    size: tuple[int, int] = (320, 200),
    **settings: float,
) -> Image.Image:
    """Grayscale coverage of ``pattern``, white on black, after rotation and crop."""
    return render_background(
        size,
        {
            "pattern": pattern,
            "seed": seed,
            "colors": {"top": "#000000", "bottom": "#000000", "accent": "#ffffff"},
            "patternSettings": {"opacity": 100, **settings},
        },
    ).convert("L")


class PatternTests(unittest.TestCase):
    """Seeds give distinct arrangements; control edits keep existing shapes."""

    def test_seed_diversity_for_every_pattern(self):
        """Every pattern except ``none`` gives many distinct images across seeds."""
        for pattern in load_schema()["$defs"]["pattern"]["enum"]:
            if pattern == "none":
                continue
            with self.subTest(pattern=pattern):
                fingerprints = {
                    hashlib.sha256(coverage(pattern, str(seed)).tobytes()).digest()
                    for seed in range(200)
                }
                self.assertGreaterEqual(len(fingerprints), 190)

    def test_density_keeps_scattered_shapes_when_the_rounded_count_is_unchanged(self):
        """A density change that rounds to the same shape count renders identical pixels."""
        for seed in ("67", "68", "184"):
            with self.subTest(seed=seed):
                difference = ImageChops.difference(
                    coverage("confetti", seed, density=53.65),
                    coverage("confetti", seed, density=53.66),
                )
                self.assertIsNone(difference.getbbox())

    def test_density_adds_scattered_shapes_without_moving_existing_ones(self):
        """Higher density keeps every sparse shape and adds coverage."""
        sparse = coverage("confetti", "68", density=25)
        dense = coverage("confetti", "68", density=75)
        self.assertIsNone(ImageChops.subtract(sparse, dense).getbbox())
        self.assertGreater(sum(dense.tobytes()), sum(sparse.tobytes()))

    def test_flat_waves_still_respond_to_seed(self):
        """Waves with zero amplitude still vary with the seed."""
        self.assertGreater(
            len({coverage("waves", str(seed), amplitude=0).tobytes() for seed in range(50)}),
            40,
        )

    def test_sparse_arcs_reach_canvas_from_distant_centers(self):
        """Sparse arcs at a large scale still draw on the canvas."""
        for density in (1, 2, 3):
            with self.subTest(density=density):
                self.assertIsNotNone(coverage("arcs", "8", density=density, scale=220).getbbox())

    def test_mesh_preserves_bright_wave_rows_at_intersections(self):
        """Mesh keeps the wave rows' brightness at crossings and adds coverage."""
        for opacity in (20, 100):
            with self.subTest(opacity=opacity):
                waves = coverage("waves", amplitude=0, opacity=opacity)
                mesh = coverage("mesh", amplitude=0, opacity=opacity)
                difference = ImageChops.subtract(waves, mesh)
                # Bicubic sampling can ring at edges, but cannot erase row interiors.
                self.assertEqual(sum(difference.histogram()[round(opacity * 0.24) + 1 :]), 0)
                self.assertGreater(sum(mesh.tobytes()), sum(waves.tobytes()))

    def test_small_scale_range_changes_geometry_on_small_canvases(self):
        """Scales 10 and 30 render differently on small canvases for regular patterns."""
        for size in ((160, 96), (320, 200)):
            for pattern in ("dots", "circles", "grid", "hexagons", "stars", "checkerboard"):
                with self.subTest(size=size, pattern=pattern):
                    difference = ImageChops.difference(
                        coverage(pattern, size=size, scale=10),
                        coverage(pattern, size=size, scale=30),
                    )
                    self.assertIsNotNone(difference.getbbox())

    def test_rotation_never_exceeds_the_requested_opacity(self):
        """A rotated pattern at 20% opacity has no pixel above 51 of 255."""
        for pattern in load_schema()["$defs"]["pattern"]["enum"]:
            with self.subTest(pattern=pattern):
                image = coverage(pattern, opacity=20, rotation=30)
                self.assertEqual(sum(image.histogram()[52:]), 0)

    def test_tiny_round_motifs_remain_separate_points(self):
        """At scale 10 on a small canvas, dots and circles cover under half of it."""
        for pattern in ("dots", "circles"):
            with self.subTest(pattern=pattern):
                image = coverage(pattern, size=(160, 96), scale=10)
                self.assertGreater(sum(image.tobytes()), 0)
                self.assertLess(sum(image.tobytes()), image.width * image.height * 127)
