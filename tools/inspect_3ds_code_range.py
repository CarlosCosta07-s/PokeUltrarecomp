#!/usr/bin/env python3
"""Decode a fixed, user-selected range in a local decompressed 3DS .code file."""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import arm_subset_poc as arm  # noqa: E402
import inspect_3ds_target as intake  # noqa: E402
import thumb_subset_poc as thumb  # noqa: E402
import arm_thumb_cfg as cfg  # noqa: E402
import arm_thumb_effects as effects  # noqa: E402


class TargetRangeError(ValueError):
    """The selected range is outside this tool's explicit scope."""


def parse_address(token: str) -> int:
    try:
        value = int(token, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"expected a numeric address, preferably hexadecimal with 0x prefix: {token!r}"
        ) from exc
    if not 0 <= value < (1 << 32):
        raise argparse.ArgumentTypeError("address must fit uint32")
    return value


def decode_arm_for_inspection(word: int) -> tuple[object, ...]:
    """Decode a few A32 control-flow/literal forms for inspection only.

    These forms are intentionally not enabled in the synthetic C translator:
    they need broader state/ABI semantics before recompilation is safe.
    """
    if word == 0xE12FFF1E:
        return arm.decode_word(word)

    condition = (word >> 28) & 0xF
    branch_class = (word >> 25) & 0b111
    if branch_class == 0b101:
        imm24 = word & 0x00FFFFFF
        if condition == 0xF:
            # A32 BLX immediate: SignExtend(imm24:H:'0', 32), target state T32.
            offset = (imm24 << 2) | (((word >> 24) & 1) << 1)
            if offset & (1 << 25):
                offset -= 1 << 26
            return ("call", "blx", offset)
        if (word >> 24) & 1:
            if condition != 0xE:
                raise arm.UnsupportedInstruction(
                    "conditional A32 BL is not yet interpreted by the range inspector"
                )
            # B/BL uses PC = current instruction address + 8.
            if imm24 & (1 << 23):
                imm24 -= 1 << 24
            return ("call", "bl", imm24 << 2)

    if condition == 0xE and ((word >> 25) & 0b111) == 0b100:
        preindexed = ((word >> 24) & 1) == 1
        increment = ((word >> 23) & 1) == 1
        status_update = ((word >> 22) & 1) == 1
        writeback = ((word >> 21) & 1) == 1
        load = ((word >> 20) & 1) == 1
        rn = (word >> 16) & 0xF
        register_mask = word & 0xFFFF
        if rn == 13 and writeback and not status_update:
            if preindexed and not increment and not load:
                if register_mask == 0 or register_mask & ((1 << 13) | (1 << 15)):
                    raise arm.UnsupportedInstruction(
                        "A32 STMDB sp! register list is empty or includes SP/PC"
                    )
                return ("arm_push", register_mask)
            if not preindexed and increment and load:
                if register_mask == 0 or register_mask & (1 << 13):
                    raise arm.UnsupportedInstruction(
                        "A32 LDMIA sp! register list is empty or includes SP"
                    )
                return ("arm_pop", register_mask)

    if condition == 0xE:
        special = word & 0x0FFFFFF0
        rm = word & 0xF
        if special == 0x012FFF10:
            if rm == 15:
                raise arm.UnsupportedInstruction("BX with Rm=PC is not decoded by this inspector")
            return ("bx", rm)
        if special == 0x012FFF30:
            if rm == 15:
                raise arm.UnsupportedInstruction("BLX register with Rm=PC is not decoded by this inspector")
            return ("blx_reg", rm)

        # A32 LDR (literal), word form: P=1, B=0, W=0, L=1, Rn=PC,
        # immediate offset. Reject Rt=PC here because it is an indirect branch.
        if ((word >> 26) & 0b11) == 0b01:
            immediate_form = ((word >> 25) & 1) == 0
            preindexed = ((word >> 24) & 1) == 1
            add_offset = ((word >> 23) & 1) == 1
            byte_transfer = ((word >> 22) & 1) == 1
            writeback = ((word >> 21) & 1) == 1
            load = ((word >> 20) & 1) == 1
            rn = (word >> 16) & 0xF
            rd = (word >> 12) & 0xF
            if immediate_form and preindexed and not byte_transfer and not writeback and load and rn == 15:
                if rd == 15:
                    raise arm.UnsupportedInstruction(
                        "LDR literal into PC is an indirect branch and is not yet decoded"
                    )
                offset = word & 0xFFF
                if not add_offset:
                    offset = -offset
                return ("ldr_literal", rd, offset)

    return arm.decode_word(word)


