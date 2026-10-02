#include "device_protocol.h"

#include <inttypes.h>
#include <stdio.h>

static esp_err_t checked_format_result(int result, size_t capacity,
                                       size_t *length) {
  if (result < 0) {
    return ESP_FAIL;
  }
  if ((size_t)result >= capacity) {
    return ESP_ERR_INVALID_SIZE;
  }
  *length = (size_t)result;
  return ESP_OK;
}

esp_err_t device_protocol_format_status_json(char *buffer, size_t capacity,
                                             const device_status_t *status,
                                             size_t *length) {
  if (buffer == NULL || capacity == 0 || status == NULL || length == NULL ||
      status->sensor == NULL || status->pixel_format == NULL) {
    return ESP_ERR_INVALID_ARG;
  }
  const int result = snprintf(
      buffer, capacity,
      "{\"sensor\":\"%s\",\"width\":%" PRIu16
      ",\"height\":%" PRIu16 ",\"resolution\":\"%" PRIu16 "x%" PRIu16
      "\",\"pixel_format\":\"%s\",\"psram_bytes\":%zu,\"frame_count\":%"
      PRIu64 "}",
      status->sensor, status->width, status->height, status->width,
      status->height, status->pixel_format, status->psram_bytes,
      status->frame_count);
  return checked_format_result(result, capacity, length);
}

esp_err_t device_protocol_format_pgm_header(char *buffer, size_t capacity,
                                            uint16_t width, uint16_t height,
                                            size_t *length) {
  if (buffer == NULL || capacity == 0 || width == 0 || height == 0 ||
      length == NULL) {
    return ESP_ERR_INVALID_ARG;
  }
  const int result =
      snprintf(buffer, capacity, "P5\n%" PRIu16 " %" PRIu16 "\n255\n", width,
               height);
  return checked_format_result(result, capacity, length);
}
