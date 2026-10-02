#include "app_config.h"
#include "camera_capture.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "frame_transport.h"
#include "network_manager.h"

static const char *TAG = "digital_pen";

void app_main(void) {
  esp_err_t err = camera_capture_init();
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "Camera initialization stopped frame service: %s",
             esp_err_to_name(err));
    return;
  }

  network_manager_info_t network_info;
  err = network_manager_start(&network_info);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "Network initialization stopped frame service: %s",
             esp_err_to_name(err));
    return;
  }

  const frame_transport_config_t transport_config = {
      .sensor = "OV5640",
      .width = APP_CAMERA_WIDTH,
      .height = APP_CAMERA_HEIGHT,
      .pixel_format = "GRAYSCALE",
  };
  err = frame_transport_start(&transport_config);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "HTTP frame service failed to start: %s",
             esp_err_to_name(err));
    return;
  }

  ESP_LOGI(TAG, "Ready: mode=%s SSID=%s HTTP=http://" IPSTR,
           network_manager_mode_name(network_info.mode), network_info.ssid,
           IP2STR(&network_info.ip));
}
