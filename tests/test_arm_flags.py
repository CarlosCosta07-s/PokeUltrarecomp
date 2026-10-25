"""Synthetic unit tests for the isolated ARM A32 NZCV flag model."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from arm_flags import NZCV, add_with_flags, logical_flags, sub_with_flags  # noqa: E402


class FlagStructureTests(unittest.TestCase):
    def test_default_flags_are_clear(self):
        self.assertEqual(NZCV(False, False, False, False), NZCV())
        self.assertEqual(0, NZCV().nibble)

    def test_nibble_encodes_nzcv_order(self):
        self.assertEqual(0b1011, NZCV(True, False, True, True).nibble)
        self.assertEqual(0b0100, NZCV(False, True, False, False).nibble)

    def test_flag_fields_must_be_booleans(self):
        with self.assertRaisesRegex(ValueError, "N flag must be bool"):
            NZCV(1, False, False, False)


class AdditionFlagTests(unittest.TestCase):
    def test_unsigned_carry_sets_c_and_zero(self):
        result, flags = add_with_flags(0xFFFFFFFF, 1)
        self.assertEqual(0, result)
        self.assertEqual(NZCV(False, True, True, False), flags)

    def test_signed_positive_overflow_sets_v(self):
        result, flags = add_with_flags(0x7FFFFFFF, 1)
        self.assertEqual(0x80000000, result)
        self.assertEqual(NZCV(True, False, False, True), flags)

    def test_signed_negative_overflow_can_coexist_with_unsigned_carry(self):
        result, flags = add_with_flags(0x80000000, 0x80000000)
        self.assertEqual(0, result)
        self.assertEqual(NZCV(False, True, True, True), flags)

    def test_carry_in_is_included(self):
        result, flags = add_with_flags(0xFFFFFFFF, 0, carry_in=1)
        self.assertEqual(0, result)
        self.assertEqual(NZCV(False, True, True, False), flags)

    def test_non_overflowing_addition_leaves_c_and_v_clear(self):
        result, flags = add_with_flags(12, 3)
        self.assertEqual(15, result)
        self.assertEqual(NZCV(False, False, False, False), flags)


class SubtractionFlagTests(unittest.TestCase):
    def test_unsigned_borrow_clears_c(self):
        result, flags = sub_with_flags(0, 1)
        self.assertEqual(0xFFFFFFFF, result)
        self.assertEqual(NZCV(True, False, False, False), flags)

    def test_exact_subtraction_sets_z_and_no_borrow(self):
        result, flags = sub_with_flags(7, 7)
        self.assertEqual(0, result)
        self.assertEqual(NZCV(False, True, True, False), flags)

    def test_signed_overflow_on_subtraction(self):
        result, flags = sub_with_flags(0x80000000, 1)
        self.assertEqual(0x7FFFFFFF, result)
        self.assertEqual(NZCV(False, False, True, True), flags)

    def test_borrow_in_is_included(self):
        result, flags = sub_with_flags(0, 0, borrow_in=1)
        self.assertEqual(0xFFFFFFFF, result)
        self.assertEqual(NZCV(True, False, False, False), flags)

    def test_unsigned_borrow_can_coexist_with_signed_overflow(self):
        _, flags = sub_with_flags(0x7FFFFFFF, 0xFFFFFFFF)
        self.assertFalse(flags.c)
        self.assertTrue(flags.v)


class LogicalFlagTests(unittest.TestCase):
    def test_zero_result_updates_nz_and_preserves_cv(self):
        previous = NZCV(False, False, True, True)
        flags = logical_flags(0, previous)
        self.assertEqual(NZCV(False, True, True, True), flags)

    def test_negative_result_sets_n(self):
        previous = NZCV(False, False, False, True)
        flags = logical_flags(0x80000000, previous)
        self.assertEqual(NZCV(True, False, False, True), flags)

    def test_explicit_shifter_carry_replaces_c_only(self):
        previous = NZCV(False, True, False, True)
        flags = logical_flags(1, previous, shifter_carry=True)
        self.assertEqual(NZCV(False, False, True, True), flags)

    def test_invalid_input_ranges_are_rejected(self):
        with self.assertRaises(ValueError):
            add_with_flags(-1, 0)
        with self.assertRaises(ValueError):
            add_with_flags(0, 0, carry_in=2)
        with self.assertRaises(ValueError):
            sub_with_flags(0, 0, borrow_in=-1)
        with self.assertRaises(ValueError):
            logical_flags(0x1_0000_0000, NZCV())

    def test_invalid_prior_flags_and_shifter_carry_are_rejected(self):
        with self.assertRaises(ValueError):
            logical_flags(0, None)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            logical_flags(0, NZCV(), shifter_carry=1)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
