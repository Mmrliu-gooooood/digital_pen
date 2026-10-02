#pragma once

#include "esp_err.h"
#include "esp_netif_ip_addr.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
  NETWORK_MANAGER_MODE_STA,
  NETWORK_MANAGER_MODE_SOFTAP,
} network_manager_mode_t;

typedef struct {
  network_manager_mode_t mode;
  esp_ip4_addr_t ip;
  char ssid[33];
} network_manager_info_t;

esp_err_t network_manager_start(network_manager_info_t *info);
const char *network_manager_mode_name(network_manager_mode_t mode);

#ifdef __cplusplus
}
#endif
