#include "frame_transport_internal.h"

#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#include "camera_capture.h"
#include "device_protocol.h"
#include "esp_camera.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_psram.h"
#include "esp_timer.h"

static const char *TAG = "transport_http";
static frame_transport_config_t s_config;
static char s_sensor[16];
static char s_pixel_format[16];
static uint64_t s_frame_count;
static httpd_handle_t s_server;

static esp_err_t status_handler(httpd_req_t *request) {
  char response[256];
  size_t response_length = 0;
  const device_status_t status = {
      .sensor = s_config.sensor,
      .width = s_config.width,
      .height = s_config.height,
      .pixel_format = s_config.pixel_format,
      .psram_bytes = esp_psram_get_size(),
      .frame_count = s_frame_count,
  };
  esp_err_t err = device_protocol_format_status_json(
      response, sizeof(response), &status, &response_length);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "Could not format status response: %s", esp_err_to_name(err));
    return httpd_resp_send_err(request, HTTPD_500_INTERNAL_SERVER_ERROR,
                               "status encoding failed");
  }
  httpd_resp_set_type(request, "application/json");
  httpd_resp_set_hdr(request, "Cache-Control", "no-store");
  return httpd_resp_send(request, response, response_length);
}

static int64_t frame_timestamp_us(const camera_fb_t *frame) {
  const int64_t timestamp =
      (int64_t)frame->timestamp.tv_sec * 1000000LL + frame->timestamp.tv_usec;
  return timestamp > 0 ? timestamp : esp_timer_get_time();
}

static esp_err_t capture_handler(httpd_req_t *request) {
  camera_fb_t *frame = camera_capture_get();
  if (frame == NULL) {
    ESP_LOGE(TAG, "Camera capture timed out");
    httpd_resp_set_status(request, "503 Service Unavailable");
    return httpd_resp_sendstr(request, "camera capture timed out");
  }

  esp_err_t err = ESP_OK;
  if (frame->buf == NULL || frame->format != PIXFORMAT_GRAYSCALE ||
      frame->width != s_config.width || frame->height != s_config.height ||
      frame->len != (size_t)s_config.width * s_config.height) {
    ESP_LOGE(TAG, "Invalid camera frame: len=%zu size=%zux%zu format=%d",
             frame->len, frame->width, frame->height, (int)frame->format);
    err = httpd_resp_send_err(request, HTTPD_500_INTERNAL_SERVER_ERROR,
                              "camera returned an invalid grayscale frame");
    goto cleanup;
  }

  char pgm_header[32];
  size_t pgm_header_length = 0;
  err = device_protocol_format_pgm_header(
      pgm_header, sizeof(pgm_header), s_config.width, s_config.height,
      &pgm_header_length);
  if (err != ESP_OK) {
    err = httpd_resp_send_err(request, HTTPD_500_INTERNAL_SERVER_ERROR,
                              "PGM header encoding failed");
    goto cleanup;
  }

  const uint64_t frame_id = ++s_frame_count;
  const int64_t timestamp_us = frame_timestamp_us(frame);
  uint32_t exposure = 0;
  err = camera_capture_get_exposure(&exposure);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "Could not read exposure for frame %" PRIu64 ": %s",
             frame_id, esp_err_to_name(err));
    err = httpd_resp_send_err(request, HTTPD_500_INTERNAL_SERVER_ERROR,
                              "camera exposure read failed");
    goto cleanup;
  }
  char frame_id_header[24];
  char timestamp_header[24];
  char exposure_header[16];
  snprintf(frame_id_header, sizeof(frame_id_header), "%" PRIu64, frame_id);
  snprintf(timestamp_header, sizeof(timestamp_header), "%" PRId64,
           timestamp_us);
  snprintf(exposure_header, sizeof(exposure_header), "%" PRIu32, exposure);

  httpd_resp_set_type(request, "image/x-portable-graymap");
  httpd_resp_set_hdr(request, "Cache-Control", "no-store");
  httpd_resp_set_hdr(request, "X-Frame-Id", frame_id_header);
  httpd_resp_set_hdr(request, "X-Timestamp-Us", timestamp_header);
  httpd_resp_set_hdr(request, "X-Exposure", exposure_header);
  err = httpd_resp_send_chunk(request, pgm_header, pgm_header_length);
  if (err == ESP_OK) {
    err = httpd_resp_send_chunk(request, (const char *)frame->buf, frame->len);
  }
  if (err == ESP_OK) {
    err = httpd_resp_send_chunk(request, NULL, 0);
  }
  if (err != ESP_OK) {
    ESP_LOGW(TAG, "Frame %" PRIu64 " send failed: %s", frame_id,
             esp_err_to_name(err));
  }

cleanup:
  camera_capture_return(frame);
  return err;
}

esp_err_t transport_http_start(const frame_transport_config_t *config) {
  if (s_server != NULL) {
    return ESP_ERR_INVALID_STATE;
  }
  if (strlen(config->sensor) >= sizeof(s_sensor) ||
      strlen(config->pixel_format) >= sizeof(s_pixel_format)) {
    return ESP_ERR_INVALID_SIZE;
  }
  snprintf(s_sensor, sizeof(s_sensor), "%s", config->sensor);
  snprintf(s_pixel_format, sizeof(s_pixel_format), "%s", config->pixel_format);
  s_config = *config;
  s_config.sensor = s_sensor;
  s_config.pixel_format = s_pixel_format;

  httpd_config_t http_config = HTTPD_DEFAULT_CONFIG();
  http_config.max_uri_handlers = 2;
  http_config.lru_purge_enable = true;
  esp_err_t err = httpd_start(&s_server, &http_config);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "Could not start HTTP server: %s", esp_err_to_name(err));
    return err;
  }

  const httpd_uri_t status_uri = {
      .uri = "/status",
      .method = HTTP_GET,
      .handler = status_handler,
      .user_ctx = NULL,
  };
  const httpd_uri_t capture_uri = {
      .uri = "/capture.pgm",
      .method = HTTP_GET,
      .handler = capture_handler,
      .user_ctx = NULL,
  };
  err = httpd_register_uri_handler(s_server, &status_uri);
  if (err == ESP_OK) {
    err = httpd_register_uri_handler(s_server, &capture_uri);
  }
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "Could not register HTTP endpoint: %s",
             esp_err_to_name(err));
    httpd_stop(s_server);
    s_server = NULL;
    return err;
  }

  ESP_LOGI(TAG, "HTTP frame service started: /status and /capture.pgm");
  return ESP_OK;
}
