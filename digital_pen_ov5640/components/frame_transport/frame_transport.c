#include "frame_transport.h"

#include <stddef.h>

#include "frame_transport_internal.h"

esp_err_t frame_transport_start(const frame_transport_config_t *config) {
  if (config == NULL || config->sensor == NULL || config->width == 0 ||
      config->height == 0 || config->pixel_format == NULL) {
    return ESP_ERR_INVALID_ARG;
  }
  return transport_http_start(config);
}
