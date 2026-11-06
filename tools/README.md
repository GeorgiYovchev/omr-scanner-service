# tools/

* `decode_raw.py <hex>` — decode a `[scan] raw …` buffer from `service/logs/omr_service.log`: grid, row-0 signature, type, JSON.
* `grid_from_sdklog.py <scanprnliblog file> [from] [to]` — rebuild and decode every scan recorded in the SDK's
  device log (scans made by the vendor demo or while the service was down; new ticket types).
* To capture the scan image of a slip, run the service with `OMR_FETCH_IMAGE=1` (or `"fetch_image": true` in
  `config.json`): each scan is saved as `service/logs/scan_<timestamp>.bmp` (8-bit, ~2 MB).
Earlier one-off probe/capture scripts are in `archive/experiments/`.