def mnemonic_for(state: str, decoded: tuple[object, ...]) -> str:
    if decoded == ("return",):
        return "BX LR"
    if decoded[0] == "branch":
        cond = decoded[1]
        return "B" if cond == "al" else f"B{str(cond).upper()}"
    if decoded[0] == "call":
        return str(decoded[1]).upper()
    if decoded[0] == "ldr_literal":
        return f"LDR r{decoded[1]}, [pc, #{decoded[2]}]"
    if decoded[0] == "bx":
        return f"BX r{decoded[1]}"
    if decoded[0] == "blx_reg":
        return f"BLX r{decoded[1]}"
    if decoded[0] in ("pop_pc", "pop", "push"):
        regs = [f"r{n}" for n in range(8) if int(decoded[1]) >> n & 1]
        if decoded[0] == "pop_pc":
            regs.append("pc")
        elif decoded[0] == "push" and decoded[2]:
            regs.append("lr")
        return ("PUSH {" if decoded[0] == "push" else "POP {") + ", ".join(regs) + "}"
    if state == "arm" and decoded[0] in ("arm_push", "arm_pop"):
        register_mask = int(decoded[1])
        names = {13: "sp", 14: "lr", 15: "pc"}
        registers = [names.get(number, f"r{number}") for number in range(16) if register_mask & (1 << number)]
        operation = "STMDB" if decoded[0] == "arm_push" else "LDMIA"
        return f"{operation} sp!, {{{', '.join(registers)}}}"
    cond = None
    inst = decoded
    if decoded[0] == "predicated":
        _, cond, inst = decoded
    op = str(inst[0])
    names = {
        "mov": "MOV", "mvn": "MVN", "add": "ADD", "sub": "SUB",
        "and": "AND", "orr": "ORR", "eor": "EOR", "bic": "BIC",
        "adds": "ADDS", "subs": "SUBS", "cmp": "CMP", "cmn": "CMN",
        "movs": "MOVS", "adds_reg": "ADDS", "subs_reg": "SUBS",
        "adds_imm3": "ADDS", "subs_imm3": "SUBS",
        "lsl_imm": "LSL", "lsr_imm": "LSR", "asr_imm": "ASR",
        "ands_reg": "ANDS", "eors_reg": "EORS", "orrs_reg": "ORRS",
        "lsls_reg": "LSLS", "lsrs_reg": "LSRS", "asrs_reg": "ASRS", "rors_reg": "RORS",
        "adcs_reg": "ADCS", "sbcs_reg": "SBCS", "muls_reg": "MULS",
        "cmp_reg": "CMP", "cmn_reg": "CMN",
        "rsbs_zero": "RSBS",
        "bics_reg": "BICS", "mvns_reg": "MVNS", "tst_reg": "TST",
        "str_reg": "STR", "strh_reg": "STRH", "strb_reg": "STRB",
        "ldrsb_reg": "LDRSB", "ldr_reg": "LDR", "ldrh_reg": "LDRH",
        "ldrb_reg": "LDRB", "ldrsh_reg": "LDRSH",
        "str_imm": "STR", "ldr_imm": "LDR", "strb_imm": "STRB",
        "ldrb_imm": "LDRB", "strh_imm": "STRH", "ldrh_imm": "LDRH",
        "str_sp": "STR", "ldr_sp": "LDR",
        "stmia": "STMIA", "ldmia": "LDMIA",
        "adr": "ADR", "add_sp_imm": "ADD", "add_sp": "ADD", "sub_sp": "SUB",
    }
    name = names.get(op)
    if name is None:
        raise TargetRangeError(f"unsupported decoded operation {op!r}")
    if cond is not None:
        name += str(cond).upper()
    if op in ("mov", "mvn", "movs", "cmp", "cmn"):
        return f"{name} r{inst[1]}, #{inst[2]}"
    if state == "thumb" and op in ("adds", "subs"):
        return f"{name} r{inst[1]}, #{inst[2]}"
    if state == "thumb" and op in ("adds_imm3", "subs_imm3"):
        return f"{name} r{inst[1]}, r{inst[2]}, #{inst[3]}"
    if state == "thumb" and op in ("lsl_imm", "lsr_imm", "asr_imm"):
        return f"{name} r{inst[1]}, r{inst[2]}, #{inst[3]}"
    if state == "thumb" and op in (
        "ands_reg", "eors_reg", "lsls_reg", "lsrs_reg", "asrs_reg", "rors_reg",
        "adcs_reg", "sbcs_reg", "orrs_reg", "muls_reg", "bics_reg", "mvns_reg", "tst_reg",
    ):
        return f"{name} r{inst[1]}, r{inst[2]}"
    if state == "thumb" and op in ("stmia", "ldmia"):
        base_register, register_mask = int(inst[1]), int(inst[2])
        registers = [f"r{n}" for n in range(8) if (register_mask >> n) & 1]
        writeback = not (op == "ldmia" and ((register_mask >> base_register) & 1))
        suffix = "!" if writeback else ""
        register_list_text = ", ".join(registers)
        return f"{name} r{base_register}{suffix}, {{{register_list_text}}}"
    if state == "thumb" and op in (
        "str_reg", "strh_reg", "strb_reg", "ldrsb_reg", "ldr_reg",
        "ldrh_reg", "ldrb_reg", "ldrsh_reg",
    ):
        return f"{name} r{inst[1]}, [r{inst[2]}, r{inst[3]}]"
    if state == "thumb" and op in (
        "str_imm", "ldr_imm", "strb_imm", "ldrb_imm", "strh_imm", "ldrh_imm",
    ):
        return f"{name} r{inst[1]}, [r{inst[2]}, #{inst[3]}]"
    if state == "thumb" and op in ("str_sp", "ldr_sp"):
        return f"{name} r{inst[1]}, [sp, #{inst[2]}]"
    if state == "thumb" and op == "adr":
        return f"ADR r{inst[1]}, [pc, #{inst[2]}]"
    if state == "thumb" and op == "add_sp_imm":
        return f"ADD r{inst[1]}, sp, #{inst[2]}"
    if state == "thumb" and op in ("add_sp", "sub_sp"):
        return f"{name} sp, #{inst[1]}"
    if state == "thumb" and op in ("cmp_reg", "cmn_reg"):
        return f"{name} r{inst[1]}, r{inst[2]}"
    if state == "thumb" and op == "rsbs_zero":
        return f"{name} r{inst[1]}, r{inst[2]}, #0"
    if state == "thumb" and op in ("adds_reg", "subs_reg"):
        return f"{name} r{inst[1]}, r{inst[2]}, r{inst[3]}"
    if op in ("add", "sub", "and", "orr", "eor", "bic", "adds", "subs"):
        return f"{name} r{inst[1]}, r{inst[2]}, #{inst[3]}"
    raise TargetRangeError(f"could not format decoded operation {decoded!r}")


