idf_component_register(
    SRCS "camera_capture.c"
    INCLUDE_DIRS "include"
    PRIV_INCLUDE_DIRS "."
    REQUIRES esp32-camera esp_psram heap
)
