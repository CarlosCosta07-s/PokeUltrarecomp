#include "pokeultrarecomp/native_abi.h"

#include <cstdint>
#include <iostream>
#include <type_traits>

static_assert(std::is_standard_layout_v<PokeNativeCall>);
static_assert(std::is_standard_layout_v<PokeNativeResult>);
static_assert(sizeof(((PokeNativeCall *)nullptr)->registers) / sizeof(uint32_t)
              == POKE_NATIVE_REGISTER_COUNT);

namespace {

int fail(const char *message)
{
    std::cerr << "FAIL: " << message << '\n';
    return 1;
}

bool equals_sentinel(const PokeNativeResult &result)
{
    if (result.abi_version != UINT32_C(0xAAAAAAAA)
        || result.return_value != UINT32_C(0xAAAAAAAA)
        || result.steps_executed != UINT32_C(0xAAAAAAAA)
        || result.nzcv != UINT8_C(0xAA)
        || result.execution_status != UINT8_C(0xAA)) {
        return false;
    }
    for (uint32_t value : result.registers) {
        if (value != UINT32_C(0xAAAAAAAA)) return false;
    }
    return true;
}

void set_sentinel(PokeNativeResult &result)
{
    result.abi_version = UINT32_C(0xAAAAAAAA);
    for (uint32_t &value : result.registers) value = UINT32_C(0xAAAAAAAA);
    result.return_value = UINT32_C(0xAAAAAAAA);
    result.steps_executed = UINT32_C(0xAAAAAAAA);
    result.nzcv = UINT8_C(0xAA);
    result.execution_status = UINT8_C(0xAA);
}

} // namespace

int main()
{
    PokeNativeCall call{};
    call.abi_version = POKE_NATIVE_ABI_VERSION;
    call.registers[0] = 37U;
    call.registers[1] = UINT32_C(0x12345678);
    call.registers[2] = UINT32_C(0x80000000);
    call.registers[3] = UINT32_C(0xDEADBEEF);
    call.registers[4] = 4U;
    call.registers[5] = 5U;
    call.registers[6] = 6U;
    call.registers[7] = 7U;
    call.initial_nzcv = UINT8_C(0xB);

    PokeNativeResult result{};
    if (poke_native_execute_a32(&call, &result) != POKE_NATIVE_ABI_OK) {
        return fail("A32 call through the C ABI returned an error");
    }
    if (result.abi_version != POKE_NATIVE_ABI_VERSION
        || result.return_value != 12U || result.registers[0] != 12U
        || result.registers[1] != UINT32_MAX || result.registers[2] != call.registers[2]
        || result.registers[3] != call.registers[3]) {
        return fail("A32 result or register preservation mismatch");
    }
    for (uint32_t index = 4U; index < POKE_NATIVE_REGISTER_COUNT; ++index) {
        if (result.registers[index] != call.registers[index]) {
            return fail("A32 host register preservation mismatch");
        }
    }
    if (result.nzcv != UINT8_C(0xB) || result.steps_executed != 10U
        || result.execution_status != 0U) {
        return fail("A32 NZCV/status/step-count mismatch");
    }
    std::cout << "PASS: C++20 host calls generated A32 C through the versioned C ABI\n";

    call.registers[0] = 99U;
    call.initial_nzcv = UINT8_C(0x9);
    set_sentinel(result);
    if (poke_native_execute_thumb(&call, &result) != POKE_NATIVE_ABI_OK) {
        return fail("Thumb call through the C ABI returned an error");
    }
    if (result.abi_version != POKE_NATIVE_ABI_VERSION
        || result.return_value != 7U || result.registers[0] != 7U
        || result.nzcv != UINT8_C(0x6) || result.steps_executed != 5U
        || result.execution_status != 0U) {
        return fail("Thumb result/NZCV/status/step-count mismatch");
    }
    for (uint32_t index = 1U; index < POKE_NATIVE_REGISTER_COUNT; ++index) {
        if (result.registers[index] != call.registers[index]) {
            return fail("Thumb register preservation mismatch");
        }
    }
    std::cout << "PASS: C++20 host calls generated Thumb C through the versioned C ABI\n";

    set_sentinel(result);
    call.initial_nzcv = UINT8_C(16);
    if (poke_native_execute_a32(&call, &result) != POKE_NATIVE_ABI_INVALID_ARGUMENT) {
        return fail("invalid NZCV input was not rejected");
    }
    if (!equals_sentinel(result)) return fail("invalid input partially modified the output result");

    call.initial_nzcv = 0U;
    call.abi_version = UINT32_C(99);
    if (poke_native_execute_thumb(&call, &result) != POKE_NATIVE_ABI_VERSION_MISMATCH) {
        return fail("ABI version mismatch was not rejected");
    }
    if (!equals_sentinel(result)) return fail("ABI mismatch partially modified the output result");

    if (poke_native_execute_a32(nullptr, &result) != POKE_NATIVE_ABI_INVALID_ARGUMENT) {
        return fail("null call pointer was not rejected");
    }
    if (poke_native_execute_thumb(&call, nullptr) != POKE_NATIVE_ABI_INVALID_ARGUMENT) {
        return fail("null result pointer was not rejected");
    }
    std::cout << "PASS: ABI rejects invalid inputs without partially modifying results\n";
    return 0;
}
