idf_component_register(
    SRCS "app_main.c"
    INCLUDE_DIRS "."
    REQUIRES camera_capture esp_netif frame_transport network_manager
)
