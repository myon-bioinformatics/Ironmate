"""Public procedural grid presets generated from the existing Python implementation."""
import json
import pixel_grid

SIZES = (16, 23, 31, 32, 64)


def catalog_script():
    catalog = dict(masks=pixel_grid.MASKS, sizes=SIZES, effects=pixel_grid.EFFECTS,
                   palettes=pixel_grid.PALETTES, labels=pixel_grid.PALETTE_LABELS, grids={})
    row_ids = {}
    for mask in pixel_grid.MASKS:
        for effect in pixel_grid.EFFECTS:
            for size in SIZES:
                artifact = pixel_grid.render(mask, 'C01', effect, size)
                grid = []
                for pixels in artifact['pixels']:
                    row = ''.join(map(str, pixels))
                    grid.append(row_ids.setdefault(row, len(row_ids)))
                catalog['grids'][f'{mask}/{effect}/{size}'] = grid
    compact = (',', ':')
    return (
        '"use strict";\nconst IronmateCatalog = (() => {\n'
        f'  const rows = {json.dumps(list(row_ids), separators=compact)};\n'
        f'  const catalog = {json.dumps(catalog, separators=compact)};\n'
        '  for (const key of Object.keys(catalog.grids)) {\n'
        '    catalog.grids[key] = catalog.grids[key].map(index => rows[index]);\n'
        '  }\n  return catalog;\n})();\n'
    ).encode()
