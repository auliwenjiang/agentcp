cmake_minimum_required(VERSION 3.18)

project(agentcp_core LANGUAGES CXX)

# ============== Dependencies ==============

include(FetchContent)

# nlohmann/json (single-header JSON library) - local path
FetchContent_Declare(
    nlohmann_json
    SOURCE_DIR "H:/project/evol_main/json-3.11.3"
)

# IXWebSocket (cross-platform WebSocket library) - local path
FetchContent_Declare(
    ixwebsocket
    SOURCE_DIR "H:/project/evol_main/IXWebSocket-11.4.5"
)

# Make dependencies available
set(IXWEBSOCKET_INSTALL OFF CACHE BOOL "" FORCE)

# TLS: try OpenSSL first, then disable TLS if not found
find_package(OpenSSL QUIET)
if(OpenSSL_FOUND)
    set(USE_TLS ON CACHE BOOL "" FORCE)
    set(USE_OPEN_SSL ON CACHE BOOL "" FORCE)
    set(USE_MBED_TLS OFF CACHE BOOL "" FORCE)
else()
    set(USE_TLS OFF CACHE BOOL "" FORCE)
endif()

FetchContent_MakeAvailable(nlohmann_json ixwebsocket)

# ============== Core Library ==============

add_library(agentcp_core STATIC
    # Original sources
    src/agentcp.cpp
    src/agentid.cpp
    src/session_manager.cpp
    src/session.cpp
    src/stream.cpp
    src/file_client.cpp
    src/utils.cpp
    src/crypto.cpp

    # Network layer
    src/net/http_client.cpp
    src/net/udp_socket.cpp
    src/net/websocket_client.cpp

    # Protocol layer
    src/protocol/auth_protocol.cpp
    src/protocol/heartbeat_protocol.cpp
    src/protocol/message_protocol.cpp
    src/protocol/binary_protocol.cpp

    # Client layer
    src/client/auth_client.cpp
    src/client/heartbeat_client.cpp
    src/client/message_client.cpp
    src/client/stream_client_impl.cpp

    # Group module
    src/group/group_types.cpp
    src/group/group_client.cpp
    src/group/group_events.cpp
    src/group/group_operations.cpp
    src/group/cursor_store.cpp
)

target_include_directories(agentcp_core
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/src
)

target_compile_features(agentcp_core PUBLIC cxx_std_17)

# ============== nlohmann/json ==============

# Create a symlink/copy of the json.hpp single-header into third_party
# so that includes like "third_party/json.hpp" work from src/
get_target_property(JSON_INCLUDE_DIR nlohmann_json INTERFACE_INCLUDE_DIRECTORIES)
# Find the actual json.hpp location
file(GLOB_RECURSE JSON_HPP_FILE "${nlohmann_json_SOURCE_DIR}/single_include/nlohmann/json.hpp")
if(JSON_HPP_FILE)
    # Copy to our third_party directory for easy include
    configure_file(${JSON_HPP_FILE} ${CMAKE_CURRENT_SOURCE_DIR}/src/third_party/json.hpp COPYONLY)
    message(STATUS "Copied json.hpp to src/third_party/")
endif()

target_include_directories(agentcp_core PRIVATE
    ${nlohmann_json_SOURCE_DIR}/single_include
)

# Also add a convenience include path so "third_party/json.hpp" resolves
# when included as a relative path from src/
target_include_directories(agentcp_core PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/src
)

# ============== IXWebSocket ==============

target_link_libraries(agentcp_core PRIVATE ixwebsocket)

# ============== zlib (optional) ==============

find_package(ZLIB QUIET)
if(ZLIB_FOUND)
    target_link_libraries(agentcp_core PRIVATE ZLIB::ZLIB)
    target_compile_definitions(agentcp_core PRIVATE AGENTCP_USE_ZLIB=1)
    message(STATUS "zlib found: ${ZLIB_VERSION_STRING}")
else()
    message(WARNING "zlib not found, binary protocol compression disabled")
    target_compile_definitions(agentcp_core PRIVATE AGENTCP_USE_ZLIB=0)
endif()

# ============== OpenSSL (optional) ==============

find_package(OpenSSL QUIET)
if(OpenSSL_FOUND)
    target_link_libraries(agentcp_core PUBLIC OpenSSL::SSL OpenSSL::Crypto)
    target_compile_definitions(agentcp_core PRIVATE AGENTCP_USE_OPENSSL=1)
    message(STATUS "OpenSSL found: ${OPENSSL_VERSION}")
else()
    message(WARNING "OpenSSL not found, using stub crypto implementation")
    target_compile_definitions(agentcp_core PRIVATE AGENTCP_USE_OPENSSL=0)
endif()

# ============== Platform-specific ==============

if(WIN32)
    target_link_libraries(agentcp_core PRIVATE ws2_32)
endif()

if(ANDROID)
    target_link_libraries(agentcp_core PRIVATE log)
endif()

# ============== Tests ==============

option(BUILD_TESTS "Build tests" ON)
if(BUILD_TESTS)
    add_subdirectory(tests)
endif()
