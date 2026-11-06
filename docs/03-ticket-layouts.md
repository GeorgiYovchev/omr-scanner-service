# 3. Ticket layouts — from mark grid to lottery numbers

All current lotto.ge betslips share one print template: a left **timing track**, registration
marks, and a **22-row × 15-column** mark grid organised as two 7-column blocks (columns 1–7 and
9–15; column 0 is the timing mark, column 8 the separator, which the SNBC decoder never sets).
The scanner returns which cells are filled; `service/genlot_map.py` turns that into numbers.

## Step 1 — decode the words

`decode_matrix(raw)` skips the 7-byte header and expands 22 big-endian words into a 22×16 boolean
table, column `c` ← bit `15-c`. This is exactly `make_matrix()` from the Linux reader's `util.c`.

## Step 2 — un-mirror the columns (`blockmirror`)

The SNBC scanner reports columns **mirrored within each 7-column block** compared with the Linux
GENLOT/a4ocr reader whose tables we reuse:

```
SNBC column c →  8 - c   for c in 1..7
                 24 - c  for c in 9..15
                 c       for 0 and 8
```

Found empirically on 2026-10-16: with this transform the Rosetta test ticket decodes to exactly the
24 numbers the Linux terminal reported for it.

## Step 3 — look up the layout table

`SCARA42` and `SCARA35` (transcribed verbatim from `util.c` of `pixel_scanner` on the Linux
terminals) are 22×16 tables, cell value = `block*100 + number`:

* **type 42** (6-from-42): blocks 1–5 = boards (rows 1–6 → board 1 left / board 2 right, rows 8–13
  → boards 3/4, rows 15–20 → board 5 left), 6 columns × 7 rows per board = numbers 1…42; blocks
  6–9 in the lower-right area = draws/extra options (only 8 and 9 are published as `draws`).
* **type 35** (5-from-35): same frame, boards use 6 columns starting one column later, numbers 1…35
  (last row has 5), blocks 6–9 → `draws` (all four published).

Rows 0, 7, 14, 21 are frame rows (type markers + registration); they carry no picks.

## Step 4 — detect the game type from row 0

Row 0 contains fixed marker cells per template. In SNBC column order (before un-mirroring):

| type | row-0 columns | word | GENLOT string (`util.c`) |
|---|---|---|---|
| 42 | {0, 7, 9, 10, 13} | `0x8164` | `1100000010010011` |
| 35 | {0, 7, 9, 12, 14} | `0x814A` | `1100000010101001` |

`TYPE_SIGNATURES` in `genlot_map.py`. An unknown signature falls back to 42 (and is visible in the
log as the raw hex — see below).

## Output rules (`to_output`)

```json
{"type": 42, "blocks": [b1, b2, b3, b4, b5], "draws": [...]}
```
Boards sorted ascending, `[]` when empty; `draws` = blocks (8, 9) for type 42, (6, 7, 8, 9) for 35.
This matches `parseCustomTextToJSON` in the Linux publisher (`pipe-websocket-publisher-https.js`)
byte for byte — verified against a live capture.

## decomr string ↔ SNBC word

The device layer logs every decode as a 22×15 string (`pszOMRDecodeDest=100000010010011,…`).
Position `p` of that string maps to SNBC column: `p 0..6 → 7-p`, `p 7 → 0`, `p 8..14 → 23-p`.
`tools/grid_from_sdklog.py` applies this so scans can be reconstructed from the SDK log alone
(e.g. scans made while the service was not running, or by the vendor demo).

## Reproducing a decode offline

```
py -3.13 tools\decode_raw.py 012c000f0016008164...      # the "[scan] raw" hex from omr_service.log
py -3.13 tools\grid_from_sdklog.py sdk\log\scanprnliblog_20261016_000.log 15:50:40 15:50:50
```

Both print the grid, the row-0 signature, the detected type and the JSON.

## Adding a new game / ticket type

Three tiers, cheapest first:

1. **Same template, new arrangement of boards/numbers** (different board count, picks per board,
   number range ≤ what fits in 6 columns × 6–7 rows): scan one slip, read its row-0 signature from
   the log (`[scan] raw` or the tools above), add `frozenset({…}): <type>` to `TYPE_SIGNATURES`, add a
   `SCARA<type>` table (cell = block*100+number) and the `draws` rule in `to_output`. Validate with a
   slip whose marks you know. No scanner-side change.
2. **Different physical grid** (rows/columns/pitch): also needs a new `{…}` format block in
   `sdk/lib/FormatFile.txt` (and possibly `DecodeCfg.ini`); the slip must be designed with the
   scanner's constraints (timing track, registration marks, mark size). The service already reads
   rows/cols from the buffer header, so `decode_matrix` and the tables just change shape.
3. **Barcode / QR tickets**: the SDK decodes PDF417/QR/1D on the same pass (enable in
   `LScannerConfig.ini`); the result arrives with a different `type` byte and is text, not a grid —
   a new, small code path.

Whatever the tier, the Linux terminals need the same tables in their `util.c` to stay consistent.

## Known sensitivity quirk

One test ticket ("Rosetta", 6/42) has a borderline cell (row 2, scara 206 → board 2 "6") that reads
as filled on some scans and not others. Rescans of the same ticket are otherwise identical. Tune
`[OMR] threshold` / `threshold_mark` / `mark_block_ratio` in `sdk/lib/DecodeCfg.ini` (or
`SAdjustSensibility`) with that ticket as the test case; the Linux a4ocr reader reads it cleanly.
