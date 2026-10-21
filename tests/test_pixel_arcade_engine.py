import pytest
from pixel_arcade_engine import (
    ReversiblePixelGrid,
    InvaderSparseScanner,
    PacmanGhostProbes,
    ProbeTargets,
    NesAttributeTable,
    GalaxianWaveEngine,
    ChrTileBank,
)


def test_reversibility_and_rollback():
    """Verify that swap operations and rollback restore pixels and active mask completely."""
    grid = ReversiblePixelGrid(8, 8)
    grid.pixels[10] = 1
    grid.pixels[25] = 2
    grid.pixels[40] = 3
    grid.rebuild_active_mask()

    initial_pixels = list(grid.pixels)
    initial_mask = grid.active_mask

    grid.swap_pixels_reversible(10, 11)
    grid.swap_pixels_reversible(25, 26)
    grid.swap_pixels_reversible(40, 50)
    grid.swap_pixels_reversible(11, 12)

    assert grid.pixels != initial_pixels
    assert len(grid._reversible_log) == 4

    steps_rolled_back = grid.rollback_all()
    assert steps_rolled_back == 4
    assert grid.pixels == initial_pixels
    assert grid.active_mask == initial_mask


def test_sparse_scanner_iteration_and_sentinel():
    """Verify O(N) iteration count for N active pixels and O(1) sentinel collision check."""
    grid = ReversiblePixelGrid(8, 8)

    interior_indices = [18, 19, 27, 35, 42]
    for idx in interior_indices:
        grid.pixels[idx] = 1
    grid.rebuild_active_mask()

    scanner = InvaderSparseScanner(grid)
    scanned_coords = list(scanner.iter_active_coords())

    assert len(scanned_coords) == len(interior_indices)
    assert [idx for idx, _, _ in scanned_coords] == sorted(interior_indices)

    assert not grid.check_sentinel_collision()

    grid.pixels[0] = 1
    grid.rebuild_active_mask()
    assert grid.check_sentinel_collision()


def test_4ghost_probes_and_downscale_resistance():
    """Verify Pacman probe calculation and Orange probe retreat avoiding dot clumping."""
    probes = PacmanGhostProbes(corner_pos=(0, 0))

    targets = probes.compute_targets(
        x=10,
        y=10,
        dx=1,
        dy=0,
        red_ref=(9, 10),
        nearest_feature=(10, 12),
    )

    assert isinstance(targets, ProbeTargets)
    assert targets.red == (9, 10)
    assert targets.pink == (14, 10)
    assert targets.blue == (15, 10)
    assert targets.orange == (0, 0)

    targets_far = probes.compute_targets(
        x=10,
        y=10,
        dx=1,
        dy=0,
        red_ref=(9, 10),
        nearest_feature=(15, 15),
    )
    assert targets_far.orange == (15, 15)

    src_dense = ReversiblePixelGrid(4, 4, [1] * 16)
    dst = probes.adaptive_downscale_2x(src_dense)

    assert dst.width == 2
    assert dst.height == 2
    assert dst.active_count < 4


def test_adapter_roundtrip():
    """Verify adapters from_2d_grid, to_2d_grid, from_artifact, to_artifact."""
    grid_2d = [
        [1, 0, 0, 1],
        [0, 2, 2, 0],
        [0, 2, 2, 0],
        [1, 0, 0, 1],
    ]
    grid = ReversiblePixelGrid.from_2d_grid(grid_2d)
    assert grid.width == 4
    assert grid.height == 4
    assert grid.to_2d_grid() == grid_2d

    artifact = grid.to_artifact(palette="C01", mask="test_mask")
    assert artifact["schema"] == "ironmate-pixel-grid/1"
    assert artifact["width"] == 4
    assert artifact["height"] == 4
    assert artifact["pixels"] == grid_2d

    grid_from_art = ReversiblePixelGrid.from_artifact(artifact)
    assert grid_from_art.to_2d_grid() == grid_2d


def test_nes_attribute_table():
    """Verify 2x2 NES subpalette packing and retrieval."""
    attr_table = NesAttributeTable(16, 16)
    attr_table.set_subpalette(0, 0, 2)
    attr_table.set_subpalette(1, 0, 3)

    assert attr_table.get_subpalette(0, 0) == 2
    assert attr_table.get_subpalette(1, 0) == 3


def test_galaxian_wave_engine():
    """Verify integer SINE LUT wave deformation."""
    engine = GalaxianWaveEngine()
    assert engine.sin_lut(0) == 0
    assert engine.sin_lut(64) == 127
    assert engine.cos_lut(0) == 127

    src = ReversiblePixelGrid(8, 8)
    src.pixels[18] = 1  # (2, 2)
    src.rebuild_active_mask()

    dst = engine.apply_wave_distortion(src, frame_step=1, amplitude=2)
    assert dst.active_count == 1


def test_chr_tile_bank_deduplication():
    """Verify 8x8 CHR tile pattern deduplication with H/V flips."""
    bank = ChrTileBank(tile_size=8)

    tile_a = [0] * 64
    tile_a[0] = 1  # Top-left corner

    tile_b = [0] * 64
    tile_b[7] = 1  # Top-right corner (H-flipped tile_a)

    grid1 = ReversiblePixelGrid(8, 8, tile_a)
    grid2 = ReversiblePixelGrid(8, 8, tile_b)

    map1 = bank.add_grid(grid1)
    map2 = bank.add_grid(grid2)

    assert len(bank.patterns) == 1  # Deduplicated into 1 canonical pattern
    assert map1[0][0] == map2[0][0]  # Same pattern ID
    assert map1[0][1] != map2[0][1]  # Differing H-flip flags