def memory_access_metadata(decoded: tuple[object, ...]) -> dict[str, Any]:
    """Describe a Thumb memory encoding without resolving runtime register values."""
    if not decoded or decoded[0] not in thumb.MEMORY_OPS:
        raise TargetRangeError(f"not a decoded Thumb memory access: {decoded!r}")
    op = str(decoded[0])
    width_by_op = {
        "str_reg": 4, "ldr_reg": 4, "str_imm": 4, "ldr_imm": 4, "str_sp": 4, "ldr_sp": 4,
        "strh_reg": 2, "ldrh_reg": 2, "strh_imm": 2, "ldrh_imm": 2, "ldrsh_reg": 2,
        "strb_reg": 1, "ldrb_reg": 1, "strb_imm": 1, "ldrb_imm": 1, "ldrsb_reg": 1,
        "stmia": 4, "ldmia": 4,
    }
    record: dict[str, Any] = {
        "direction": "store" if (op.startswith("str") or op == "stmia") else "load",
        "width_bytes": width_by_op[op],
        "sign_extend": op in ("ldrsb_reg", "ldrsh_reg"),
        "runtime_effective_address_resolved": False,
        "memory_value_read_by_inspector": False,
    }
    if op in ("stmia", "ldmia"):
        base_register = int(decoded[1])
        register_mask = int(decoded[2])
        registers = [f"r{n}" for n in range(8) if (register_mask >> n) & 1]
        base_in_list = bool((register_mask >> base_register) & 1)
        record.update({
            "addressing_mode": "multiple-increment-after",
            "base_register": f"r{base_register}",
            "offset_register": None,
            "offset_bytes": 0,
            "registers": registers,
            "transfer_count": len(registers),
            "total_bytes": len(registers) * 4,
            "base_register_in_list": base_in_list,
            "base_register_writeback": not (op == "ldmia" and base_in_list),
            "base_register_stored_value_unknown": bool(
                op == "stmia" and base_in_list and register_mask & -register_mask != (1 << base_register)
            ),
        })
    elif op.endswith("_reg"):
        record.update({
            "addressing_mode": "register-offset",
            "base_register": f"r{decoded[2]}",
            "offset_register": f"r{decoded[3]}",
            "offset_bytes": None,
        })
    elif op.endswith("_sp"):
        record.update({
            "addressing_mode": "sp-relative",
            "base_register": "sp",
            "offset_register": None,
            "offset_bytes": int(decoded[2]),
        })
    else:
        record.update({
            "addressing_mode": "immediate-offset",
            "base_register": f"r{decoded[2]}",
            "offset_register": None,
            "offset_bytes": int(decoded[3]),
        })
    return record

