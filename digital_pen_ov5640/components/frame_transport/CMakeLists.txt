idf_component_register(
    SRCS "frame_transport.c" "transport_http.c"
    INCLUDE_DIRS "include"
    PRIV_INCLUDE_DIRS "."
    REQUIRES camera_capture device_protocol esp_http_server esp_psram esp_timer
)
