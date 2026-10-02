# Task 6 validation record

Date: 2026-09-06

## Automated checks

- `.venv/Scripts/python.exe -m pytest pc/tests -q`: 43 passed.
- `.venv/Scripts/python.exe -m ruff check pc tools/patterns`: passed.
- The synthetic lattice test applies 24-degree rotation, unequal scale,
  projective distortion, 0.2 px Gaussian noise, 12% missing dots, and 18
  random outliers. All retained real dots recover their original row/column
  indices; inlier ratio is above 85% and offset-corrected RMS is below 0.5 px.

## Generator truth comparison

Source image: `artifacts/task5/generator-prototype-a.png`.

Truth matrix:
`artifacts/patterns/prototype-a/prototype-a_55x55_s10_2.matrix.json`.

- Detected/inlier dots: 3025/3025.
- Recovered matrix: 55 x 55, no missing cells.
- Median spacing: 20.8336 px.
- Estimated direction offset: 0.3000 grid units.
- Offset-corrected lattice RMS: 0.0630 px.
- Direction accuracy: 3025/3025 (100%).

## Printer scan truth comparison

Source image: `artifacts/task5/printer-scan.png`, printed from the same
manifest above.

- Detected/inlier dots: 3025/3025.
- Recovered matrix: 55 x 55, no missing cells.
- Median spacing: 19.9842 px.
- Estimated direction offset: 0.3000 grid units.
- Offset-corrected lattice RMS: 0.0737 px.
- Direction accuracy: 3025/3025 (100%).

## OV5640 hardware regression

The current firmware built successfully and was flashed to COM16. Boot logs
confirmed an ESP32-S3 with 8 MB PSRAM, OV5640 PID `0x5640`, QVGA grayscale
capture, STA connection, and the HTTP frame service at `192.168.1.6`.
`GET /status` returned 320 x 240 GRAYSCALE, 8388608 PSRAM bytes.

After the camera was positioned square to the known `prototype-a` print, ten
fresh frames were saved as `artifacts/task6/ov5640-aligned-*.pgm`. Each frame
was fitted independently and matched against the retained 55 x 55 truth
matrix. Matching enumerated crop translations and the eight possible image
orientations, transforming both matrix positions and direction labels. Every
frame selected the horizontal-mirror transform, consistent with the current
camera orientation.

| Frame | Detected | Inlier directions | RMS (px) | Direction accuracy |
|---:|---:|---:|---:|---:|
| 1 | 285 | 243 | 0.3843 | 100.000% |
| 2 | 288 | 250 | 0.3970 | 100.000% |
| 3 | 289 | 252 | 0.3966 | 100.000% |
| 4 | 287 | 245 | 0.3894 | 100.000% |
| 5 | 288 | 250 | 0.3753 | 100.000% |
| 6 | 288 | 246 | 0.3829 | 100.000% |
| 7 | 289 | 243 | 0.3630 | 100.000% |
| 8 | 288 | 245 | 0.3654 | 100.000% |
| 9 | 288 | 246 | 0.3757 | 100.000% |
| 10 | 291 | 251 | 0.3911 | 99.602% |

- Mean direction accuracy: 99.960%.
- Minimum per-frame direction accuracy: 99.602%.
- Frames meeting the at-least-99% requirement: 10/10.
- RMS range: 0.3630 to 0.3970 px; all frames meet the below-0.5 px target.

The OV5640 direction-accuracy and lattice-RMS exit gates are therefore passed
for this aligned, clear capture batch.
