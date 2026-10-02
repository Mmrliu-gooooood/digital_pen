#include "network_manager.h"

#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#include "esp_check.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "nvs_flash.h"
#include "sdkconfig.h"

#define STA_GOT_IP_BIT BIT0

static const char *TAG = "network_manager";
static EventGroupHandle_t s_events;
static esp_netif_t *s_sta_netif;
static esp_netif_t *s_ap_netif;
static esp_ip4_addr_t s_sta_ip;
static bool s_fallback_requested;
static bool s_started;

static void network_event_handler(void *argument, esp_event_base_t event_base,
                                  int32_t event_id, void *event_data) {
  (void)argument;
  if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
    esp_wifi_connect();
    return;
  }
  if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED &&
      !s_fallback_requested) {
    esp_wifi_connect();
    return;
  }
  if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
    const ip_event_got_ip_t *event = (const ip_event_got_ip_t *)event_data;
    s_sta_ip = event->ip_info.ip;
    xEventGroupSetBits(s_events, STA_GOT_IP_BIT);
  }
}

static esp_err_t initialize_nvs(void) {
  esp_err_t err = nvs_flash_init();
  if (err == ESP_ERR_NVS_NO_FREE_PAGES ||
      err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
    ESP_LOGW(TAG, "NVS layout is stale; erasing and reinitializing NVS");
    ESP_RETURN_ON_ERROR(nvs_flash_erase(), TAG, "Could not erase NVS");
    err = nvs_flash_init();
  }
  return err;
}

static esp_err_t start_softap(network_manager_info_t *info) {
  uint8_t mac[6];
  ESP_RETURN_ON_ERROR(esp_read_mac(mac, ESP_MAC_WIFI_SOFTAP), TAG,
                      "Could not read SoftAP MAC");

  char ssid[33];
  snprintf(ssid, sizeof(ssid), "digital-pen-%02X%02X%02X", mac[3], mac[4],
           mac[5]);
  wifi_config_t ap_config = {0};
  ap_config.ap.ssid_len = strlen(ssid);
  memcpy(ap_config.ap.ssid, ssid, ap_config.ap.ssid_len);
  ap_config.ap.channel = 1;
  ap_config.ap.max_connection = 4;
  ap_config.ap.authmode = WIFI_AUTH_OPEN;
  ap_config.ap.pmf_cfg.required = false;

  s_fallback_requested = true;
  ESP_RETURN_ON_ERROR(esp_wifi_stop(), TAG, "Could not stop STA mode");
  ESP_RETURN_ON_ERROR(esp_wifi_set_mode(WIFI_MODE_AP), TAG,
                      "Could not select SoftAP mode");
  ESP_RETURN_ON_ERROR(esp_wifi_set_config(WIFI_IF_AP, &ap_config), TAG,
                      "Could not configure SoftAP");
  ESP_RETURN_ON_ERROR(esp_wifi_start(), TAG, "Could not start SoftAP");

  esp_netif_ip_info_t ip_info;
  ESP_RETURN_ON_ERROR(esp_netif_get_ip_info(s_ap_netif, &ip_info), TAG,
                      "Could not read SoftAP IP");
  info->mode = NETWORK_MANAGER_MODE_SOFTAP;
  info->ip = ip_info.ip;
  snprintf(info->ssid, sizeof(info->ssid), "%s", ssid);
  ESP_LOGW(TAG, "STA DHCP timed out; SoftAP SSID=%s IP=" IPSTR, ssid,
           IP2STR(&info->ip));
  return ESP_OK;
}

static void rollback_network(bool netif_initialized, bool event_loop_created,
                             bool wifi_initialized, bool wifi_started,
                             bool wifi_handler_registered,
                             bool ip_handler_registered) {
  s_fallback_requested = true;
  if (wifi_handler_registered) {
    esp_event_handler_unregister(WIFI_EVENT, ESP_EVENT_ANY_ID,
                                 &network_event_handler);
  }
  if (ip_handler_registered) {
    esp_event_handler_unregister(IP_EVENT, IP_EVENT_STA_GOT_IP,
                                 &network_event_handler);
  }
  if (wifi_started) {
    esp_wifi_stop();
  }
  if (wifi_initialized) {
    esp_wifi_deinit();
  }
  if (s_sta_netif != NULL) {
    esp_netif_destroy_default_wifi(s_sta_netif);
    s_sta_netif = NULL;
  }
  if (s_ap_netif != NULL) {
    esp_netif_destroy_default_wifi(s_ap_netif);
    s_ap_netif = NULL;
  }
  if (s_events != NULL) {
    vEventGroupDelete(s_events);
    s_events = NULL;
  }
  if (event_loop_created) {
    esp_event_loop_delete_default();
  }
  if (netif_initialized) {
    esp_netif_deinit();
  }
  s_fallback_requested = false;
}

