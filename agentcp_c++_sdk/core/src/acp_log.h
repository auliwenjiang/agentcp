#pragma once

// AgentCP cross-platform logging utility
// On Android: outputs to logcat via __android_log_print
// On other platforms: outputs to stderr

#ifdef __ANDROID__
#include <android/log.h>
#define ACP_LOG_TAG "AgentCP_Native"
#define ACP_LOGE(...) __android_log_print(ANDROID_LOG_ERROR, ACP_LOG_TAG, __VA_ARGS__)
#define ACP_LOGW(...) __android_log_print(ANDROID_LOG_WARN,  ACP_LOG_TAG, __VA_ARGS__)
#define ACP_LOGI(...) __android_log_print(ANDROID_LOG_INFO,  ACP_LOG_TAG, __VA_ARGS__)
#define ACP_LOGD(...) __android_log_print(ANDROID_LOG_DEBUG, ACP_LOG_TAG, __VA_ARGS__)
#else
#include <cstdio>
#define ACP_LOGE(...) do { fprintf(stderr, "[ERROR] "); fprintf(stderr, __VA_ARGS__); fprintf(stderr, "\n"); } while(0)
#define ACP_LOGW(...) do { fprintf(stderr, "[WARN]  "); fprintf(stderr, __VA_ARGS__); fprintf(stderr, "\n"); } while(0)
#define ACP_LOGI(...) do { fprintf(stderr, "[INFO]  "); fprintf(stderr, __VA_ARGS__); fprintf(stderr, "\n"); } while(0)
#define ACP_LOGD(...) do { fprintf(stderr, "[DEBUG] "); fprintf(stderr, __VA_ARGS__); fprintf(stderr, "\n"); } while(0)
#endif
