#pragma once

#include <stddef.h>
#include <stdint.h>

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
  const char *sensor;
  uint16_t width;
  uint16_t height;
  const char *pixel_format;
  size_t psram_bytes;
  uint64_t frame_count;
} device_status_t;

esp_err_t device_protocol_format_status_json(char *buffer, size_t capacity,
                                             const device_status_t *status,
                                             size_t *length);
esp_err_t device_protocol_format_pgm_header(char *buffer, size_t capacity,
                                            uint16_t width, uint16_t height,
                                            size_t *length);

#ifdef __cplusplus
}
#endif
