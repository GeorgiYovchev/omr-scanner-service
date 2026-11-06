# 10. The Linux reference implementation

The Linux POS terminals (Ubuntu, GNOME kiosk, see the POS terminal docs) read betslips with a
**different scanner** and publish the JSON this project reproduces. Everything below was observed
on terminal `.248` (`172.16.30.161`) on 2026-10-16; it is the contract to keep matching.

## Hardware and software chain

```
a4ocr / GENLOT reader (Atmel AT91SAM CDC, USB 03eb:6119, /dev/ttyACM1, fw 22011211/V1.107)
   │  libreaderGENLOT.so  (API mirrors the Windows SDK's: ReaderInit/Start/Stop/IsComplete/IsReady/GetTicketInfo/RollBack/GetOriginImage)
   ▼
pixel_scanner_recompiled   (/home/pos/test/pixel_scanner/, C source: main.c util.c communication.c; systemd pixel-scanner.service, Nice=15)
   │  writes decoded TEXT to a named pipe /home/pos/test/node/pipe1
   │  format:  { type: 42 \n block(0):[7,9,17,25,33,34] \n block(1):[...] ... }   (type may be "42" or "42/35")
   ▼
node pipe-websocket-publisher-https.js   (systemd omr-websocket.service; also listens TCP :9000)
   │  parseCustomTextToJSON → broadcast to ALL websocket clients
   ▼
wss://0.0.0.0:8443   cert /home/pos/Printer/ssl/oddstech.net/fullchain.pem (the *.oddstech.net wildcard)
```

Logs: `/home/pos/test/pixel_scanner/log/reader.log` (`_ocr_readticket_img() length:54[...]` per
scan) and `output.log`.

## The JSON contract (what the frontend consumes)

```json
{"type": 42, "blocks": [[7,9,17,25,33,34],[7,10,25,30,38,42],[3,4,5,25,31,37],[7,15,18,27,32,36],[]], "draws": []}
```
* `type`: int (42, 35) — or a string in the odd `"42/35"` case the node parser passes through.
* `blocks`: exactly 5 arrays = boards 1–5, sorted ascending, `[]` when the board is empty.
* `draws`: numbers from the draw-selection blocks — for type 42 the parser takes block indexes > 7,
  for type 35 indexes > 5 (our `to_output` mirrors this: (8, 9) and (6, 7, 8, 9)).
* One message per scan; nothing is sent for unreadable slips; no acknowledgements.

Captured sample (Rosetta ticket, scanned 3× identically on Linux) — the same slip on the Windows
scanner through this service gives the identical message.

## Where the number tables come from

`util.c` contains `scara42` and `scara35` (22×16 ints, `block*100+number`) and detects the type
from the first matrix row: `"1100000010010011"` = 42, `"1100000010101001"` = 35. `make_matrix()`
skips a 7-byte header and expands 22 big-endian words — the same buffer layout the vendor SDK
returns, except that scanner columns are mirrored within each 7-column block
([03-ticket-layouts](03-ticket-layouts.md)). Any new game must get its table in **both** places.

## Open question that affects Windows terminals

How the frontend addresses the socket (`wss://<name>:8443`): check `/etc/hosts` on a Linux
terminal and the frontend configuration. The Windows service must be reachable under a
`*.oddstech.net` name for the certificate to validate in the browser.

## Related terminal facts (summary; full notes live in the POS terminal documentation)

* Other services on the terminals: `printer` (thermal receipts, `wss://:8765`), `lottery-agent`,
  `ssh-tunnel` (reverse tunnel to the management server).
* `pixel_scanner_recompiled` busy-polls (~60 % of one core) — `Nice=15` in its unit file.
* Certificates for both the printer and the scanner publisher are the same wildcard; renew together.
