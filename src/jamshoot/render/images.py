"""Bounded image decoding with explicit orientation and transparency handling."""

import warnings
from pathlib import Path
from typing import BinaryIO

from PIL import Image, ImageOps, UnidentifiedImageError

from jamshoot.catalog import CUSTOM_MAX_PIXELS
from jamshoot.core.project import ProjectError

MAX_IMAGE_PIXELS = CUSTOM_MAX_PIXELS


def load_image(path: str | Path | BinaryIO, *, max_pixels: int = MAX_IMAGE_PIXELS) -> Image.Image:
    """An RGB, EXIF-rotated copy of the image with transparency flattened onto white.

    ProjectError unless it is a still PNG, JPEG or WebP of at most ``max_pixels`` pixels.
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as source:
                if source.format not in {"PNG", "JPEG", "WEBP"}:
                    raise ProjectError(f"Unsupported image format: {source.format}")
                if source.width * source.height > max_pixels:
                    raise ProjectError(f"Input image exceeds pixel limit {max_pixels}: {path}")
                if getattr(source, "n_frames", 1) != 1:
                    raise ProjectError(f"Animated image is unsupported: {path}")
                oriented = ImageOps.exif_transpose(source).convert("RGBA")
                background = Image.new("RGBA", oriented.size, "white")
                background.alpha_composite(oriented)
                return background.convert("RGB")
    except (
        OSError,
        ValueError,
        UnidentifiedImageError,
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
    ) as error:
        if isinstance(error, ProjectError):
            raise
        raise ProjectError(f"Cannot decode image {path}: {error}") from error
