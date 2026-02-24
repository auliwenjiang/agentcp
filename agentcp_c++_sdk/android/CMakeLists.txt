cmake_minimum_required(VERSION 3.18)

project(agentcp_android LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(AGENTCP_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(CMAKE_CROSSCOMPILING_EMULATOR "cmd" "/c" "echo")
set(FETCHCONTENT_SOURCE_DIR_GOOGLETEST "${CMAKE_CURRENT_SOURCE_DIR}/gtest_src/googletest-release-1.12.1")
set(googletest_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/gtest_src/googletest-release-1.12.1")

# OpenSSL for Android
# 使用预编译的 OpenSSL 静态库
set(OPENSSL_ROOT_DIR "${CMAKE_CURRENT_SOURCE_DIR}/openssl/prebuilt")
set(OPENSSL_INCLUDE_DIR "${OPENSSL_ROOT_DIR}/include")
set(OPENSSL_CRYPTO_LIBRARY "${OPENSSL_ROOT_DIR}/${ANDROID_ABI}/lib/libcrypto.a")
set(OPENSSL_SSL_LIBRARY "${OPENSSL_ROOT_DIR}/${ANDROID_ABI}/lib/libssl.a")

add_subdirectory(../core core_build)

add_library(agentcp_jni SHARED
    src/main/cpp/agentcp_jni.cpp
)

target_include_directories(agentcp_jni
    PRIVATE
        ../core/include
        ../core/src
)

target_link_libraries(agentcp_jni
    PRIVATE
        agentcp_core
        log
)
