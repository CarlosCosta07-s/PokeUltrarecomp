"""Native differential checks between generated synthetic C and the NZCV model."""
import unittest

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import arm_differential_poc as differential  # noqa: E402


class DifferentialFixtureTests(unittest.TestCase):
    def test_matrix_covers_all_operations_and_boundary_values(self):
        cases = differential.build_cases()
        self.assertEqual(72, len(cases))
        self.assertEqual(72, len({case.name for case in cases}))
        for operation in ("adds", "subs", "cmn"):
            self.assertEqual(24, sum(case.name.startswith(operation + "-") for case in cases))

    def test_cmn_fixtures_keep_r0_as_result_and_still_check_flags(self):
        cases = differential.build_cases()
        cmn_cases = [case for case in cases if case.name.startswith("cmn-")]
        self.assertEqual(24, len(cmn_cases))
        for case in cmn_cases:
            self.assertEqual(case.initial_value, case.expected_result, case.name)

    def test_native_differential_when_compiler_exists(self):
        compiler = differential._find_compiler()
        if not compiler:
            self.skipTest("no C compiler found; native differential proof requires cc, gcc, or clang")
        selected, count = differential.run_differential(compiler)
        self.assertEqual(compiler, selected)
        self.assertEqual(72, count)


if __name__ == "__main__":
    unittest.main()
