#ifndef POKEULTRARECOMP_NATIVE_ABI_H
#define POKEULTRARECOMP_NATIVE_ABI_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define POKE_NATIVE_ABI_VERSION UINT32_C(1)
#define POKE_NATIVE_REGISTER_COUNT 8U

typedef enum PokeNativeAbiStatus {
    POKE_NATIVE_ABI_OK = 0,
    POKE_NATIVE_ABI_INVALID_ARGUMENT = 1,
    POKE_NATIVE_ABI_VERSION_MISMATCH = 2,
    POKE_NATIVE_ABI_EXECUTION_FAILED = 3
} PokeNativeAbiStatus;

/* Stable, versioned boundary between generated C units and the C++20 host. */
typedef struct PokeNativeCall {
    uint32_t abi_version;
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

/* The two entries below are only generated synthetic fixtures used by tests. */
int poke_native_execute_a32(const PokeNativeCall *call, PokeNativeResult *result);
int poke_native_execute_thumb(const PokeNativeCall *call, PokeNativeResult *result);

#ifdef __cplusplus
}
#endif

#endif /* POKEULTRARECOMP_NATIVE_ABI_H */
