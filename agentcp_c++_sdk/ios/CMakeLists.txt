cmake_minimum_required(VERSION 3.18)

project(agentcp_ios LANGUAGES CXX OBJCXX)

add_subdirectory(../core core_build)

add_library(agentcp_ios STATIC
    src/AgentCP.mm
    src/AgentID.mm
    src/AgentCPTypes.mm
)

target_include_directories(agentcp_ios
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
        ../core/include
)

target_link_libraries(agentcp_ios
    PRIVATE
        agentcp_core
)

if (APPLE)
    target_compile_options(agentcp_ios PRIVATE -fobjc-arc)
endif()
