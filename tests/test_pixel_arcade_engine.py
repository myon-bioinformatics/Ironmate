import pytest
from pixel_arcade_engine import (
    ReversiblePixelGrid,
    InvaderSparseScanner,
    PacmanGhostProbes,
    ProbeTargets,
)


def test_reversibility_and_rollback():
    """Verify that swap operations and rollback restore pixels and active mask completely."""
    # 8x8 grid with some non-zero pixels
    grid = ReversiblePixelGrid(8, 8)
    grid.pixels[10] = 1
    grid.pixels[25] = 2
    grid.pixels[40] = 3
    grid.rebuild_active_mask()

    initial_pixels = list(grid.pixels)
    initial_mask = grid.active_mask

    # Perform multiple pixel swaps
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

    # Set 5 active pixels strictly in the interior (not touching sentinel border)
    interior_indices = [18, 19, 27, 35, 42]
    for idx in interior_indices:
        grid.pixels[idx] = 1
    grid.rebuild_active_mask()

    scanner = InvaderSparseScanner(grid)
    scanned_coords = list(scanner.iter_active_coords())

    # Ensure iteration count is strictly N (5 iterations)
    assert len(scanned_coords) == len(interior_indices)
    assert [idx for idx, _, _ in scanned_coords] == sorted(interior_indices)

    # O(1) Sentinel collision check should be False when no active pixels touch border
    assert not grid.check_sentinel_collision()

    # Move/place a pixel on sentinel border (e.g. index 0)
    grid.pixels[0] = 1
    grid.rebuild_active_mask()
    assert grid.check_sentinel_collision()


def test_4ghost_probes_and_downscale_resistance():
    """Verify Pacman probe calculation and Orange probe retreat avoiding dot clumping."""
    probes = PacmanGhostProbes(corner_pos=(0, 0))

    # Test probe calculation with bit shift arithmetic
    targets = probes.compute_targets(
        x=10,
        y=10,
        dx=1,
        dy=0,
        red_ref=(9, 10),
        nearest_feature=(10, 12),  # Manhattan dist = 2 < 8
    )

    assert isinstance(targets, ProbeTargets)
    assert targets.red == (9, 10)
    assert targets.pink == (14, 10)  # x + (1 << 2) = 14
    assert targets.blue == (15, 10)  # (pivot_x << 1) - rx = (12 * 2) - 9 = 15
    # Manhattan dist is 2 (< 8), so Orange retreats to corner_pos (0, 0)
    assert targets.orange == (0, 0)

    # Test distance >= 8 keeps nearest feature
    targets_far = probes.compute_targets(
        x=10,
        y=10,
        dx=1,
        dy=0,
        red_ref=(9, 10),
        nearest_feature=(15, 15),  # Manhattan dist = 10 >= 8
    )
    assert targets_far.orange == (15, 15)

    # Dense grid 4x4 -> 2x2 downscaling test
    # A dense 4x4 block filled with dots
    src_dense = ReversiblePixelGrid(4, 4, [1] * 16)
    dst = probes.adaptive_downscale_2x(src_dense)

    assert dst.width == 2
    assert dst.height == 2

    # Naive downscale would keep all 4 cells (2x2 grid filled).
    # With Orange probe corner retreat (dist < 8) and checkerboard thinning in dense blocks (>= 3 active),
    # some dense cells are thinned (set to 0) to avoid dot clumping / blob merging.
    active_dst_count = dst.active_count
    assert active_dst_count < 4  # Clumping avoided by thinning dense regions


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
