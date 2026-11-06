r"""Rebuild SGetTicketInfo buffers from the SDK's own device log and decode them.

The device layer (sdk\log\scanprnliblog_*.log, GBK encoded) logs every OMR decode as
  DecodeOMR succeed, ... pszOMRDecodeDest=100000010010011,000000100000001,...   (22 rows x 15 chars)
This maps those strings back to the 22 x 16-bit row words the SDK hands to SGetTicketInfo
(pos 0..6 -> col 7-pos, pos 7 -> col 0, pos 8..14 -> col 23-pos; column 8 is never set) and runs
the mapper on each. Use it to recover scans that happened while the service was not running,
or to get the row-0 signature of a NEW ticket type.

  py -3.13 tools\grid_from_sdklog.py sdk\log\scanprnliblog_20261016_000.log [HH:MM:SS-from] [HH:MM:SS-to]
"""
import json, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "service"))
import genlot_map as g

HEADER = bytes([1, 0x2c, 0, 0x0f, 0, 0x16, 0])


def word(s15: str) -> int:
    w = 0
    for p, ch in enumerate(s15):
        if ch == "1":
            c = 7 - p if p <= 6 else (0 if p == 7 else 23 - p)
            w |= 1 << (15 - c)
    return w


def buffer_from_rows(rows: list[str]) -> bytes:
    return HEADER + b"".join(word(r).to_bytes(2, "big") for r in rows[:22])


def main():
    path = sys.argv[1]
    t_from = sys.argv[2] if len(sys.argv) > 2 else "00:00:00"
    t_to = sys.argv[3] if len(sys.argv) > 3 else "23:59:59"
    pat = re.compile(r"^(\S+) (\S+) .*pszOMRDecodeDest=([01,]+)")
    with open(path, encoding="gbk", errors="replace") as f:
        for line in f:
            m = pat.match(line)
            if not m:
                continue
            day, tm, grid = m.groups()
            if not (t_from <= tm[:8] <= t_to):
                continue
            rows = grid.split(",")
            if len(rows) < 22 or any(len(r) != 15 for r in rows[:22]):
                print(day, tm, "skipped (not a 22x15 grid)")
                continue
            raw = buffer_from_rows(rows)
            row0 = sorted(c for c in range(16) if g.decode_matrix(raw)[0][c])
            print(f"{day} {tm}  row0 decomr={rows[0]} -> SNBC cols {row0} type={g.detect_type(raw) or 'unknown'}")
            print("   raw", raw.hex())
            print("   ", json.dumps(g.to_output(raw)))


if __name__ == "__main__":
    main()
