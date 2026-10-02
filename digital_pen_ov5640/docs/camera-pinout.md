# OV5640 与 ESP32-S3 N16R8 接线

本文记录点阵笔原型的实际 OV5640 模块接线。GPIO 来自实际接线，不套用其他 ESP32-S3 Camera 开发板的默认映射。

| OV5640 模块信号 | ESP32-S3 | `camera_config_t` 字段 | 方向 |
|---|---:|---|---|
| PWDN | GPIO38 | `pin_pwdn` | ESP → Camera |
| RESET | GPIO15 | `pin_reset` | ESP → Camera |
| XCLK/MCLK | 不连接（`-1`） | `pin_xclk` | 模块内部提供 |
| SIOD/SDA | GPIO4 | `pin_sccb_sda` | 双向 |
| SIOC/SCL | GPIO5 | `pin_sccb_scl` | ESP → Camera |
| Y2/D0 | GPIO11 | `pin_d0` | Camera → ESP |
| Y3/D1 | GPIO9 | `pin_d1` | Camera → ESP |
| Y4/D2 | GPIO8 | `pin_d2` | Camera → ESP |
| Y5/D3 | GPIO10 | `pin_d3` | Camera → ESP |
| Y6/D4 | GPIO12 | `pin_d4` | Camera → ESP |
| Y7/D5 | GPIO18 | `pin_d5` | Camera → ESP |
| Y8/D6 | GPIO17 | `pin_d6` | Camera → ESP |
| Y9/D7 | GPIO16 | `pin_d7` | Camera → ESP |
| VSYNC | GPIO6 | `pin_vsync` | Camera → ESP |
| HREF/HSYNC | GPIO7 | `pin_href` | Camera → ESP |
| PCLK | GPIO13 | `pin_pclk` | Camera → ESP |
| GND | GND | — | 公共地 |
| VCC | 3.3 V | — | 电源 |

## XCLK 说明

模块板载 24 MHz 有源时钟通过 `OV_XCLK` 驱动 OV5640，因此 ESP32-S3 不连接 XCLK，配置为 `pin_xclk = -1`。`xclk_freq_hz` 仍设置为 `24000000`，用于向驱动描述传感器实际输入时钟。esp32-camera 2.1.7 在 `pin_xclk < 0` 时不会配置 XCLK GPIO。

不要把模块排针中的 `NC` 当作 XCLK。NC 是否接到连接器不影响当前接口，但外部不得向该脚驱动电平。

## 初始采集参数

- 像素格式：8 位灰度 `PIXFORMAT_GRAYSCALE`
- 分辨率：QVGA，320 × 240
- 帧缓冲：2 个，位于 PSRAM
- 抓取策略：`CAMERA_GRAB_LATEST`
- 模块输入时钟：24 MHz

## 硬件验收

构建前显式选择 ESP32-S3：

```powershell
idf.py set-target esp32s3
idf.py build
```

烧录并监控后，启动日志应显示约 8 MB PSRAM、OV5640 PID `0x5640`，随后每 100 帧打印一次状态。Task3 通过标准为连续采集并归还 1000 帧，无 camera timeout、无重启，且内部堆与 PSRAM 可用量不持续下降。
