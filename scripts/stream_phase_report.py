#!/usr/bin/env python3
"""Stdlib RAW/P5 patches, fitted CSV range spins, and verified bit ladders.

Pixel buffers are borrowed; patch descriptors and CSV fields allocate. CSV uses
seekable two-pass calibration. Ladders are model counterfactuals, not causality.
"""
from __future__ import annotations
import argparse
from collections import deque
import csv
import html
import json
from pathlib import Path
import re

try:
    from .littlebit_jev_5way_survey import CalibratedTernaryPatch, FiveWaySurveyEngine
except ImportError:
    from littlebit_jev_5way_survey import CalibratedTernaryPatch, FiveWaySurveyEngine


def image_patches(buffer, width, height, channels=1):
    """Yield row-major 8x8 descriptors, rejecting incomplete edge patches."""
    if channels not in (1, 3) or width <= 0 or height <= 0 or width & 7 or height & 7:
        raise ValueError('positive multiples of 8 and channels 1 or 3 required')
    mv = memoryview(buffer).cast('B')
    stride = width if channels == 1 else width + (width << 1)
    if len(mv) != stride * height:
        raise ValueError('pixel byte count does not match dimensions')
    for y in range(0, height, 8):
        for x in range(0, width, 8):
            rows, cols = [], [0 for _ in range(8)]
            for dy in range(8):
                total = 0
                offset = stride * (y + dy) + (x if channels == 1 else x + (x << 1))
                for dx in range(8):
                    value = mv[offset]
                    if channels == 3:
                        value = (value + (mv[offset + 1] << 1) + mv[offset + 2]) >> 2
                    offset += channels
                    total += value
                    cols[dx] += value
                rows.append(total >> 3)
            yield CalibratedTernaryPatch(rows, [v >> 3 for v in cols])


def pgm_view(buffer):
    """Borrow an 8-bit binary P5 payload; consume exactly one header separator.

    CRLF counts as one separator. Never strip payload whitespace or '#'.
    """
    mv = memoryview(buffer).cast('B')
    i, tokens = 0, []
    whitespace = b' \t\r\n\v\f'
    while len(tokens) < 4:
        while i < len(mv) and mv[i] in whitespace:
            i += 1
        if i < len(mv) and mv[i] == 35:
            while i < len(mv) and mv[i] not in (10, 13):
                i += 1
            continue
        start = i
        while i < len(mv) and mv[i] not in whitespace and mv[i] != 35:
            i += 1
        if i == start:
            raise ValueError('truncated PGM header')
        tokens.append(bytes(mv[start:i]))
    if tokens[0] != b'P5' or tokens[3] != b'255':
        raise ValueError('only binary P5 maxval 255 supported')
    if i >= len(mv) or mv[i] not in whitespace:
        raise ValueError('missing PGM raster separator')
    i += 2 if mv[i] == 13 and i + 1 < len(mv) and mv[i + 1] == 10 else 1
    return mv[i:], int(tokens[1]), int(tokens[2])


def fixed100(text):
    """Exact hundredths, rejecting precision loss, missing values and exponents."""
    text = text.strip()
    if not re.fullmatch(r'[+-]?[0-9]+(?:\.[0-9]{1,2})?', text):
        raise ValueError(f'invalid hundredths: {text!r}')
    negative = text.startswith('-')
    whole, _, fraction = text.lstrip('+-').partition('.')
    n = int(whole)
    value = (n << 6) + (n << 5) + (n << 2) + int(fraction.ljust(2, '0'))
    return -value if negative else value


def csv_spins(stream, id_col, columns, allow_missing=False):
    """Two passes, O(columns) calibration storage; yields separate spin masks.

    Thresholds partition numeric range, not population quantiles. Constant
    columns stay neutral. Input must remain unchanged between the two passes.
    """
    if not columns or len(set(columns)) != len(columns):
        raise ValueError('unique numeric columns required')
    start = stream.tell()
    def rows():
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not set([id_col, *columns]) <= set(reader.fieldnames):
            raise ValueError('missing required CSV columns')
        if len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError('duplicate CSV headers')
        for row in reader:
            if None in row or any(row.get(c) is None for c in [id_col, *columns]):
                raise ValueError('malformed CSV row')
            yield row, [None if allow_missing and row[c].strip() in ('', 'NULL') else fixed100(row[c]) for c in columns]
    bounds = [None for _ in columns]
    for _, values in rows():
        for i, value in enumerate(values):
            if value is None:
                continue
            old = bounds[i]
            bounds[i] = (value, value) if old is None else (min(old[0], value), max(old[1], value))
    stream.seek(start)
    for row, values in rows():
        pos = neg = observed = 0
        for i, value in enumerate(values):
            if value is None:
                continue
            observed |= 3 << (i << 1)
            lo, hi = bounds[i]
            if lo == hi:
                continue
            quarter = (hi - lo) >> 2
            if value >= hi - quarter:
                pos |= 1 << i
            elif value <= lo + quarter:
                neg |= 1 << i
        yield dict(id=row[id_col], pos_mask=pos, neg_mask=neg,
                   spin_board=interleave(pos, neg, len(columns)), obs_mask=observed)


def interleave(pos, neg, count):
    board = 0
    for i in range(count):
        board |= ((pos >> i) & 1) << (i << 1)
        board |= ((neg >> i) & 1) << ((i << 1) + 1)
    return board


