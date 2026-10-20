"""Public procedural grid presets generated from the existing Python implementation."""
import json
import pixel_grid

SIZES = (16, 23, 31, 32, 64)


def catalog_script():
    catalog = dict(masks=pixel_grid.MASKS, sizes=SIZES, effects=pixel_grid.EFFECTS,
                   palettes=pixel_grid.PALETTES, labels=pixel_grid.PALETTE_LABELS, grids={})
    for mask in pixel_grid.MASKS:
        for effect in pixel_grid.EFFECTS:
            for size in SIZES:
                artifact = pixel_grid.render(mask, 'C01', effect, size)
                catalog['grids'][f'{mask}/{effect}/{size}'] = [
                    ''.join(map(str, row)) for row in artifact['pixels']]
    return ('"use strict";\nconst IronmateCatalog = ' + json.dumps(catalog, separators=(',', ':')) + ';\n').encode()
