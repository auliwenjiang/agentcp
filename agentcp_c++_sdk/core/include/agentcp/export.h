#pragma once

#if defined(_WIN32) && defined(ACP_SHARED)
  #if defined(ACP_BUILD)
    #define ACP_API __declspec(dllexport)
  #else
    #define ACP_API __declspec(dllimport)
  #endif
#else
  #define ACP_API
#endif
