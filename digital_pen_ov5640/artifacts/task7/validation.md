# Task 7 validation record

Date: 2026-09-06

## Protocol and automated checks

- Codec: external `microdots 1.0.0`, `anoto_6x6_a4_fixed`.
- Direction mapping regression: `UP=(0,0)`, `LEFT=(1,0)`,
  `RIGHT=(0,1)`, `DOWN=(1,1)`.
- Sliding-window coordinates are normalized with
  `origin=(decoded_x-window_col, decoded_y-window_row)`.
- Missing/low-confidence direction cells support bounded candidate completion;
  section validation runs only once on the bounded winning hypothesis.
- `.venv/Scripts/python.exe -B -m pytest pc/tests -q -p no:cacheprovider`:
  62 passed.
- `.venv/Scripts/python.exe -m ruff check pc tools/patterns --no-cache`:
  passed.
- `tools/patterns/verify_codec.py --samples 1000`: 1000/1000 windows decoded
  correctly.

## Existing Task 6 frame regression

Input: `artifacts/task6/ov5640-aligned-*.pgm` (10 frames).

- Decoded: 10/10.
- Coordinate: all 10 frames decoded to `prototype-a (25,23)`.
- Camera orientation: all frames selected horizontal mirror, rotation 0.
- Confidence range: 0.961408 to 0.964066.
- Supporting-window range: 150 to 157.

## Fresh 100-frame hardware validation

Device status before capture:

```json
{"sensor":"OV5640","width":320,"height":240,"resolution":"320x240","pixel_format":"GRAYSCALE","psram_bytes":8388608,"frame_count":10}
```

Capture command:

```powershell
.venv\Scripts\python.exe pc/apps/capture_frame.py `
  --url http://192.168.1.6 `
  --output artifacts/task7/static/frame.pgm `
  --count 100 --timeout 5
```

`capture_frame.py` verified strictly increasing HTTP frame IDs and a stable
`240x320` image shape while saving all 100 PGM files.

Results:

- Frames decoded: 100/100 (100%).
- Correct coordinate: 100/100 at `prototype-a (25,23)`.
- Incorrect high-confidence results: 0.
- Confidence: minimum 0.956382, maximum 0.964609, mean 0.960400.
- Supporting windows: minimum 130, maximum 157, mean 143.36.
- Coordinate jumps: 0.

The Task 7 static clear-frame requirement of at least 95% correct coordinates
is passed. The current firmware was already flashed and validated on COM16 in
Task 6; Task 7 changes only the PC decoder, so no firmware image was reflashed.
