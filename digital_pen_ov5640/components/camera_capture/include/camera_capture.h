#pragma once

#include <stdint.h>

#include "esp_camera.h"
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t camera_capture_init(void);
camera_fb_t *camera_capture_get(void);
void camera_capture_return(camera_fb_t *fb);
esp_err_t camera_capture_get_exposure(uint32_t *exposure);

#ifdef __cplusplus
}
#endif
