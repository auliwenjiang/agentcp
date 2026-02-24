cmake_minimum_required(VERSION 3.18)

project(agentcp_tests LANGUAGES CXX)

include(FetchContent)
FetchContent_Declare(
    googletest
    URL https://github.com/google/googletest/archive/release-1.12.1.zip
)
set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(googletest)

enable_testing()

add_executable(agentcp_tests
    test_agentcp.cpp
    test_session.cpp
    test_lifecycle.cpp
    test_concurrent.cpp
)

target_link_libraries(agentcp_tests
    agentcp_core
    gtest_main
    gmock_main
)

target_compile_features(agentcp_tests PRIVATE cxx_std_17)

include(GoogleTest)
gtest_discover_tests(agentcp_tests)
