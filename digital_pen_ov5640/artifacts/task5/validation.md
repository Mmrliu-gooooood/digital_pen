# Task 5 validation record

Date: 2026-09-06

## Automated checks

- `python -m pytest pc/tests/vision -q`: 16 passed.
- `.venv/Scripts/python.exe -m pytest pc/tests -q`: 32 passed.
- `python -m ruff check pc tools/patterns`: passed.
- Synthetic anti-aliased dots include a brightness gradient and Gaussian blur;
  every matched centroid is required by the test to be within 0.25 px.

## Generator render

Source: `artifacts/patterns/prototype-a/prototype-a_55x55_s10_2.pdf`.

The first page was rendered at 150 DPI and inspected with Otsu thresholding,
area 4..40 px, minimum aspect ratio 0.6, minimum circularity 0.45, and
morphology disabled.

- Expected dots: 55 x 55 = 3025.
- Accepted dots: 3025.
- Rejected candidates: 0.
- Detection rate against Generator truth: 100%.

## Live OV5640 diagnostic

The ESP32-S3 firmware was flashed on COM16. Boot logs confirmed 8 MB PSRAM,
OV5640 PID `0x5640`, QVGA grayscale capture, and the HTTP frame service. A new
320 x 240 PGM frame was then captured from the running device.

Diagnostic settings: adaptive threshold, block size 31, C=7, area
0.5..120 px, minimum aspect ratio 0.3, minimum circularity 0.2, morphology
disabled.

- Accepted dot candidates: 281.
- Rejected/suspicious components: 15 (13 zero-area/small border fragments,
  one elongated component, and one low-circularity component).

This live frame has no independently labelled per-dot ground truth, so these
counts are diagnostic evidence and are not reported as a measured detection
rate.

## Printer scan

Source: `D:/ESP32_project/digital_pen/dot_picture/打印纸的扫描仪扫描图png.png`
(copied to `artifacts/task5/printer-scan.png` because OpenCV on Windows could
not open the Unicode source path directly).

Diagnostic settings: Otsu threshold, area 3..50 px, minimum aspect ratio
0.55, minimum circularity 0.35, morphology disabled.

- Expected dots: 55 x 55 = 3025.
- Accepted dots: 3025.
- Rejected candidates: 0.
- Count-based detection rate: 100%.

The file named `打印纸的扫描仪扫描图pdf.pdf` is byte-for-byte identical to the
Generator PDF, so the PNG is the independent raster scan used for this class.

## Phone photo

Source: `D:/ESP32_project/digital_pen/dot_picture/phone_pic_dot.jpg`,
4032 x 3024.

Diagnostic settings: adaptive threshold, block size 101, C=9, area
40..300 px, minimum aspect ratio 0.45, minimum circularity 0.35, 3 x 3
morphology with one iteration.

- Expected dots: 55 x 55 = 3025.
- Accepted dots: 3025.
- Rejected candidates: 528 background/JPEG-noise components.
- Count-based detection rate: 100%; visual review places accepted centroids
  on the printed dot region.

## Four-class status

Generator render, printer scan, phone photo, and live OV5640 frame have now
all been exercised. Generator, scan, and phone inputs have 55 x 55 count
truth. A strict per-dot OV5640 true-positive rate still requires spatial truth
matching (manual labels or the Task 6 lattice/homography), rather than relying
on the accepted-component count alone.
