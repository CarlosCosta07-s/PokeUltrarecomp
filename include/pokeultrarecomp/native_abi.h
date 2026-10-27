#ifndef POKEULTRARECOMP_NATIVE_ABI_H
#define POKEULTRARECOMP_NATIVE_ABI_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define POKE_NATIVE_ABI_VERSION UINT32_C(2)
#define POKE_NATIVE_REGISTER_COUNT 8U

typedef enum PokeNativeAbiStatus {
    POKE_NATIVE_ABI_OK = 0,
    POKE_NATIVE_ABI_INVALID_ARGUMENT = 1,
    POKE_NATIVE_ABI_VERSION_MISMATCH = 2,
    POKE_NATIVE_ABI_EXECUTION_FAILED = 3
} PokeNativeAbiStatus;

typedef enum PokeNativeExecutionStatus {
    POKE_NATIVE_EXECUTION_RETURNED = 0,
    POKE_NATIVE_EXECUTION_BUDGET_EXHAUSTED = 1,
    POKE_NATIVE_EXECUTION_INVALID_STATE = 2,
    POKE_NATIVE_EXECUTION_MEMORY_FAULT = 3,
    POKE_NATIVE_EXECUTION_ALIGNMENT_FAULT = 4
} PokeNativeExecutionStatus;

/* Stable, versioned boundary between generated C units and the C++20 host. */
typedef struct PokeNativeCall {
    uint32_t abi_version;
    uint32_t entry_address; /* Guest Thumb entry address; used by PC-relative literal loads. */
    uint32_t registers[POKE_NATIVE_REGISTER_COUNT];
    uint8_t initial_nzcv;
} PokeNativeCall;

typedef struct PokeNativeResult {
    uint32_t abi_version;
    uint32_t registers[POKE_NATIVE_REGISTER_COUNT];
    uint32_t return_value;
    uint32_t steps_executed;
    uint8_t nzcv;
    uint8_t execution_status;
} PokeNativeResult;

/* Test-only view of a bounded guest-address region, not a real game memory map. */
typedef struct PokeNativeMemory {
    uint32_t abi_version;
    uint32_t guest_base;
    uint32_t size;
    uint8_t *bytes;
} PokeNativeMemory;

/* These entries bind generated synthetic fixtures to the stable C ABI. */
int poke_native_execute_a32(const PokeNativeCall *call, PokeNativeResult *result);
int poke_native_execute_thumb(const PokeNativeCall *call, PokeNativeResult *result);
int poke_native_execute_thumb_memory(
    const PokeNativeCall *call,
    const PokeNativeMemory *memory,
    PokeNativeResult *result
);
int poke_native_execute_thumb_multiple_memory(
    const PokeNativeCall *call,
    const PokeNativeMemory *memory,
    PokeNativeResult *result
);
int poke_native_execute_thumb_ldmia_base_list(
    const PokeNativeCall *call,
    const PokeNativeMemory *memory,
    PokeNativeResult *result
);
int poke_native_execute_thumb_literal_memory(
    const PokeNativeCall *call,
    const PokeNativeMemory *memory,
    PokeNativeResult *result
);

#ifdef __cplusplus
}
#endif

#endif /* POKEULTRARECOMP_NATIVE_ABI_H */
