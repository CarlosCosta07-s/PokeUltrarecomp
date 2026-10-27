cmake_minimum_required(VERSION 3.24)

project(PokeUltrarecompNative
    VERSION 0.1.0
    DESCRIPTION "Native recompilation and validation tools for PokeUltrarecomp"
    LANGUAGES C CXX
)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

include(CTest)
find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)

if(BUILD_TESTING)
    add_test(
        NAME native_codegen_smoke
        COMMAND
            "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/run_native_poc_pipeline.py"
            --cc "${CMAKE_C_COMPILER}"
    )
    set_tests_properties(native_codegen_smoke PROPERTIES
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
        TIMEOUT 120
    )

    set(NATIVE_GENERATED_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated")
    set(NATIVE_GENERATED_C_FILES
        "${NATIVE_GENERATED_DIR}/native_a32_generated.c"
        "${NATIVE_GENERATED_DIR}/native_thumb_generated.c"
    )

    add_custom_command(
        OUTPUT ${NATIVE_GENERATED_C_FILES}
        COMMAND
            "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/generate_native_abi_fixtures.py"
            --output-dir "${NATIVE_GENERATED_DIR}"
        DEPENDS
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/generate_native_abi_fixtures.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm_subset_poc.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/thumb_subset_poc.py"
        COMMENT "Generate synthetic ARM/Thumb C fixtures for the native C++ ABI test"
        VERBATIM
    )

    add_executable(native_abi_smoke
        tests/native_runtime_host.cpp
        ${NATIVE_GENERATED_C_FILES}
    )
    target_include_directories(native_abi_smoke PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/include")
    target_compile_features(native_abi_smoke PRIVATE cxx_std_20)
    set_source_files_properties(${NATIVE_GENERATED_C_FILES} PROPERTIES LANGUAGE C)

    add_test(
        NAME native_cpp_abi_smoke
        COMMAND "$<TARGET_FILE:native_abi_smoke>"
    )
    set_tests_properties(native_cpp_abi_smoke PROPERTIES TIMEOUT 15)

    add_test(
        NAME python_unit_tests
        COMMAND
            "${Python3_EXECUTABLE}"
            -m unittest discover -s tests -v
    )
    set_tests_properties(python_unit_tests PROPERTIES
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
        ENVIRONMENT "CC="
        TIMEOUT 180
    )

    add_test(
        NAME repository_safety
        COMMAND
            "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/check_repository_safety.py"
    )
    set_tests_properties(repository_safety PROPERTIES
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
        TIMEOUT 30
    )

    add_custom_target(verify
        COMMAND "${CMAKE_CTEST_COMMAND}" --output-on-failure
        WORKING_DIRECTORY "${CMAKE_BINARY_DIR}"
        COMMENT "Run native recompilation smoke tests, C++ ABI integration, Python tests, and repository safety checks"
        USES_TERMINAL
        VERBATIM
    )
    add_dependencies(verify native_abi_smoke)
endif()

message(STATUS "PokeUltrarecomp native validation toolchain")
message(STATUS "  C compiler: ${CMAKE_C_COMPILER}")
message(STATUS "  C++ compiler: ${CMAKE_CXX_COMPILER}")
message(STATUS "  Python: ${Python3_EXECUTABLE}")
message(STATUS "  Game files required: no")
message(STATUS "  Emulator/interpreter fallback: prohibited")
