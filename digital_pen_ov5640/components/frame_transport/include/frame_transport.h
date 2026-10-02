#pragma once

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
} frame_transport_config_t;

esp_err_t frame_transport_start(const frame_transport_config_t *config);

#ifdef __cplusplus
}
#endif
