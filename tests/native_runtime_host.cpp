#include "pokeultrarecomp/native_abi.h"

#include <array>
#include <cstdint>
#include <iostream>
#include <type_traits>

static_assert(std::is_standard_layout_v<PokeNativeCall>);
static_assert(std::is_standard_layout_v<PokeNativeResult>);
static_assert(sizeof(((PokeNativeCall *)nullptr)->registers) / sizeof(uint32_t)
              == POKE_NATIVE_REGISTER_COUNT);
static_assert(std::is_standard_layout_v<PokeNativeA32StackCall>);
static_assert(std::is_standard_layout_v<PokeNativeA32StackResult>);
static_assert(sizeof(((PokeNativeA32StackCall *)nullptr)->registers) / sizeof(uint32_t)
              == POKE_NATIVE_A32_REGISTER_COUNT);

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
        || result.guest_sp != UINT32_C(0xAAAAAAAA)
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
    result.guest_sp = UINT32_C(0xAAAAAAAA);
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

    std::array<uint8_t, 64> a32_stack_bytes{};
    a32_stack_bytes.fill(UINT8_C(0xEE));
    PokeNativeMemory a32_stack_memory{};
    a32_stack_memory.abi_version = POKE_NATIVE_ABI_VERSION;
    a32_stack_memory.guest_base = UINT32_C(0x1000);
    a32_stack_memory.size = static_cast<uint32_t>(a32_stack_bytes.size());
    a32_stack_memory.bytes = a32_stack_bytes.data();

    PokeNativeA32StackCall a32_stack_call{};
    a32_stack_call.abi_version = POKE_NATIVE_ABI_VERSION;
    a32_stack_call.registers[4] = UINT32_C(0x44444444);
    a32_stack_call.registers[5] = UINT32_C(0x55555555);
    a32_stack_call.registers[13] = UINT32_C(0x1020);
    a32_stack_call.registers[14] = UINT32_C(0xDEADBEEF);
    a32_stack_call.initial_nzcv = UINT8_C(0xB);
    PokeNativeA32StackResult a32_stack_result{};
    if (poke_native_execute_a32_stack(&a32_stack_call, &a32_stack_memory, &a32_stack_result)
        != POKE_NATIVE_ABI_OK
        || a32_stack_result.abi_version != POKE_NATIVE_ABI_VERSION
        || a32_stack_result.execution_status != POKE_NATIVE_EXECUTION_RETURNED
        || a32_stack_result.return_value != 0U
        || a32_stack_result.steps_executed != UINT32_C(3)
        || a32_stack_result.nzcv != UINT8_C(0xB)
        || a32_stack_result.registers[4] != a32_stack_call.registers[4]
        || a32_stack_result.registers[5] != a32_stack_call.registers[5]
        || a32_stack_result.registers[13] != a32_stack_call.registers[13]
        || a32_stack_result.registers[14] != a32_stack_call.registers[14]) {
        return fail("A32 full-register stack round-trip failed through the versioned C ABI");
    }
    if (a32_stack_bytes[20] != UINT8_C(0x44) || a32_stack_bytes[23] != UINT8_C(0x44)
        || a32_stack_bytes[24] != UINT8_C(0x55) || a32_stack_bytes[27] != UINT8_C(0x55)
        || a32_stack_bytes[28] != UINT8_C(0xEF) || a32_stack_bytes[29] != UINT8_C(0xBE)
        || a32_stack_bytes[30] != UINT8_C(0xAD) || a32_stack_bytes[31] != UINT8_C(0xDE)) {
        return fail("A32 STMDB/LDMIA memory order or LR serialization mismatch");
    }
    std::cout << "PASS: C++20 host calls full-register A32 stack transfer through the versioned C ABI\n";

    const auto a32_stack_bytes_before_fault = a32_stack_bytes;
    a32_stack_call.registers[13] = UINT32_C(0x1004);
    a32_stack_call.initial_nzcv = UINT8_C(0x6);
    if (poke_native_execute_a32_stack(&a32_stack_call, &a32_stack_memory, &a32_stack_result)
        != POKE_NATIVE_ABI_OK
        || a32_stack_result.execution_status != POKE_NATIVE_EXECUTION_MEMORY_FAULT
        || a32_stack_result.steps_executed != UINT32_C(1)
        || a32_stack_result.nzcv != UINT8_C(0x6)
        || a32_stack_result.registers[4] != a32_stack_call.registers[4]
        || a32_stack_result.registers[5] != a32_stack_call.registers[5]
        || a32_stack_result.registers[13] != a32_stack_call.registers[13]
        || a32_stack_result.registers[14] != a32_stack_call.registers[14]
        || a32_stack_bytes != a32_stack_bytes_before_fault) {
        return fail("A32 stack-transfer range fault changed registers, NZCV, or guest memory");
    }
    std::cout << "PASS: C++20 A32 stack-transfer faults preserve memory and guest state\n";

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

    PokeNativeCall memory_call{};
    memory_call.abi_version = POKE_NATIVE_ABI_VERSION;
    memory_call.registers[0] = UINT32_C(0x1000);
    memory_call.registers[1] = UINT32_C(4);
    memory_call.registers[2] = UINT32_C(0xA1B2C380);
    memory_call.registers[3] = UINT32_C(0xAAAAAAAA);
    memory_call.registers[4] = UINT32_C(0xAAAAAAAA);
    memory_call.registers[5] = UINT32_C(0xAAAAAAAA);
    memory_call.registers[6] = UINT32_C(0xAAAAAAAA);
    memory_call.registers[7] = UINT32_C(0xAAAAAAAA);
    memory_call.initial_nzcv = UINT8_C(0x9);

    std::array<uint8_t, 24> guest_bytes{};
    guest_bytes.fill(UINT8_C(0xEE));
    PokeNativeMemory guest_memory{};
    guest_memory.abi_version = POKE_NATIVE_ABI_VERSION;
    guest_memory.guest_base = UINT32_C(0x1000);
    guest_memory.size = static_cast<uint32_t>(guest_bytes.size());
    guest_memory.bytes = guest_bytes.data();
    PokeNativeResult memory_result{};

    if (poke_native_execute_thumb_memory(&memory_call, &guest_memory, &memory_result)
        != POKE_NATIVE_ABI_OK) {
        return fail("Thumb memory call through the C ABI returned an error");
    }
    if (memory_result.abi_version != POKE_NATIVE_ABI_VERSION
        || memory_result.return_value != UINT32_C(0x1000)
        || memory_result.steps_executed != 15U
        || memory_result.nzcv != UINT8_C(0x9)
        || memory_result.execution_status != POKE_NATIVE_EXECUTION_RETURNED) {
        return fail("Thumb memory result/status/step-count mismatch");
    }
    if (memory_result.registers[0] != UINT32_C(0x1000)
        || memory_result.registers[1] != UINT32_C(4)
        || memory_result.registers[2] != UINT32_C(0xA1B2C380)
        || memory_result.registers[3] != UINT32_C(0xA1B2C380)
        || memory_result.registers[4] != UINT32_C(0xC380)
        || memory_result.registers[5] != UINT32_C(0xFFFFFF80)
        || memory_result.registers[6] != UINT32_C(0x80)
        || memory_result.registers[7] != UINT32_C(0xFFFFC380)) {
        return fail("Thumb memory register output mismatch");
    }
    if (guest_bytes[4] != UINT8_C(0x80) || guest_bytes[5] != UINT8_C(0xC3)
        || guest_bytes[6] != UINT8_C(0xB2) || guest_bytes[7] != UINT8_C(0xA1)
        || guest_bytes[12] != UINT8_C(0x80) || guest_bytes[13] != UINT8_C(0xC3)
        || guest_bytes[14] != UINT8_C(0xB2) || guest_bytes[15] != UINT8_C(0xA1)
        || guest_bytes[16] != UINT8_C(0x80)
        || guest_bytes[18] != UINT8_C(0x80) || guest_bytes[19] != UINT8_C(0xC3)) {
        return fail("Thumb memory byte layout mismatch");
    }
    std::cout << "PASS: C++20 host calls Thumb loads/stores through the versioned C ABI\n";

    const auto memory_before_fault = guest_bytes;
    memory_call.registers[0] = UINT32_C(0x1014);
    memory_call.registers[1] = UINT32_C(4);
    memory_call.registers[2] = UINT32_C(0x11223344);
    memory_call.initial_nzcv = UINT8_C(0x6);
    set_sentinel(memory_result);
    if (poke_native_execute_thumb_memory(&memory_call, &guest_memory, &memory_result)
        != POKE_NATIVE_ABI_OK
        || memory_result.execution_status != POKE_NATIVE_EXECUTION_MEMORY_FAULT
        || memory_result.steps_executed != UINT32_C(1)
        || memory_result.nzcv != UINT8_C(0x6)
        || guest_bytes != memory_before_fault) {
        return fail("out-of-range memory call did not fail atomically through the C ABI");
    }

    memory_call.registers[0] = UINT32_C(0x1002);
    memory_call.registers[1] = UINT32_C(0);
    set_sentinel(memory_result);
    if (poke_native_execute_thumb_memory(&memory_call, &guest_memory, &memory_result)
        != POKE_NATIVE_ABI_OK
        || memory_result.execution_status != POKE_NATIVE_EXECUTION_ALIGNMENT_FAULT
        || memory_result.steps_executed != UINT32_C(1)
        || guest_bytes != memory_before_fault) {
        return fail("misaligned memory call did not fail atomically through the C ABI");
    }

    memory_call.registers[0] = UINT32_C(0x1000);
    memory_call.registers[1] = UINT32_C(4);
    guest_memory.size = 0U;
    set_sentinel(memory_result);
    if (poke_native_execute_thumb_memory(&memory_call, &guest_memory, &memory_result)
        != POKE_NATIVE_ABI_OK
        || memory_result.execution_status != POKE_NATIVE_EXECUTION_INVALID_STATE
        || memory_result.steps_executed != 0U) {
        return fail("invalid guest memory size was not reported by execution status");
    }
    guest_memory.size = static_cast<uint32_t>(guest_bytes.size());

    guest_memory.guest_base = UINT32_C(0xFFFFFFF8);
    guest_memory.size = UINT32_C(16);
    set_sentinel(memory_result);
    if (poke_native_execute_thumb_memory(&memory_call, &guest_memory, &memory_result)
        != POKE_NATIVE_ABI_OK
        || memory_result.execution_status != POKE_NATIVE_EXECUTION_INVALID_STATE
        || memory_result.steps_executed != 0U) {
        return fail("guest memory mapping overflow was not rejected");
    }
    guest_memory.guest_base = UINT32_C(0x1000);
    guest_memory.size = static_cast<uint32_t>(guest_bytes.size());

    guest_memory.abi_version = UINT32_C(99);
    set_sentinel(memory_result);
    if (poke_native_execute_thumb_memory(&memory_call, &guest_memory, &memory_result)
        != POKE_NATIVE_ABI_VERSION_MISMATCH || !equals_sentinel(memory_result)) {
        return fail("memory ABI version mismatch changed the result");
    }
    guest_memory.abi_version = POKE_NATIVE_ABI_VERSION;

    guest_memory.bytes = nullptr;
    set_sentinel(memory_result);
    if (poke_native_execute_thumb_memory(&memory_call, &guest_memory, &memory_result)
        != POKE_NATIVE_ABI_INVALID_ARGUMENT || !equals_sentinel(memory_result)) {
        return fail("null guest-memory buffer was not rejected atomically");
    }
    guest_memory.bytes = guest_bytes.data();
    std::cout << "PASS: C++20 memory ABI preserves outputs on contract errors\n";

    std::array<uint8_t, 24> literal_bytes{};
    literal_bytes[8] = UINT8_C(0x78);
    literal_bytes[9] = UINT8_C(0x56);
    literal_bytes[10] = UINT8_C(0x34);
    literal_bytes[11] = UINT8_C(0x12);
    PokeNativeMemory literal_memory{};
    literal_memory.abi_version = POKE_NATIVE_ABI_VERSION;
    literal_memory.guest_base = UINT32_C(0x1000);
    literal_memory.size = static_cast<uint32_t>(literal_bytes.size());
    literal_memory.bytes = literal_bytes.data();
    PokeNativeCall literal_call{};
    literal_call.abi_version = POKE_NATIVE_ABI_VERSION;
    literal_call.entry_address = UINT32_C(0x1000);
    literal_call.registers[1] = UINT32_C(0xAAAAAAAA);
    literal_call.initial_nzcv = UINT8_C(0xB);
    PokeNativeResult literal_result{};
    if (poke_native_execute_thumb_literal_memory(&literal_call, &literal_memory, &literal_result)
        != POKE_NATIVE_ABI_OK
        || literal_result.execution_status != POKE_NATIVE_EXECUTION_RETURNED
        || literal_result.return_value != 0U || literal_result.steps_executed != UINT32_C(3)
        || literal_result.nzcv != UINT8_C(0x7)
        || literal_result.registers[1] != UINT32_C(0x12345678)) {
        return fail("Thumb PC-relative LDR literal failed through the versioned C ABI");
    }
    std::cout << "PASS: C++20 host calls Thumb PC-relative LDR literal through the C ABI\n";

    const auto literal_memory_before_fault = literal_bytes;
    literal_memory.size = UINT32_C(8);
    literal_call.registers[1] = UINT32_C(0xAAAAAAAA);
    set_sentinel(literal_result);
    if (poke_native_execute_thumb_literal_memory(&literal_call, &literal_memory, &literal_result)
        != POKE_NATIVE_ABI_OK
        || literal_result.execution_status != POKE_NATIVE_EXECUTION_MEMORY_FAULT
        || literal_result.steps_executed != UINT32_C(2)
        || literal_result.registers[1] != UINT32_C(0xAAAAAAAA)
        || literal_bytes != literal_memory_before_fault) {
        return fail("literal-load range fault changed the destination register or guest memory");
    }
    literal_memory.size = static_cast<uint32_t>(literal_bytes.size());
    literal_call.entry_address = UINT32_C(0x1001);
    set_sentinel(literal_result);
    if (poke_native_execute_thumb_literal_memory(&literal_call, &literal_memory, &literal_result)
        != POKE_NATIVE_ABI_OK
        || literal_result.execution_status != POKE_NATIVE_EXECUTION_INVALID_STATE
        || literal_result.steps_executed != 0U) {
        return fail("unaligned Thumb entry address was not rejected before execution");
    }
    literal_call.entry_address = UINT32_C(0xFFFFFFFC);
    set_sentinel(literal_result);
    if (poke_native_execute_thumb_literal_memory(&literal_call, &literal_memory, &literal_result)
        != POKE_NATIVE_ABI_OK
        || literal_result.execution_status != POKE_NATIVE_EXECUTION_INVALID_STATE
        || literal_result.steps_executed != UINT32_C(2)) {
        return fail("PC-relative literal PC overflow was not rejected");
    }

    std::array<uint8_t, 24> sp_bytes{};
    sp_bytes.fill(UINT8_C(0xEE));
    PokeNativeMemory sp_memory{};
    sp_memory.abi_version = POKE_NATIVE_ABI_VERSION;
    sp_memory.guest_base = UINT32_C(0x1000);
    sp_memory.size = static_cast<uint32_t>(sp_bytes.size());
    sp_memory.bytes = sp_bytes.data();
    PokeNativeCall sp_call{};
    sp_call.abi_version = POKE_NATIVE_ABI_VERSION;
    sp_call.guest_sp = UINT32_C(0x100C);
    sp_call.registers[0] = UINT32_C(0x5A);
    sp_call.registers[1] = UINT32_C(0x12345678);
    sp_call.registers[2] = UINT32_C(0xAAAAAAAA);
    sp_call.initial_nzcv = UINT8_C(0x9);
    PokeNativeResult sp_result{};
    if (poke_native_execute_thumb_sp_memory(&sp_call, &sp_memory, &sp_result)
        != POKE_NATIVE_ABI_OK
        || sp_result.execution_status != POKE_NATIVE_EXECUTION_RETURNED
        || sp_result.return_value != UINT32_C(0x5A) || sp_result.steps_executed != UINT32_C(3)
        || sp_result.nzcv != UINT8_C(0x9)
        || sp_result.registers[2] != UINT32_C(0x12345678)
        || sp_bytes[16] != UINT8_C(0x78) || sp_bytes[17] != UINT8_C(0x56)
        || sp_bytes[18] != UINT8_C(0x34) || sp_bytes[19] != UINT8_C(0x12)) {
        return fail("SP-relative STR/LDR failed through the versioned C ABI");
    }
    std::cout << "PASS: C++20 host calls Thumb SP-relative STR/LDR through the C ABI\n";
    const auto sp_bytes_before_fault = sp_bytes;
    sp_call.guest_sp = UINT32_C(0x1018);
    sp_call.registers[1] = UINT32_C(0xCAFEBABE);
    sp_call.registers[2] = UINT32_C(0xAAAAAAAA);
    set_sentinel(sp_result);
    if (poke_native_execute_thumb_sp_memory(&sp_call, &sp_memory, &sp_result)
        != POKE_NATIVE_ABI_OK || sp_result.execution_status != POKE_NATIVE_EXECUTION_MEMORY_FAULT
        || sp_result.steps_executed != UINT32_C(1)
        || sp_result.registers[2] != UINT32_C(0xAAAAAAAA) || sp_bytes != sp_bytes_before_fault) {
        return fail("SP-relative out-of-range STR changed guest memory or destination state");
    }
    sp_call.guest_sp = UINT32_C(0x100D);
    set_sentinel(sp_result);
    if (poke_native_execute_thumb_sp_memory(&sp_call, &sp_memory, &sp_result)
        != POKE_NATIVE_ABI_OK || sp_result.execution_status != POKE_NATIVE_EXECUTION_ALIGNMENT_FAULT
        || sp_result.steps_executed != UINT32_C(1) || sp_bytes != sp_bytes_before_fault) {
        return fail("SP-relative misalignment was not rejected atomically");
    }
    sp_call.guest_sp = UINT32_C(0xFFFFFFFC);
    set_sentinel(sp_result);
    if (poke_native_execute_thumb_sp_memory(&sp_call, &sp_memory, &sp_result)
        != POKE_NATIVE_ABI_OK || sp_result.execution_status != POKE_NATIVE_EXECUTION_INVALID_STATE
        || sp_result.steps_executed != UINT32_C(1) || sp_bytes != sp_bytes_before_fault) {
        return fail("SP-relative 32-bit address overflow was not rejected atomically");
    }

    std::array<uint8_t, 24> stack_bytes{};
    stack_bytes.fill(UINT8_C(0xEE));
    PokeNativeMemory stack_memory{};
    stack_memory.abi_version = POKE_NATIVE_ABI_VERSION;
    stack_memory.guest_base = UINT32_C(0x1000);
    stack_memory.size = static_cast<uint32_t>(stack_bytes.size());
    stack_memory.bytes = stack_bytes.data();
    PokeNativeCall stack_call{};
    stack_call.abi_version = POKE_NATIVE_ABI_VERSION;
    stack_call.guest_sp = UINT32_C(0x1018);
    stack_call.guest_lr = UINT32_C(0xAABBCCDD);
    stack_call.registers[0] = UINT32_C(0x11223344);
    stack_call.registers[1] = UINT32_C(0x55667788);
    stack_call.registers[2] = UINT32_C(0xAAAAAAAA);
    stack_call.registers[3] = UINT32_C(0xBBBBBBBB);
    stack_call.initial_nzcv = UINT8_C(0x9);
    PokeNativeResult stack_result{};
    if (poke_native_execute_thumb_stack_memory(&stack_call, &stack_memory, &stack_result)
        != POKE_NATIVE_ABI_OK
        || stack_result.execution_status != POKE_NATIVE_EXECUTION_RETURNED
        || stack_result.return_value != UINT32_C(0x11223344)
        || stack_result.steps_executed != UINT32_C(3)
        || stack_result.guest_sp != UINT32_C(0x1014)
        || stack_result.registers[2] != UINT32_C(0x11223344)
        || stack_result.registers[3] != UINT32_C(0x55667788)
        || stack_bytes[12] != UINT8_C(0x44) || stack_bytes[13] != UINT8_C(0x33)
        || stack_bytes[14] != UINT8_C(0x22) || stack_bytes[15] != UINT8_C(0x11)
        || stack_bytes[16] != UINT8_C(0x88) || stack_bytes[17] != UINT8_C(0x77)
        || stack_bytes[18] != UINT8_C(0x66) || stack_bytes[19] != UINT8_C(0x55)
        || stack_bytes[20] != UINT8_C(0xDD) || stack_bytes[21] != UINT8_C(0xCC)
        || stack_bytes[22] != UINT8_C(0xBB) || stack_bytes[23] != UINT8_C(0xAA)) {
        return fail("Thumb PUSH/POP did not preserve order, LR or final SP through the C ABI");
    }
    std::cout << "PASS: C++20 host calls Thumb PUSH/POP through the versioned C ABI\n";
    const auto stack_bytes_before_fault = stack_bytes;
    for (uint32_t bad_sp : {UINT32_C(8), UINT32_C(0x1019), UINT32_C(0x1008)}) {
        stack_call.guest_sp = bad_sp;
        set_sentinel(stack_result);
        if (poke_native_execute_thumb_stack_memory(&stack_call, &stack_memory, &stack_result)
            != POKE_NATIVE_ABI_OK || stack_result.guest_sp != bad_sp
            || stack_result.steps_executed != UINT32_C(1)
            || stack_result.execution_status != (bad_sp == UINT32_C(8)
                ? POKE_NATIVE_EXECUTION_INVALID_STATE
                : bad_sp == UINT32_C(0x1019) ? POKE_NATIVE_EXECUTION_ALIGNMENT_FAULT
                : POKE_NATIVE_EXECUTION_MEMORY_FAULT)
            || stack_bytes != stack_bytes_before_fault) {
            return fail("failed Thumb PUSH changed SP or guest memory");
        }
    }
    stack_call.guest_sp = UINT32_C(0xFFFFFFFC);
    set_sentinel(stack_result);
    if (poke_native_execute_thumb_stack_pop_overflow_memory(&stack_call, &stack_memory, &stack_result)
        != POKE_NATIVE_ABI_OK || stack_result.guest_sp != UINT32_C(0xFFFFFFFC)
        || stack_result.steps_executed != UINT32_C(1)
        || stack_result.execution_status != POKE_NATIVE_EXECUTION_INVALID_STATE
        || stack_bytes != stack_bytes_before_fault) {
        return fail("Thumb POP SP overflow changed SP or guest memory");
    }

    stack_call.guest_sp = UINT32_C(0x1018);
    set_sentinel(stack_result);
    if (poke_native_execute_thumb_stack_adjust_memory(&stack_call, &stack_memory, &stack_result)
        != POKE_NATIVE_ABI_OK || stack_result.guest_sp != UINT32_C(0x1018)
        || stack_result.steps_executed != UINT32_C(3)
        || stack_result.execution_status != POKE_NATIVE_EXECUTION_RETURNED
        || stack_result.return_value != stack_call.registers[0]
        || stack_result.nzcv != stack_call.initial_nzcv
        || stack_bytes != stack_bytes_before_fault) {
        return fail("Thumb ADD/SUB SP did not restore SP or preserve flags/memory through the C ABI");
    }
    stack_call.guest_sp = UINT32_C(4);
    set_sentinel(stack_result);
    if (poke_native_execute_thumb_sp_sub_underflow_memory(&stack_call, &stack_memory, &stack_result)
        != POKE_NATIVE_ABI_OK || stack_result.guest_sp != UINT32_C(4)
        || stack_result.steps_executed != UINT32_C(1)
        || stack_result.execution_status != POKE_NATIVE_EXECUTION_INVALID_STATE
        || stack_bytes != stack_bytes_before_fault) {
        return fail("Thumb SUB SP underflow changed SP or guest memory");
    }
    stack_call.guest_sp = UINT32_C(0xFFFFFFFC);
    set_sentinel(stack_result);
    if (poke_native_execute_thumb_sp_add_overflow_memory(&stack_call, &stack_memory, &stack_result)
        != POKE_NATIVE_ABI_OK || stack_result.guest_sp != UINT32_C(0xFFFFFFFC)
        || stack_result.steps_executed != UINT32_C(1)
        || stack_result.execution_status != POKE_NATIVE_EXECUTION_INVALID_STATE
        || stack_bytes != stack_bytes_before_fault) {
        return fail("Thumb ADD SP overflow changed SP or guest memory");
    }

    guest_bytes.fill(UINT8_C(0xEE));
    PokeNativeCall multiple_call{};
    multiple_call.abi_version = POKE_NATIVE_ABI_VERSION;
    multiple_call.registers[0] = UINT32_C(0x1010);
    multiple_call.registers[1] = UINT32_C(0x11223344);
    multiple_call.registers[2] = UINT32_C(0x55667788);
    multiple_call.registers[3] = UINT32_C(0x1010);
    multiple_call.registers[4] = UINT32_C(0xAAAAAAAA);
    multiple_call.registers[5] = UINT32_C(0xBBBBBBBB);
    multiple_call.registers[6] = UINT32_C(0xCCCCCCCC);
    multiple_call.registers[7] = UINT32_C(0xDDDDDDDD);
    multiple_call.initial_nzcv = UINT8_C(0x9);
    set_sentinel(memory_result);
    if (poke_native_execute_thumb_multiple_memory(&multiple_call, &guest_memory, &memory_result)
        != POKE_NATIVE_ABI_OK) {
        return fail("LDMIA/STMIA call through the C ABI returned an error");
    }
    if (memory_result.abi_version != POKE_NATIVE_ABI_VERSION
        || memory_result.return_value != UINT32_C(0x1018)
        || memory_result.steps_executed != UINT32_C(3)
        || memory_result.nzcv != UINT8_C(0x9)
        || memory_result.execution_status != POKE_NATIVE_EXECUTION_RETURNED
        || memory_result.registers[0] != UINT32_C(0x1018)
        || memory_result.registers[1] != UINT32_C(0x11223344)
        || memory_result.registers[2] != UINT32_C(0x55667788)
        || memory_result.registers[3] != UINT32_C(0x1018)
        || memory_result.registers[4] != UINT32_C(0x11223344)
        || memory_result.registers[5] != UINT32_C(0x55667788)
        || memory_result.registers[6] != multiple_call.registers[6]
        || memory_result.registers[7] != multiple_call.registers[7]) {
        return fail("LDMIA/STMIA C ABI result/write-back mismatch");
    }
    if (guest_bytes[16] != UINT8_C(0x44) || guest_bytes[17] != UINT8_C(0x33)
        || guest_bytes[18] != UINT8_C(0x22) || guest_bytes[19] != UINT8_C(0x11)
        || guest_bytes[20] != UINT8_C(0x88) || guest_bytes[21] != UINT8_C(0x77)
        || guest_bytes[22] != UINT8_C(0x66) || guest_bytes[23] != UINT8_C(0x55)) {
        return fail("LDMIA/STMIA C ABI memory bytes mismatch");
    }
    std::cout << "PASS: C++20 host calls native Thumb LDMIA/STMIA through the C ABI\n";

    const auto multiple_memory_before_fault = guest_bytes;
    multiple_call.registers[0] = UINT32_C(0x1018);
    multiple_call.initial_nzcv = UINT8_C(0x6);
    set_sentinel(memory_result);
    if (poke_native_execute_thumb_multiple_memory(&multiple_call, &guest_memory, &memory_result)
        != POKE_NATIVE_ABI_OK
        || memory_result.execution_status != POKE_NATIVE_EXECUTION_MEMORY_FAULT
        || memory_result.steps_executed != UINT32_C(1)
        || memory_result.nzcv != UINT8_C(0x6)
        || guest_bytes != multiple_memory_before_fault) {
        return fail("LDMIA/STMIA C ABI range fault did not preserve the guest region");
    }
    multiple_call.registers[0] = UINT32_C(0x1011);
    set_sentinel(memory_result);
    if (poke_native_execute_thumb_multiple_memory(&multiple_call, &guest_memory, &memory_result)
        != POKE_NATIVE_ABI_OK
        || memory_result.execution_status != POKE_NATIVE_EXECUTION_ALIGNMENT_FAULT
        || memory_result.steps_executed != UINT32_C(1)
        || guest_bytes != multiple_memory_before_fault) {
        return fail("LDMIA/STMIA C ABI alignment fault did not preserve the guest region");
    }

    guest_bytes[0] = UINT8_C(0x78);
    guest_bytes[1] = UINT8_C(0x56);
    guest_bytes[2] = UINT8_C(0x34);
    guest_bytes[3] = UINT8_C(0x12);
    PokeNativeCall ldm_base_call{};
    ldm_base_call.abi_version = POKE_NATIVE_ABI_VERSION;
    ldm_base_call.registers[0] = UINT32_C(0x1000);
    ldm_base_call.initial_nzcv = UINT8_C(0x5);
    set_sentinel(memory_result);
    if (poke_native_execute_thumb_ldmia_base_list(&ldm_base_call, &guest_memory, &memory_result)
        != POKE_NATIVE_ABI_OK
        || memory_result.execution_status != POKE_NATIVE_EXECUTION_RETURNED
        || memory_result.return_value != UINT32_C(0x12345678)
        || memory_result.registers[0] != UINT32_C(0x12345678)
        || memory_result.steps_executed != UINT32_C(2)
        || memory_result.nzcv != UINT8_C(0x5)) {
        return fail("LDMIA with base in register list did not suppress write-back");
    }
    std::cout << "PASS: C++20 host validates LDMIA base-in-list write-back rule\n";



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