def shortest_ladder(board, target, choose, bits, max_distance=3, max_states=10000, valid=lambda b: True):
    """BFS certifies shortest winner-changing path in a bounded valid bit domain.

    choose must be deterministic. Exhaustion within distance is distinguished
    from resource cutoff. Topology is not silently changed by flipping features.
    """
    if board < 0 or not 0 <= bits <= 20 or board >> bits or max_distance < 0 or max_states < 1 or not valid(board):
        raise ValueError('invalid search domain')
    queue, seen = deque([(board, [board])]), {board}
    while queue:
        current, path = queue.popleft()
        if choose(current) == target:
            return dict(status='found', path=path, distance=len(path)-1)
        if len(path)-1 >= max_distance:
            continue
        for i in range(bits):
            nxt = current ^ (1 << i)
            if nxt in seen or not valid(nxt):
                continue
            if len(seen) >= max_states:
                return dict(status='resource_limit', path=None)
            seen.add(nxt)
            queue.append((nxt, path + [nxt]))
    return dict(status='not_found_within_bound', path=None)


def render_ladder(path, choose, names):
    """Render verified consecutive one-bit states with escaped user labels."""
    lines, ascii_lines = ['```mermaid', 'flowchart TD'], ['```text']
    for i, board in enumerate(path):
        label = html.escape(str(choose(board)), quote=True).replace('\n', ' ').replace('\r', ' ').replace('`', '&#96;')
        lines.append(f'    N{i}["{label}: {board:#x}"]')
        if i:
            delta = board ^ path[i-1]
            if delta.bit_count() != 1:
                raise ValueError('ladder edges must flip exactly one bit')
            bit = delta.bit_length()-1
            action = ('+' if board & delta else '-') + str(names.get(bit, f'bit_{bit}'))
            safe = html.escape(action, quote=True).replace('\n', ' ').replace('\r', ' ').replace('`', '&#96;')
            lines.append(f'    N{i-1} -->|"{safe}"| N{i}')
            ascii_lines.append(f'{path[i-1]:#x} -- {action.replace(chr(10), " ").replace(chr(13), " ").replace("`", "")} --> {board:#x}')
    return '\n'.join(lines + ['```', ''] + ascii_lines + ['```', ''])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--csv', type=Path)
    source.add_argument('--image', type=Path)
    parser.add_argument('--id-col', default='team_season')
    parser.add_argument('--columns', nargs='+')
    parser.add_argument('--width', type=int)
    parser.add_argument('--height', type=int)
    parser.add_argument('--channels', type=int, default=1)
    parser.add_argument('--ladder-spec', type=Path, help='JSON ordered class predicates and target')
    parser.add_argument('--allow-missing', action='store_true', help='treat empty/NULL CSV cells as unknown')
    parser.add_argument('--observable-spec', type=Path, help='JSON width/classes for masked candidate routing')
    args = parser.parse_args(argv)
    try:
        if args.csv:
            if not args.columns:
                parser.error('--columns required with --csv')
            engine = None
            if args.observable_spec:
                try:
                    from .observable_choice import ObservableChoice, Prototype
                except ImportError:
                    from observable_choice import ObservableChoice, Prototype
                spec = json.loads(args.observable_spec.read_text(encoding='utf-8'))
                engine = ObservableChoice([Prototype(c['name'], c.get('must_and', 0),
                                          c.get('forbid_not', 0), tuple(c.get('or_masks', [])))
                                          for c in spec['classes']], len(args.columns) << 1)
            if args.ladder_spec:
                ladder_spec = json.loads(args.ladder_spec.read_text(encoding='utf-8'))
                def choose(board):
                    for cls in ladder_spec['classes']:
                        required = cls.get('must_and', 0)
                        if (board & required == required and not board & cls.get('forbid_not', 0)
                                and all(board & mask for mask in cls.get('or_masks', []))):
                            return cls['name']
                    return 'Unknown'
                def valid(board):
                    return all((board >> (i << 1)) & 3 != 3 for i in range(len(args.columns)))
                names = {i << 1: c + '_High' for i, c in enumerate(args.columns)}
                names.update({(i << 1) + 1: c + '_Low' for i, c in enumerate(args.columns)})
            with args.csv.open(encoding='utf-8-sig', newline='') as stream:
                for row in csv_spins(stream, args.id_col, args.columns, args.allow_missing):
                    print(json.dumps(row, ensure_ascii=False))
                    if engine is not None:
                        print(json.dumps(engine.query(row['spin_board'], row['obs_mask'])))
                    if args.ladder_spec:
                        if row['obs_mask'] != (1 << (len(args.columns) << 1))-1:
                            parser.error('ladder requires complete observations')
                        result = shortest_ladder(row['spin_board'], ladder_spec['target'], choose,
                                                 len(args.columns) << 1, valid=valid)
                        print(json.dumps(result))
                        if result['path'] is not None:
                            print(render_ladder(result['path'], choose, names))
        else:
            buffer = args.image.read_bytes()
            if buffer.startswith(b'P5'):
                buffer, width, height = pgm_view(buffer)
                channels = 1
            else:
                width, height, channels = args.width, args.height, args.channels
                if width is None or height is None:
                    parser.error('RAW requires --width and --height')
            patches = list(image_patches(buffer, width, height, channels))
            result = FiveWaySurveyEngine(patches, width >> 3, height >> 3).execute_5way_survey()
            print(json.dumps({k: result[k] for k in ('bitboard', 'candidate_count', 'total_patches', 'euler_stats')}))
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
