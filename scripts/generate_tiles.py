#!/usr/bin/env python3
"""
Generate TMS tiles from Natural Earth II raster for offline CesiumJS use.

Downloads NE2_HR_LC_SR_W (21600x10800 JPEG, ~25MB) and slices into
256x256 TMS tiles at zoom levels 0 through max_zoom.

Tile scheme: TMS (y=0 at bottom), matching Cesium's TileMapServiceImageryProvider.
Output: cop/public/tiles/NaturalEarth/{z}/{x}/{y}.jpg + tilemapresource.xml
"""

import math
import os
import sys
import urllib.request
from pathlib import Path

from PIL import Image
Image.MAX_IMAGE_PIXELS = 300_000_000  # 21600x10800 = 233M pixels

# Natural Earth II with shaded relief + water — 21600x10800 JPEG (~25MB)
SOURCE_URL = "https://naciscdn.org/naturalearth/10m/raster/NE2_HR_LC_SR_W.zip"
SOURCE_TIFF = "NE2_HR_LC_SR_W.tif"

TILE_SIZE = 256
OUTPUT_DIR = Path(__file__).parent.parent / "cop" / "public" / "tiles" / "NaturalEarth"


def download_source(dest_dir: Path) -> Path:
    """Download and extract the Natural Earth raster."""
    zip_path = dest_dir / "ne2.zip"
    tif_path = dest_dir / SOURCE_TIFF

    if tif_path.exists():
        print(f"Source raster already exists: {tif_path}")
        return tif_path

    # Also check for a .jpg version (some distributions)
    jpg_path = dest_dir / SOURCE_TIFF.replace(".tif", ".jpg")
    if jpg_path.exists():
        return jpg_path

    print(f"Downloading Natural Earth II raster (~25MB)...")
    dest_dir.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(SOURCE_URL, zip_path)
    print("Extracting...")

    import zipfile
    with zipfile.ZipFile(zip_path, "r") as zf:
        # Find the main raster file
        for name in zf.namelist():
            if name.endswith((".tif", ".jpg", ".png")) and "HR" in name:
                zf.extract(name, dest_dir)
                extracted = dest_dir / name
                if extracted.exists():
                    zip_path.unlink()
                    return extracted

        # Fallback: extract everything
        zf.extractall(dest_dir)

    zip_path.unlink()
    # Find the extracted file
    for ext in (".tif", ".jpg", ".png"):
        for f in dest_dir.rglob(f"*{ext}"):
            if "HR" in f.name or "NE2" in f.name:
                return f

    raise FileNotFoundError("Could not find raster in downloaded archive")


def generate_tiles(source_path: Path, max_zoom: int = 6):
    """Generate TMS tiles from the source raster."""
    print(f"Opening source raster: {source_path}")
    img = Image.open(source_path)
    src_w, src_h = img.size
    print(f"Source size: {src_w}x{src_h}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    total_tiles = 0

    for zoom in range(max_zoom + 1):
        num_tiles_x = 2 ** (zoom + 1)  # longitude tiles
        num_tiles_y = 2 ** zoom         # latitude tiles
        level_dir = OUTPUT_DIR / str(zoom)
        level_tiles = 0

        print(f"Zoom {zoom}: {num_tiles_x}x{num_tiles_y} = {num_tiles_x * num_tiles_y} tiles...", end=" ", flush=True)

        # Scale source to match this zoom level's total pixel dimensions
        target_w = num_tiles_x * TILE_SIZE
        target_h = num_tiles_y * TILE_SIZE

        # Resize source image to match tile grid
        if target_w <= src_w:
            resized = img.resize((target_w, target_h), Image.LANCZOS)
        else:
            resized = img.resize((target_w, target_h), Image.LANCZOS)

        for tx in range(num_tiles_x):
            col_dir = level_dir / str(tx)
            col_dir.mkdir(parents=True, exist_ok=True)

            for ty_tms in range(num_tiles_y):
                # TMS y is flipped (0 at bottom)
                # In image coords, y=0 is top (north), so we need to flip
                ty_img = num_tiles_y - 1 - ty_tms

                left = tx * TILE_SIZE
                upper = ty_img * TILE_SIZE
                right = left + TILE_SIZE
                lower = upper + TILE_SIZE

                tile = resized.crop((left, upper, right, lower))
                tile_path = col_dir / f"{ty_tms}.jpg"
                tile.save(tile_path, "JPEG", quality=85)
                level_tiles += 1

        total_tiles += level_tiles
        print(f"done ({level_tiles} tiles)")

        # Free memory
        del resized

    print(f"\nTotal: {total_tiles} tiles")
    return total_tiles


def write_tilemapresource(max_zoom: int):
    """Write tilemapresource.xml for Cesium's TileMapServiceImageryProvider."""
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<TileMap version="1.0.0" tilemapservice="http://tms.osgeo.org/1.0.0">
  <Title>Natural Earth II</Title>
  <Abstract>Natural Earth II with shaded relief and water</Abstract>
  <SRS>EPSG:4326</SRS>
  <BoundingBox minx="-180" miny="-90" maxx="180" maxy="90"/>
  <Origin x="-180" y="-90"/>
  <TileFormat width="256" height="256" mime-type="image/jpeg" extension="jpg"/>
  <TileSets profile="geodetic">
"""
    for z in range(max_zoom + 1):
        units_per_pixel = 0.703125 / (2 ** z)
        xml += f'    <TileSet href="{z}" units-per-pixel="{units_per_pixel}" order="{z}"/>\n'
    xml += """  </TileSets>
</TileMap>
"""
    out = OUTPUT_DIR / "tilemapresource.xml"
    out.write_text(xml)
    print(f"Wrote {out}")


def main():
    max_zoom = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    print(f"Generating tiles up to zoom level {max_zoom}")
    print(f"Output: {OUTPUT_DIR}\n")

    # Download source
    cache_dir = Path(__file__).parent / "tile_cache"
    source = download_source(cache_dir)

    # Generate tiles
    generate_tiles(source, max_zoom)

    # Write TMS metadata
    write_tilemapresource(max_zoom)

    # Report size
    total_size = sum(f.stat().st_size for f in OUTPUT_DIR.rglob("*") if f.is_file())
    print(f"\nTile set size: {total_size / 1024 / 1024:.1f} MB")
    print("Done! Update cesium-setup.js to use /tiles/NaturalEarth as the offline provider.")


if __name__ == "__main__":
    main()
