"""Decode the SGetTicketInfo result (type 1) into a mark grid + JSON.

Format confirmed from the vendor demo's Decode Result panel + a captured buffer:
  - type 1 result, Row x Col mark grid (demo showed Row:22, Col:15, Len:44)
  - each row = one big-endian 16-bit word; column c (1-based) = bit (16 - c)
  - Len = Row * 2 data bytes; the SDK buffer (51 B) = small header + these Len bytes

Header layout is finalized once we see the raw 51-byte capture; parse_result()
locates the Len data bytes and decodes the grid. Mapping grid cells -> lottery
numbers is game-specific (lotto.ge 5x5) and comes from the Linux reference.
"""
from __future__ import annotations
import json


def decode_row(word: int, cols: int) -> list[int]:
    """Return 1-based column indices marked in a 16-bit row word."""
    return [c for c in range(1, cols + 1) if word & (1 << (16 - c))]


def decode_grid(data: bytes, rows: int, cols: int) -> list[list[int]]:
    """data = rows*2 bytes (big-endian words) -> per-row marked column lists."""
    grid = []
    for r in range(rows):
        word = (data[2 * r] << 8) | data[2 * r + 1]
        grid.append(decode_row(word, cols))
    return grid


def parse_buffer(raw: bytes) -> dict:
    """Parse the 51-byte SGetTicketInfo buffer (type-1 OMR result).

    Header (7 bytes): type(1), len(1), cols(2 BE), rows(2 BE), reserved(1),
    then `len` data bytes = rows * 2-byte big-endian row bitmasks.
    """
    if len(raw) < 7:
        raise ValueError(f"buffer too short: {len(raw)}")
    rtype = raw[0]
    dlen = raw[1]
    cols = (raw[2] << 8) | raw[3]
    rows = (raw[4] << 8) | raw[5]
    data = raw[7:7 + dlen]
    if len(data) < rows * 2:
        raise ValueError(f"data {len(data)} < rows*2 {rows * 2}")
    grid = decode_grid(data, rows, cols)
    return {"type": rtype, "rows": rows, "cols": cols, "grid": grid}


def to_json(grid: list[list[int]], rows: int, cols: int) -> str:
    marks = [{"row": r + 1, "cols": cs} for r, cs in enumerate(grid) if cs]
    return json.dumps(
        {"type": 1, "rows": rows, "cols": cols, "marks": marks},
        ensure_ascii=False,
    )


def ascii_grid(grid: list[list[int]], cols: int) -> str:
    lines = []
    for r, cs in enumerate(grid):
        cells = "".join("*" if c in cs else "." for c in range(1, cols + 1))
        lines.append(f"{r + 1:2d} |{cells}")
    return "\n".join(lines)


if __name__ == "__main__":
    # Real capture from the live scanner (2026-10-16), validated vs demo screenshot.
    SAMPLE = bytes.fromhex(
        "012c000f001600"                                  # header
        "814a2202000418080208100400008140001200040002"    # rows 1-11
        "001000000000814000000000000000000000000081400000"  # rows 12-22
    )
    assert len(decode_row(0x814A, 15)) == 5
    r = parse_buffer(SAMPLE)
    print(f"type={r['type']} rows={r['rows']} cols={r['cols']}")
    print(ascii_grid(r["grid"], r["cols"]))
    print(to_json(r["grid"], r["rows"], r["cols"]))