def inspect_code_range(
    target_id: str,
    exheader_path: Path,
    code_path: Path,
    state: str,
    start_address: int,
    instruction_count: int,
    *,
    title_id: str | None = None,
    allow_unverified_target: bool = False,
    include_unsupported: bool = False,
) -> dict[str, Any]:
    """Decode a user-selected instruction range inside declared .text.

    With include_unsupported=True, unknown instructions are recorded as raw
    encodings. Thumb-2 prefix halfwords consume two halfwords as one unknown
    32-bit instruction so the remainder of the range stays aligned.
    """
    if state not in ("arm", "thumb"):
        raise TargetRangeError("instruction state must be 'arm' or 'thumb'")
    if isinstance(instruction_count, bool) or not isinstance(instruction_count, int):
        raise TargetRangeError("instruction count must be an integer")
    if not 1 <= instruction_count <= 256:
        raise TargetRangeError("instruction count must be in 1..256")
    if isinstance(start_address, bool) or not isinstance(start_address, int) or not 0 <= start_address < (1 << 32):
        raise TargetRangeError("start address must fit uint32")
    unit = 4 if state == "arm" else 2
    if start_address % unit:
        raise TargetRangeError(f"start address 0x{start_address:08X} is not aligned for {state.upper()}")

    try:
        checked = intake.inspect_target(target_id, exheader_path, code_path, title_id=title_id)
    except intake.TargetInspectionError as exc:
        raise TargetRangeError(str(exc)) from exc
    program_match = checked["identity"]["program_id_match"]
    if program_match != "matched" and not allow_unverified_target:
        raise TargetRangeError(
            "ExHeader Program ID is unrecognized; use the matching executable or explicitly pass "
            "--allow-unverified-target after verifying the local input"
        )

    text = next(segment for segment in checked["memory"]["segments"] if segment["name"] == "text")
    text_start = int(text["virtual_address"])
    text_size = int(text["declared_size_bytes"])
    relative = start_address - text_start
    if relative < 0 or relative >= text_size:
        raise TargetRangeError(
            f"start address 0x{start_address:08X} lies outside declared .text "
            f"0x{text_start:08X}..0x{text_start + text_size:08X}"
        )
    if relative + unit > text_size:
        raise TargetRangeError(
            f"requested range extends beyond declared .text payload ({text_size} bytes); page padding is not code"
        )

    try:
        code = code_path.read_bytes()
    except OSError as exc:
        raise TargetRangeError(f"cannot read local .code file: {exc}") from exc
    if hashlib.sha256(code).hexdigest() != checked["inputs"]["decompressed_code"]["sha256"]:
        raise TargetRangeError(".code changed during inspection; retry with a stable local file")
    file_offset = int(text["code_file_offset"]) + relative

    instructions: list[dict[str, Any]] = []
    cursor = 0
    index = 0
    while index < instruction_count:
        if relative + cursor + unit > text_size:
            raise TargetRangeError(
                f"requested range extends beyond declared .text payload ({text_size} bytes); page padding is not code"
            )
        absolute_offset = file_offset + cursor
        unit_bytes = code[absolute_offset:absolute_offset + unit]
        if len(unit_bytes) != unit:
            raise TargetRangeError("selected range is truncated in .code")
        word = int.from_bytes(unit_bytes, "little")
        address = start_address + cursor
        instruction_size = unit
        unknown_reason: str | None = None
        thumb32_second: int | None = None
        is_thumb32 = state == "thumb" and (word & 0xF800) in (0xE800, 0xF000, 0xF800)
        if is_thumb32:
            instruction_size = 4
            if relative + cursor + instruction_size > text_size:
                raise TargetRangeError(
                    f"32-bit Thumb instruction prefix at 0x{address:08X} crosses the declared .text boundary"
                )
            second_offset = absolute_offset + 2
            second_bytes = code[second_offset:second_offset + 2]
            if len(second_bytes) != 2:
                raise TargetRangeError(f"truncated 32-bit Thumb instruction at 0x{address:08X}")
            thumb32_second = int.from_bytes(second_bytes, "little")
            try:
                decoded = thumb.decode_call_pair(word, thumb32_second)
                call_target, call_state = thumb.call_target(address, decoded)
            except thumb.UnsupportedThumbInstruction as exc:
                unknown_reason = (
                    "32-bit Thumb pair is not a decodable ARMv6K BL/BLX immediate: " + str(exc)
                )
            else:
                instructions.append({
                    "index": index,
                    "virtual_address": f"0x{address:08X}",
                    "decompressed_code_file_offset": absolute_offset,
                    "instruction_size_bytes": instruction_size,
                    "encoding": f"0x{word:04X} 0x{thumb32_second:04X}",
                    "halfwords": [f"0x{word:04X}", f"0x{thumb32_second:04X}"],
                    "decode_status": "decoded",
                    "mnemonic": mnemonic_for(state, decoded),
                    "decoded_ir": decoded,
                    "branch_links": True,
                    "link_register_value": f"0x{(address + 4) | 1:08X}",
                    "branch_target_virtual_address": f"0x{call_target:08X}",
                    "branch_target_state": call_state,
                    "branch_target_within_declared_text": text_start <= call_target < text_start + text_size,
                })
                cursor += instruction_size
                index += 1
                continue
        else:
            call_target: int | None = None
            call_target_state = state
            try:
                decoded = decode_arm_for_inspection(word) if state == "arm" else thumb.decode_halfword(word)
                mnemonic = mnemonic_for(state, decoded)
                if state == "arm" and decoded[0] == "call":
                    call_target = address + 8 + int(decoded[2])
                    if not 0 <= call_target < (1 << 32):
                        raise TargetRangeError(
                            f"A32 call target from 0x{address:08X} lies outside the 32-bit address space"
                        )
                    if address + 4 >= (1 << 32):
                        raise TargetRangeError(
                            f"A32 call return address from 0x{address:08X} lies outside the 32-bit address space"
                        )
                    call_target_state = "thumb" if decoded[1] == "blx" else "arm"

                literal = None
                if state == "thumb" and decoded[0] == "ldr_literal":
                    literal = thumb.literal_address(address, decoded)
                elif state == "arm" and decoded[0] == "ldr_literal":
                    literal = address + 8 + int(decoded[2])
                    if not 0 <= literal < (1 << 32):
                        raise TargetRangeError(
                            f"A32 literal address from 0x{address:08X} lies outside the 32-bit address space"
                        )
            except (arm.UnsupportedInstruction, thumb.UnsupportedThumbInstruction, TargetRangeError) as exc:
                unknown_reason = str(exc)
            else:
                item = {
                    "index": index,
                    "virtual_address": f"0x{address:08X}",
                    "decompressed_code_file_offset": absolute_offset,
                    "instruction_size_bytes": instruction_size,
                    "encoding": f"0x{word:0{unit * 2}X}",
                    "decode_status": "decoded",
                    "mnemonic": mnemonic,
                    "decoded_ir": decoded,
                }
                if literal is not None:
                    item["literal_pool_virtual_address"] = f"0x{literal:08X}"
                    item["literal_within_declared_text"] = (
                        text_start <= literal and literal + 4 <= text_start + text_size
                    )
                    item["literal_width_bytes"] = 4
                    item["literal_value_read"] = False
                if decoded[0] in ("push", "pop", "pop_pc"):
                    count = bin(int(decoded[1])).count("1") + (
                        1 if decoded[0] == "pop_pc" or (decoded[0] == "push" and decoded[2]) else 0
                    )
                    item["stack_delta_bytes"] = -4 * count if decoded[0] == "push" else 4 * count
                if state == "arm" and decoded[0] in ("arm_push", "arm_pop"):
                    count = int(decoded[1]).bit_count()
                    item["stack_delta_bytes"] = -4 * count if decoded[0] == "arm_push" else 4 * count
                    if decoded[0] == "arm_pop" and (int(decoded[1]) & (1 << 15)):
                        item["indirect_branch"] = True
                        item["branch_target_virtual_address"] = None
                        item["branch_target_note"] = (
                            "PC is loaded from the stack at run time; target is not resolved"
                        )
                if state == "thumb" and decoded[0] in thumb.MEMORY_OPS:
                    item["memory_access"] = memory_access_metadata(decoded)
                if state == "thumb" and decoded[0] == "adr":
                    pc_base = (address + 4) & ~3
                    item["pc_relative_address"] = {
                        "aligned_pc_base": f"0x{pc_base:08X}",
                        "offset_bytes": int(decoded[2]),
                        "target_virtual_address": f"0x{pc_base + int(decoded[2]):08X}",
                    }
                if state == "thumb" and decoded[0] == "add_sp_imm":
                    item["address_calculation"] = {
                        "base_register": "sp",
                        "offset_bytes": int(decoded[2]),
                        "result_value_resolved": False,
                    }
                if state == "thumb" and decoded[0] in ("add_sp", "sub_sp"):
                    item["stack_pointer_delta_bytes"] = int(decoded[1]) * (1 if decoded[0] == "add_sp" else -1)
                if decoded[0] in thumb.INDIRECT_FLOW_OPS:
                    item["indirect_branch"] = True
                    item["branch_links"] = decoded[0] == "blx_reg"
                    if decoded[0] == "blx_reg":
                        link_address = address + instruction_size
                        if state == "thumb":
                            link_address |= 1
                        item["link_register_value"] = f"0x{link_address:08X}"
                    item["branch_target_virtual_address"] = None
                    item["branch_target_note"] = (
                        "target comes from a register or the stack at run time; not resolved"
                    )
                if decoded[0] == "branch":
                    target_address = address + (2 + int(decoded[2])) * unit
                    item["branch_target_virtual_address"] = f"0x{target_address:08X}"
                    item["branch_target_within_declared_text"] = text_start <= target_address < text_start + text_size
                if state == "arm" and decoded[0] == "call":
                    item["branch_links"] = True
                    item["link_register_value"] = f"0x{address + 4:08X}"
                    item["branch_target_virtual_address"] = f"0x{call_target:08X}"
                    item["branch_target_state"] = call_target_state
                    item["branch_target_within_declared_text"] = (
                        text_start <= int(call_target) < text_start + text_size
                    )
                instructions.append(item)
                cursor += instruction_size
                index += 1
                continue

        if not include_unsupported:
            if is_thumb32:
                message = (
                    f"unsupported 32-bit Thumb instruction at 0x{address:08X} "
                    f"(halfwords 0x{word:04X} 0x{thumb32_second:04X}): {unknown_reason}; "
                    "use --include-unsupported to record raw encodings without decoding them"
                )
            else:
                digits = unit * 2
                message = (
                    f"unsupported instruction at 0x{address:08X} (0x{word:0{digits}X}): "
                    f"{unknown_reason}; use --include-unsupported to continue with raw encodings"
                )
            raise TargetRangeError(message)

        item = {
            "index": index,
            "virtual_address": f"0x{address:08X}",
            "decompressed_code_file_offset": absolute_offset,
            "instruction_size_bytes": instruction_size,
            "encoding": (
                f"0x{word:04X} 0x{thumb32_second:04X}" if is_thumb32
                else f"0x{word:0{unit * 2}X}"
            ),
            "decode_status": "unsupported-thumb32" if is_thumb32 else "unsupported",
            "mnemonic": None,
            "decoded_ir": None,
            "reason": unknown_reason,
        }
        if is_thumb32:
            item["halfwords"] = [f"0x{word:04X}", f"0x{thumb32_second:04X}"]
        instructions.append(item)
        cursor += instruction_size
        index += 1

    selected_end = start_address + cursor
    scanned_starts = {int(item["virtual_address"], 16) for item in instructions}
    for item in instructions:
        target_text = item.get("branch_target_virtual_address")
        if target_text is not None:
            branch_address = int(target_text, 16)
            item["branch_target_within_selected_range"] = start_address <= branch_address < selected_end
            item["branch_target_is_scanned_instruction_start"] = (
                item.get("branch_target_state", state) == state and branch_address in scanned_starts
            )

    for item in instructions:
        literal_text = item.get("literal_pool_virtual_address")
        if literal_text is not None:
            literal_address = int(literal_text, 16)
            item["literal_overlaps_selected_range"] = start_address <= literal_address < selected_end
            item["literal_is_scanned_instruction_start"] = literal_address in scanned_starts

    has_unknown = any(item["decode_status"] != "decoded" for item in instructions)
    return {
        "schema_version": 1,
        "status": "partially-decoded-explicit-range" if has_unknown else "decoded-explicit-range",
        "target": {
            "target_id": checked["target"]["target_id"],
            "display_name": checked["target"]["display_name"],
            "program_id": checked["identity"]["program_id"],
            "program_id_match": program_match,
            "revision_hint": checked["revision_hint"],
        },
        "range": {
            "state": state,
            "start_address": f"0x{start_address:08X}",
            "instruction_count": instruction_count,
            "unit_bytes": unit,
            "byte_count": cursor,
            "decompressed_code_file_offset": file_offset,
            "text_virtual_start": f"0x{text_start:08X}",
            "text_declared_size_bytes": text_size,
            "selected_range_end": f"0x{selected_end:08X}",
            "includes_unsupported_raw_encodings": include_unsupported and has_unknown,
            "semantic_warning": "This is syntax-only; register, flag, control-flow and ABI assumptions are not proven to match the game.",
        },
        "input": {
            "exheader_filename": exheader_path.name,
            "exheader_sha256": checked["inputs"]["exheader"]["sha256"],
            "code_filename": code_path.name,
            "code_sha256": checked["inputs"]["decompressed_code"]["sha256"],
        },
        "instructions": instructions,
        "control_flow": cfg.analyze_control_flow(instructions, state, start_address, selected_end),
        "dataflow": effects.summarize_range(instructions, state),
        "limitations": [
            "Only the explicit fixed-width range is decoded; no function discovery or automatic ARM/Thumb state detection.",
            "Only the current narrow ARM A32 and Thumb-16 subsets are decoded.",
            "With --include-unsupported, unknown encodings are recorded as raw bytes; they are not disassembled or semantically analyzed.",
            "Only the ARMv6K Thumb BL/BLX immediate pair is decoded among 32-bit Thumb forms; every other 32-bit Thumb pair is kept together as two raw halfwords.",
            "BX Rm, BLX Rm and POP {..., PC} are decoded syntactically (Rm != PC); their run-time targets, ARM/Thumb state switches and stack contents are not resolved, and a decoded BX/POP does not prove a function ends there.",
            "LDR Rd, [PC, #imm] reports only the computed literal address; the literal value is never read, and a literal overlapping the scanned range means data may be decoded as code. Pool extents, shared literals and what the value means are not resolved.",
            "PUSH/POP are decoded syntactically with their stack-pointer delta only; stack contents, alignment, frame layout and calling convention are not modeled, and a PUSH/POP pair does not prove a function boundary.",
            "BL/BLX decoding computes the call target only; callee identity, return address use, argument registers and ABI are not resolved, and BLX targets are ARM state, not scanned in the Thumb range.",
            "Literal pools, embedded data, relocations, calls, memory effects, ABI and control-flow context are not resolved.",
            "Reports contain instruction encodings derived from local game code; keep them local unless reviewed and redacted.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    profiles = intake.load_profiles()
    parser = argparse.ArgumentParser(
        description="Decode an explicitly selected range in a local decompressed 3DS .code file."
    )
    parser.add_argument("--target", required=True, choices=sorted(profiles))
    parser.add_argument("--exheader", required=True, type=Path)
    parser.add_argument("--code", required=True, type=Path)
    parser.add_argument("--state", required=True, choices=("arm", "thumb"))
    parser.add_argument("--start-address", required=True, type=parse_address)
    parser.add_argument("--instruction-count", required=True, type=int)
    parser.add_argument("--title-id", help="optional NCCH/container ID, separate from the ExHeader Program ID")
    parser.add_argument("--allow-unverified-target", action="store_true")
    parser.add_argument(
        "--include-unsupported", action="store_true",
        help="record unknown encodings as raw data and continue; 32-bit Thumb instructions stay grouped",
    )
    parser.add_argument("--report", type=Path, help="write a local JSON report outside the repository")
    args = parser.parse_args(argv)
    try:
        report = inspect_code_range(
            args.target, args.exheader, args.code, args.state,
            args.start_address, args.instruction_count, title_id=args.title_id,
            allow_unverified_target=args.allow_unverified_target,
            include_unsupported=args.include_unsupported,
        )
        rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        if args.report:
            target_path = args.report.resolve()
            if target_path == ROOT or ROOT in target_path.parents:
                raise TargetRangeError("report output must be outside the repository")
            args.report.write_text(rendered, encoding="utf-8", newline="\n")
        else:
            sys.stdout.write(rendered)
        return 0
    except (TargetRangeError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
