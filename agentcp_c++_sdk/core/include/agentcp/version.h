#pragma once

#define ACP_VERSION_MAJOR 0
#define ACP_VERSION_MINOR 1
#define ACP_VERSION_PATCH 0

#define ACP_MAKE_VERSION(major, minor, patch) (((major) << 16) | ((minor) << 8) | (patch))
#define ACP_VERSION ACP_MAKE_VERSION(ACP_VERSION_MAJOR, ACP_VERSION_MINOR, ACP_VERSION_PATCH)