esp_err_t network_manager_start(network_manager_info_t *info) {
  if (info == NULL) {
    return ESP_ERR_INVALID_ARG;
  }
  if (s_started || s_events != NULL) {
    return ESP_ERR_INVALID_STATE;
  }

  bool netif_initialized = false;
  bool event_loop_created = false;
  bool wifi_initialized = false;
  bool wifi_started = false;
  bool wifi_handler_registered = false;
  bool ip_handler_registered = false;
  const char *failed_step = "NVS initialization";
  esp_err_t err = ESP_OK;
  memset(info, 0, sizeof(*info));
  if ((err = initialize_nvs()) != ESP_OK) {
    goto fail;
  }
  failed_step = "esp-netif initialization";
  if ((err = esp_netif_init()) != ESP_OK) {
    goto fail;
  }
  netif_initialized = true;
  failed_step = "event loop creation";
  if ((err = esp_event_loop_create_default()) != ESP_OK) {
    goto fail;
  }
  event_loop_created = true;

  failed_step = "default Wi-Fi netif creation";
  s_sta_netif = esp_netif_create_default_wifi_sta();
  s_ap_netif = esp_netif_create_default_wifi_ap();
  if (s_sta_netif == NULL || s_ap_netif == NULL) {
    err = ESP_ERR_NO_MEM;
    goto fail;
  }

  failed_step = "event group creation";
  s_events = xEventGroupCreate();
  if (s_events == NULL) {
    err = ESP_ERR_NO_MEM;
    goto fail;
  }
  wifi_init_config_t init_config = WIFI_INIT_CONFIG_DEFAULT();
  failed_step = "Wi-Fi initialization";
  if ((err = esp_wifi_init(&init_config)) != ESP_OK) {
    goto fail;
  }
  wifi_initialized = true;
  failed_step = "Wi-Fi event handler registration";
  if ((err = esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID,
                                        &network_event_handler, NULL)) !=
      ESP_OK) {
    goto fail;
  }
  wifi_handler_registered = true;
  failed_step = "IP event handler registration";
  if ((err = esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP,
                                        &network_event_handler, NULL)) !=
      ESP_OK) {
    goto fail;
  }
  ip_handler_registered = true;

  wifi_config_t sta_config = {0};
  snprintf((char *)sta_config.sta.ssid, sizeof(sta_config.sta.ssid), "%s",
           CONFIG_DIGITAL_PEN_WIFI_SSID);
  snprintf((char *)sta_config.sta.password, sizeof(sta_config.sta.password),
           "%s", CONFIG_DIGITAL_PEN_WIFI_PASSWORD);
  sta_config.sta.threshold.authmode =
      strlen(CONFIG_DIGITAL_PEN_WIFI_PASSWORD) == 0 ? WIFI_AUTH_OPEN
                                                    : WIFI_AUTH_WPA2_PSK;
  sta_config.sta.pmf_cfg.capable = true;
  sta_config.sta.pmf_cfg.required = false;

  failed_step = "STA mode selection";
  if ((err = esp_wifi_set_mode(WIFI_MODE_STA)) != ESP_OK) {
    goto fail;
  }
  failed_step = "STA configuration";
  if ((err = esp_wifi_set_config(WIFI_IF_STA, &sta_config)) != ESP_OK) {
    goto fail;
  }
  failed_step = "STA startup";
  if ((err = esp_wifi_start()) != ESP_OK) {
    goto fail;
  }
  wifi_started = true;
  ESP_LOGI(TAG, "Connecting in STA mode: SSID=%s timeout=%d s",
           CONFIG_DIGITAL_PEN_WIFI_SSID,
           CONFIG_DIGITAL_PEN_WIFI_TIMEOUT_SECONDS);

  const EventBits_t bits = xEventGroupWaitBits(
      s_events, STA_GOT_IP_BIT, pdFALSE, pdTRUE,
      pdMS_TO_TICKS(CONFIG_DIGITAL_PEN_WIFI_TIMEOUT_SECONDS * 1000));
  if ((bits & STA_GOT_IP_BIT) == 0) {
    failed_step = "SoftAP fallback";
    if ((err = start_softap(info)) != ESP_OK) {
      goto fail;
    }
  } else {
    info->mode = NETWORK_MANAGER_MODE_STA;
    info->ip = s_sta_ip;
    snprintf(info->ssid, sizeof(info->ssid), "%s",
             CONFIG_DIGITAL_PEN_WIFI_SSID);
    ESP_LOGI(TAG, "STA connected: SSID=%s IP=" IPSTR, info->ssid,
             IP2STR(&info->ip));
  }

  s_started = true;
  return ESP_OK;

fail:
  ESP_LOGE(TAG, "%s failed: %s", failed_step, esp_err_to_name(err));
  rollback_network(netif_initialized, event_loop_created, wifi_initialized,
                   wifi_started, wifi_handler_registered,
                   ip_handler_registered);
  return err;
}

const char *network_manager_mode_name(network_manager_mode_t mode) {
  return mode == NETWORK_MANAGER_MODE_STA ? "STA" : "SoftAP";
}
