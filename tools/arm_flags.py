"""Small, explicit ARM A32 NZCV flag model for synthetic tests.

This module is deliberately independent of the ARM-to-C translator. It models
only 32-bit arithmetic/logical flag semantics; it does not decode instructions,
model the full CPSR, or add flag-setting opcodes to POC-001.
"""
from __future__ import annotations

from dataclasses import dataclass

UINT32_MASK = 0xFFFFFFFF
SIGN_BIT = 0x80000000
INT32_MIN = -(1 << 31)
INT32_MAX = (1 << 31) - 1


def _require_u32(value: int, name: str) -> int:
    if type(value) is not int or not 0 <= value <= UINT32_MASK:
        raise ValueError(f"{name} must be an integer in uint32 range")
    return value


def _require_bit(value: int, name: str) -> int:
    if type(value) is not int or value not in (0, 1):
        raise ValueError(f"{name} must be 0 or 1")
    return value


def _signed32(value: int) -> int:
    return value - (1 << 32) if value & SIGN_BIT else value


@dataclass(frozen=True, slots=True)
class NZCV:
    """ARM condition flags: negative, zero, carry/no-borrow, overflow."""

    n: bool = False
    z: bool = False
    c: bool = False
    v: bool = False

    def __post_init__(self) -> None:
        for name in ("n", "z", "c", "v"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name.upper()} flag must be bool")

    @property
    def nibble(self) -> int:
        """Return NZCV as a four-bit integer, with N as the most significant bit."""
        return (int(self.n) << 3) | (int(self.z) << 2) | (int(self.c) << 1) | int(self.v)


def add_with_flags(lhs: int, rhs: int, carry_in: int = 0) -> tuple[int, NZCV]:
    """Compute uint32 addition and its NZCV flags, optionally including carry-in."""
    lhs = _require_u32(lhs, "lhs")
    rhs = _require_u32(rhs, "rhs")
    carry_in = _require_bit(carry_in, "carry_in")

    total = lhs + rhs + carry_in
    result = total & UINT32_MASK
    signed_total = _signed32(lhs) + _signed32(rhs) + carry_in
    flags = NZCV(
        n=bool(result & SIGN_BIT),
        z=(result == 0),
        c=(total > UINT32_MASK),
        v=(signed_total < INT32_MIN or signed_total > INT32_MAX),
    )
    return result, flags


def sub_with_flags(lhs: int, rhs: int, borrow_in: int = 0) -> tuple[int, NZCV]:
    """Compute uint32 subtraction and NZCV; C is set when no unsigned borrow occurs."""
    lhs = _require_u32(lhs, "lhs")
    rhs = _require_u32(rhs, "rhs")
    borrow_in = _require_bit(borrow_in, "borrow_in")

    subtrahend = rhs + borrow_in
    signed_total = _signed32(lhs) - _signed32(rhs) - borrow_in
    result = (lhs - subtrahend) & UINT32_MASK
    flags = NZCV(
        n=bool(result & SIGN_BIT),
        z=(result == 0),
        c=(lhs >= subtrahend),
        v=(signed_total < INT32_MIN or signed_total > INT32_MAX),
    )
    return result, flags


def logical_flags(
    result: int,
    previous: NZCV,
    *,
    shifter_carry: bool | None = None,
) -> NZCV:
    """Calculate logical-operation N/Z and preserve V and normally C.

    Pass shifter_carry when the operand shifter explicitly produces a new
    carry bit. None means carry is preserved from the prior NZCV state.
    """
    result = _require_u32(result, "result")
    if not isinstance(previous, NZCV):
        raise ValueError("previous must be an NZCV instance")
    if shifter_carry is not None and type(shifter_carry) is not bool:
        raise ValueError("shifter_carry must be bool or None")
    return NZCV(
        n=bool(result & SIGN_BIT),
        z=(result == 0),
        c=previous.c if shifter_carry is None else shifter_carry,
        v=previous.v,
    )
