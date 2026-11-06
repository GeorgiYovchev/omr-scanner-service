"""Map an SNBC SGetTicketInfo buffer -> lottery numbers, using the GENLOT
scara tables recovered from the Linux pixel_scanner util.c source.

Decode matches util.c make_matrix(): 7-byte header skipped, then 22 rows x 16
bits (44 bytes); row word = big-endian; col c (0..15) = bit (15-c).
Cell value = scara[row][col] = block*100 + number.
"""
from __future__ import annotations

# --- tables transcribed verbatim from util.c -------------------------------
SCARA42 = [
 [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
 [0,101,102,103,104,105,106,107,0,201,202,203,204,205,206,207],
 [0,108,109,110,111,112,113,114,0,208,209,210,211,212,213,214],
 [0,115,116,117,118,119,120,121,0,215,216,217,218,219,220,221],
 [0,122,123,124,125,126,127,128,0,222,223,224,225,226,227,228],
 [0,129,130,131,132,133,134,135,0,229,230,231,232,233,234,235],
 [0,136,137,138,139,140,141,142,0,236,237,238,239,240,241,242],
 [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
 [0,301,302,303,304,305,306,307,0,401,402,403,404,405,406,407],
 [0,308,309,310,311,312,313,314,0,408,409,410,411,412,413,414],
 [0,315,316,317,318,319,320,321,0,415,416,417,418,419,420,421],
 [0,322,323,324,325,326,327,328,0,422,423,424,425,426,427,428],
 [0,329,330,331,332,333,334,335,0,429,430,431,432,433,434,435],
 [0,336,337,338,339,340,341,342,0,436,437,438,439,440,441,442],
 [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
 [0,501,502,503,504,505,506,507,0,0,0,0,0,0,0,0],
 [0,508,509,510,511,512,513,514,0,0,0,601,602,603,604,605],
 [0,515,516,517,518,519,520,521,0,0,0,701,702,703,704,705],
 [0,522,523,524,525,526,527,528,0,0,0,0,0,0,0,0],
 [0,529,530,531,532,533,534,535,0,0,0,0,802,803,804,805],
 [0,536,537,538,539,540,541,542,0,0,0,906,907,908,909,910],
 [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
]
SCARA35 = [
 [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
 [0,0,101,102,103,104,105,106,0,0,201,202,203,204,205,206],
 [0,0,107,108,109,110,111,112,0,0,207,208,209,210,211,212],
 [0,0,113,114,115,116,117,118,0,0,213,214,215,216,217,218],
 [0,0,119,120,121,122,123,124,0,0,219,220,221,222,223,224],
 [0,0,125,126,127,128,129,130,0,0,225,226,227,228,229,230],
 [0,0,131,132,133,134,135,0,0,0,231,232,233,234,235,0],
 [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
 [0,0,301,302,303,304,305,306,0,0,401,402,403,404,405,406],
 [0,0,307,308,309,310,311,312,0,0,407,408,409,410,411,412],
 [0,0,313,314,315,316,317,318,0,0,413,414,415,416,417,418],
 [0,0,319,320,321,322,323,324,0,0,419,420,421,422,423,424],
 [0,0,325,326,327,328,329,330,0,0,425,426,427,428,429,430],
 [0,0,331,332,333,334,335,0,0,0,431,432,433,434,435,0],
 [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
 [0,0,501,502,503,504,505,506,0,0,0,0,0,0,0,0],
 [0,0,507,508,509,510,511,512,0,0,0,0,0,0,0,0],
 [0,0,513,514,515,516,517,518,0,0,602,603,604,605,606,0],
 [0,0,519,520,521,522,523,524,0,0,707,708,709,710,0,0],
 [0,0,525,526,527,528,529,530,0,0,0,0,0,0,0,0],
 [0,0,531,532,533,534,535,0,0,0,0,0,0,0,0,0],
 [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
]

ROWS, COLS = 22, 16


def decode_matrix(raw: bytes) -> list[list[int]]:
    """util.c make_matrix: skip 7-byte header, 22x16 bits, col = 15-bit."""
    data = raw[7:7 + 44]
    tbl = [[0] * COLS for _ in range(ROWS)]
    for i in range(0, 44, 2):
        n = (data[i] << 8) | data[i + 1]           # big-endian word
        for j in range(15, -1, -1):
            if (n >> j) & 1:
                tbl[i // 2][15 - j] = 1
    return tbl


def col_transform(c: int, mode: str) -> int:
    if mode == "identity":
        return c
    if mode == "blockmirror":                      # mirror within each 7-col block
        if 1 <= c <= 7:
            return 8 - c
        if 9 <= c <= 15:
            return 24 - c
        return c
    if mode == "reverse":
        return 15 - c
    return c


def extract(raw: bytes, scara, mode: str) -> dict[int, list[int]]:
    tbl = decode_matrix(raw)
    blocks: dict[int, list[int]] = {}
    for i in range(ROWS):
        for c in range(COLS):
            if tbl[i][c]:
                val = scara[i][col_transform(c, mode)]
                if val:
                    blocks.setdefault(val // 100, []).append(val % 100)
    for b in blocks:
        blocks[b].sort()
    return blocks


# row0 (matrix row 0) signatures per ticket type, in set-of-columns form (SNBC order,
# i.e. before blockmirror). GENLOT util.c: 42 = "1100000010010011", 35 = "1100000010101001";
# mirrored into SNBC order (col 8 is a separator the SNBC grid never sets) that gives
# 42 = word 0x8164 cols {0,7,9,10,13}, 35 = word 0x814A cols {0,7,9,12,14} - both seen live.
TYPE_SIGNATURES = {
    frozenset({0, 7, 9, 10, 13}): 42,
    frozenset({0, 7, 9, 12, 14}): 35,
}


def detect_type(raw: bytes) -> int | None:
    tbl = decode_matrix(raw)
    row0 = frozenset(c for c in range(COLS) if tbl[0][c])
    return TYPE_SIGNATURES.get(row0)


def to_output(raw: bytes) -> dict:
    """Produce the exact JSON the Linux publisher emits: {type, blocks[5], draws}."""
    t = detect_type(raw)
    scara = SCARA35 if t == 35 else SCARA42   # default 42 until a 35 signature is known
    t = t or 42
    blk = extract(raw, scara, "blockmirror")  # {blocknum: [values]}
    blocks = [sorted(blk.get(i, [])) for i in range(1, 6)]   # boards 1-5
    draws: list[int] = []
    draw_src = (8, 9) if t == 42 else (6, 7, 8, 9)           # per publisher rules
    for i in draw_src:
        draws.extend(sorted(blk.get(i, [])))
    return {"type": t, "blocks": blocks, "draws": draws}


if __name__ == "__main__":
    import json
    t1 = bytes.fromhex("012c000f001600816440400204040008083002004481401c400000000908200408020181400000000000000000000000008140")
    expected = {"type": 42,
                "blocks": [[7,9,17,25,33,34],[7,10,25,30,38,42],[3,4,5,25,31,37],[7,15,18,27,32,36],[]],
                "draws": []}
    out = to_output(t1)
    print("output:", json.dumps(out))
    print("matches Linux capture:", out == expected)
    print()
    known = {1:[7,9,17,25,33,34], 2:[7,10,25,30,38,42], 3:[3,4,5,25,31,37], 4:[7,15,18,27,32,36]}
    for mode in ("identity", "blockmirror", "reverse"):
        got = extract(t1, SCARA42, mode)
        got = {b: sorted(v) for b, v in got.items()}
        ok = all(got.get(b) == sorted(v) for b, v in known.items())
        print(f"[{mode}] match={ok}  {got}")
    print("known:", known)
