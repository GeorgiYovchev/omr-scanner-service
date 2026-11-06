r"""Decode a raw SGetTicketInfo buffer (the `[scan] raw ...` hex from omr_service.log) offline.

  py -3.13 tools\decode_raw.py 012c000f0016008164...
Prints the mark grid (SNBC column order), the detected type and the JSON the service would send.
"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "service"))
import genlot_map as g

raw = bytes.fromhex(sys.argv[1].strip())
tbl = g.decode_matrix(raw)
print("header:", raw[:7].hex(), " rows:", raw[4] << 8 | raw[5], " cols:", raw[2] << 8 | raw[3])
print("     " + "".join(str(c % 10) for c in range(16)))
for i, row in enumerate(tbl):
    print(f"r{i:02d}  " + "".join("#" if v else "." for v in row))
print("row0 cols:", sorted(c for c in range(16) if tbl[0][c]), "-> type", g.detect_type(raw) or "unknown (defaults to 42)")
print(json.dumps(g.to_output(raw)))
