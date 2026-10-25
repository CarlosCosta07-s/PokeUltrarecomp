"""Conservative candidate basic-block analysis for explicitly decoded ARM/Thumb ranges.

This module does not discover functions or prove runtime reachability. It consumes
an explicitly selected instruction list and reports only structurally justified
edges. Unknown encodings, indirect control flow, calls and literal-pool overlaps
remain explicit uncertainty.
"""
from __future__ import annotations

from typing import Any


def _address(value: object, field: str) -> int:
    if not isinstance(value, str) or not value.startswith("0x"):
        raise ValueError(f"{field} must be a hexadecimal address string")
    try:
        parsed = int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{field} is not a valid hexadecimal address: {value!r}") from exc
    if not 0 <= parsed < (1 << 32):
        raise ValueError(f"{field} lies outside uint32")
    return parsed


def analyze_control_flow(
    instructions: list[dict[str, Any]],
    state: str,
    selected_start: int,
    selected_end: int,
) -> dict[str, Any]:
    """Build candidate basic blocks and bounded edges for one explicit range."""
    if state not in ("arm", "thumb"):
        raise ValueError("state must be 'arm' or 'thumb'")
    if not 0 <= selected_start < selected_end <= (1 << 32):
        raise ValueError("selected range must be a non-empty uint32 interval")
    if not instructions:
        raise ValueError("control-flow analysis needs at least one instruction")

    ordered = sorted(instructions, key=lambda item: _address(item.get("virtual_address"), "virtual_address"))
    by_address: dict[int, dict[str, Any]] = {}
    addresses: list[int] = []
    for item in ordered:
        address = _address(item.get("virtual_address"), "virtual_address")
        size = item.get("instruction_size_bytes")
        if isinstance(size, bool) or not isinstance(size, int) or size not in (2, 4):
            raise ValueError(f"instruction at 0x{address:08X} has invalid size")
        if address < selected_start or address + size > selected_end:
            raise ValueError(f"instruction at 0x{address:08X} lies outside the selected range")
        if address in by_address:
            raise ValueError(f"duplicate instruction address 0x{address:08X}")
        by_address[address] = item
        addresses.append(address)

    def ir(item: dict[str, Any]) -> list[Any] | tuple[Any, ...] | None:
        candidate = item.get("decoded_ir")
        return candidate if isinstance(candidate, (list, tuple)) and candidate else None

    def opcode(item: dict[str, Any]) -> object | None:
        decoded = ir(item)
        return decoded[0] if decoded else None

    def is_unknown(item: dict[str, Any]) -> bool:
        return item.get("decode_status", "decoded") != "decoded"

    def ends_block(item: dict[str, Any]) -> bool:
        op = opcode(item)
        return (
            is_unknown(item)
            or op in ("branch", "call", "return", "bx", "blx_reg", "pop_pc")
            or bool(item.get("indirect_branch"))
        )

    leaders: set[int] = {addresses[0]}
    warnings: list[str] = []
    potential_data: list[dict[str, Any]] = []

    for position, item in enumerate(ordered):
        address = addresses[position]
        decoded = ir(item)
        op = decoded[0] if decoded else None

        if op == "branch":
            target_text = item.get("branch_target_virtual_address")
            if isinstance(target_text, str):
                target = _address(target_text, "branch_target_virtual_address")
                target_state = item.get("branch_target_state", state)
                if target_state == state and target in by_address:
                    leaders.add(target)

        if op == "ldr_literal":
            literal_text = item.get("literal_pool_virtual_address")
            if isinstance(literal_text, str):
                literal = _address(literal_text, "literal_pool_virtual_address")
                record = {
                    "reader_instruction_address": f"0x{address:08X}",
                    "literal_address": f"0x{literal:08X}",
                    "overlaps_selected_range": bool(item.get("literal_overlaps_selected_range")),
                    "matches_scanned_instruction_start": bool(item.get("literal_is_scanned_instruction_start")),
                    "literal_value_read": False,
                }
                potential_data.append(record)
                if record["overlaps_selected_range"]:
                    warnings.append(
                        f"literal referenced at 0x{literal:08X} overlaps the selected range; instructions there may be data"
                    )

        if is_unknown(item):
            warnings.append(f"unknown instruction at 0x{address:08X} blocks known-flow analysis")
        if item.get("indirect_branch"):
            warnings.append(f"indirect control transfer at 0x{address:08X} has no statically known target")

        if ends_block(item) and position + 1 < len(ordered):
            leaders.add(addresses[position + 1])

    blocks: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []

    def finish_block() -> None:
        nonlocal current
        if not current:
            return
        block_id = f"B{len(blocks)}"
        block = {
            "block_id": block_id,
            "start_address": f"0x{addresses_of(current[0]):08X}",
            "end_address_exclusive": f"0x{addresses_of(current[-1]) + current[-1]['instruction_size_bytes']:08X}",
            "instruction_indices": [item.get("index", idx) for idx, item in enumerate(current)],
            "instruction_count": len(current),
            "first_mnemonic": current[0].get("mnemonic"),
            "last_mnemonic": current[-1].get("mnemonic"),
        }
        blocks.append(block)
        current = []

    def addresses_of(item: dict[str, Any]) -> int:
        return _address(item.get("virtual_address"), "virtual_address")

    for item in ordered:
        address = addresses_of(item)
        if current and address in leaders:
            finish_block()
        current.append(item)
        if ends_block(item):
            finish_block()
    finish_block()

    block_for_address: dict[int, str] = {}
    for block in blocks:
        block_id = block["block_id"]
        for address in block["instruction_indices"]:
            pass
        start = int(block["start_address"], 16)
        end = int(block["end_address_exclusive"], 16)
        for address in addresses:
            if start <= address < end:
                block_for_address[address] = block_id

    edges: list[dict[str, Any]] = []
    transfers: list[dict[str, Any]] = []
    position_by_address = {address: index for index, address in enumerate(addresses)}

    def add_edge(
        source_block: str,
        kind: str,
        target_address: int | None,
        target_state: str = state,
    ) -> None:
        if target_address is None:
            edges.append({
                "from_block": source_block,
                "to_block": None,
                "kind": kind,
                "target_address": None,
                "target_state": target_state,
                "resolution": "unresolved",
            })
            return
        if target_state != state:
            resolution = "state-transition-outside-this-graph"
            target_block = None
        elif not selected_start <= target_address < selected_end:
            resolution = "outside-selected-range"
            target_block = None
        elif target_address not in block_for_address:
            resolution = "not-an-instruction-start"
            target_block = None
        else:
            resolution = "resolved"
            target_block = block_for_address[target_address]
        edges.append({
            "from_block": source_block,
            "to_block": target_block,
            "kind": kind,
            "target_address": f"0x{target_address:08X}",
            "target_state": target_state,
            "resolution": resolution,
        })
        if resolution != "resolved":
            warnings.append(f"{kind} target 0x{target_address:08X} is {resolution}")

    for block in blocks:
        source_block = block["block_id"]
        end_address = int(block["end_address_exclusive"], 16)
        last_address = max(
            (address for address in addresses if block_for_address[address] == source_block),
            default=None,
        )
        if last_address is None:
            continue
        item = by_address[last_address]
        decoded = ir(item)
        op = decoded[0] if decoded else None
        next_position = position_by_address[last_address] + 1
        next_address = addresses[next_position] if next_position < len(addresses) else None

        def add_fallthrough(kind: str = "fallthrough") -> None:
            if next_address is not None:
                add_edge(source_block, kind, next_address)
            else:
                edges.append({
                    "from_block": source_block,
                    "to_block": None,
                    "kind": kind + "-outside-selected-range",
                    "target_address": f"0x{end_address:08X}",
                    "target_state": state,
                    "resolution": "outside-selected-range",
                })

        if is_unknown(item):
            transfers.append({
                "instruction_address": f"0x{last_address:08X}",
                "kind": "unknown-instruction",
                "target_address": None,
                "resolved": False,
            })
        elif op == "branch":
            target_text = item.get("branch_target_virtual_address")
            target = _address(target_text, "branch_target_virtual_address") if isinstance(target_text, str) else None
            condition = decoded[1] if decoded and len(decoded) > 1 else "?"
            kind = "conditional-taken" if condition != "al" else "unconditional-branch"
            add_edge(source_block, kind, target, item.get("branch_target_state", state))
            if condition != "al":
                add_fallthrough("conditional-not-taken")
        elif op == "return":
            pass
        elif op == "call":
            target_text = item.get("branch_target_virtual_address")
            transfers.append({
                "instruction_address": f"0x{last_address:08X}",
                "kind": str(decoded[1]).upper() if decoded and len(decoded) > 1 else "CALL",
                "target_address": target_text,
                "target_state": item.get("branch_target_state", state),
                "resolved": False,
                "note": "direct target is a call candidate, not proven callee identity",
            })
            add_fallthrough("call-return-continuation")
        elif item.get("indirect_branch") or op in ("bx", "blx_reg", "pop_pc"):
            transfers.append({
                "instruction_address": f"0x{last_address:08X}",
                "kind": str(op).upper() if op else "INDIRECT",
                "target_address": item.get("branch_target_virtual_address"),
                "resolved": False,
                "note": "runtime target/return behavior is not known from this range",
            })
            if op == "blx_reg":
                add_fallthrough("indirect-call-return-continuation")
        else:
            add_fallthrough()

    status = "candidate-cfg-with-warnings" if warnings or transfers else "candidate-cfg"
    return {
        "status": status,
        "scope": "candidate basic blocks for the user-selected range only",
        "instruction_state": state,
        "entry_address": f"0x{addresses[0]:08X}",
        "selected_range": {
            "start_address": f"0x{selected_start:08X}",
            "end_address_exclusive": f"0x{selected_end:08X}",
        },
        "basic_block_count": len(blocks),
        "edge_count": len(edges),
        "basic_blocks": blocks,
        "edges": edges,
        "unresolved_transfers": transfers,
        "potential_data_references": potential_data,
        "warnings": sorted(set(warnings)),
        "limitations": [
            "Candidate CFG only: the selected start is not proven to be a function entry.",
            "Calls, indirect branches, unknown instructions and literal-pool overlaps remain unresolved.",
            "The graph does not execute code, discover functions, model memory/register values or prove runtime reachability.",
        ],
    }
