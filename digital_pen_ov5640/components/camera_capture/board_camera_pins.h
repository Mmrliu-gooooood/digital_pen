#pragma once

/* OV5640 module wiring supplied for the ESP32-S3 N16R8 prototype. */
#define CAM_PIN_PWDN 38
#define CAM_PIN_RESET 15

/* The camera module provides its own 24 MHz OV_XCLK clock. */
#define CAM_PIN_XCLK (-1)
#define CAM_XCLK_FREQ_HZ 24000000

#define CAM_PIN_SIOD 4
#define CAM_PIN_SIOC 5

#define CAM_PIN_D0 11
#define CAM_PIN_D1 9
#define CAM_PIN_D2 8
#define CAM_PIN_D3 10
#define CAM_PIN_D4 12
#define CAM_PIN_D5 18
#define CAM_PIN_D6 17
#define CAM_PIN_D7 16

#define CAM_PIN_VSYNC 6
#define CAM_PIN_HREF 7
#define CAM_PIN_PCLK 13

_Static_assert(CAM_PIN_XCLK == -1,
               "XCLK must remain disconnected from ESP32-S3");
