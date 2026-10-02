#include "camera_capture.h"

#include <stdbool.h>
#include <stddef.h>

#include "board_camera_pins.h"
#include "driver/ledc.h"
#include "esp_log.h"
#include "esp_psram.h"
#include "sensor.h"

#define REQUIRED_PSRAM_BYTES (8U * 1024U * 1024U)

static const char *TAG = "camera_capture";
static bool s_initialized;

esp_err_t camera_capture_init(void) {
  if (s_initialized) {
    return ESP_ERR_INVALID_STATE;
  }

  if (!esp_psram_is_initialized()) {
    ESP_LOGE(TAG, "PSRAM is not initialized");
    return ESP_ERR_NOT_FOUND;
  }

  const size_t psram_size = esp_psram_get_size();
  ESP_LOGI(TAG, "Detected PSRAM: %zu bytes", psram_size);
  if (psram_size < REQUIRED_PSRAM_BYTES) {
    ESP_LOGE(TAG, "Expected 8 MB PSRAM, detected %zu bytes", psram_size);
    return ESP_ERR_INVALID_SIZE;
  }

  const camera_config_t config = {
      .pin_pwdn = CAM_PIN_PWDN,
      .pin_reset = CAM_PIN_RESET,
      .pin_xclk = CAM_PIN_XCLK,
      .pin_sccb_sda = CAM_PIN_SIOD,
      .pin_sccb_scl = CAM_PIN_SIOC,
      .pin_d7 = CAM_PIN_D7,
      .pin_d6 = CAM_PIN_D6,
      .pin_d5 = CAM_PIN_D5,
      .pin_d4 = CAM_PIN_D4,
      .pin_d3 = CAM_PIN_D3,
      .pin_d2 = CAM_PIN_D2,
      .pin_d1 = CAM_PIN_D1,
      .pin_d0 = CAM_PIN_D0,
      .pin_vsync = CAM_PIN_VSYNC,
      .pin_href = CAM_PIN_HREF,
      .pin_pclk = CAM_PIN_PCLK,
      .xclk_freq_hz = CAM_XCLK_FREQ_HZ,
      .ledc_timer = LEDC_TIMER_0,
      .ledc_channel = LEDC_CHANNEL_0,
      .pixel_format = PIXFORMAT_GRAYSCALE,
      .frame_size = FRAMESIZE_QVGA,
      .jpeg_quality = 12,
      .fb_count = 2,
      .fb_location = CAMERA_FB_IN_PSRAM,
      .grab_mode = CAMERA_GRAB_LATEST,
      .sccb_i2c_port = -1,
  };

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "esp_camera_init failed: %s", esp_err_to_name(err));
    return err;
  }

  sensor_t *sensor = esp_camera_sensor_get();
  if (sensor == NULL || sensor->id.PID != OV5640_PID) {
    const uint16_t pid = sensor == NULL ? 0U : sensor->id.PID;
    ESP_LOGE(TAG, "Expected OV5640 PID 0x%04x, detected 0x%04x", OV5640_PID,
             pid);
    esp_camera_deinit();
    return ESP_ERR_NOT_SUPPORTED;
  }

  if (sensor->pixformat != PIXFORMAT_GRAYSCALE) {
    ESP_LOGE(TAG, "OV5640 did not enter grayscale mode");
    esp_camera_deinit();
    return ESP_ERR_INVALID_RESPONSE;
  }

  s_initialized = true;
  ESP_LOGI(TAG, "OV5640 ready: PID=0x%04x, QVGA grayscale, XCLK=%d Hz (%s)",
           sensor->id.PID, CAM_XCLK_FREQ_HZ,
           CAM_PIN_XCLK < 0 ? "module supplied" : "ESP32-S3 supplied");
  return ESP_OK;
}

camera_fb_t *camera_capture_get(void) {
  if (!s_initialized) {
    return NULL;
  }
  return esp_camera_fb_get();
}

void camera_capture_return(camera_fb_t *fb) {
  if (fb != NULL) {
    esp_camera_fb_return(fb);
  }
}

esp_err_t camera_capture_get_exposure(uint32_t *exposure) {
  if (!s_initialized || exposure == NULL) {
    return ESP_ERR_INVALID_ARG;
  }

  sensor_t *sensor = esp_camera_sensor_get();
  if (sensor == NULL || sensor->get_reg == NULL) {
    return ESP_ERR_INVALID_STATE;
  }
  const int high = sensor->get_reg(sensor, 0x3500, 0xFF);
  const int middle = sensor->get_reg(sensor, 0x3501, 0xFF);
  const int low = sensor->get_reg(sensor, 0x3502, 0xFF);
  if (high < 0 || middle < 0 || low < 0) {
    ESP_LOGE(TAG, "Could not read OV5640 exposure registers");
    return ESP_FAIL;
  }
  *exposure = ((uint32_t)(high & 0x0F) << 12) |
              ((uint32_t)(middle & 0xFF) << 4) |
              ((uint32_t)(low & 0xF0) >> 4);
  return ESP_OK;
}
