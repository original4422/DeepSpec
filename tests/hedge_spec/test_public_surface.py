"""Scope guard for the pure-core module interface."""

from __future__ import annotations

import unittest

import deepspec.hedge_spec as hedge_spec


class PublicSurfaceTests(unittest.TestCase):
    def test_legacy_success_and_project_orchestration_are_not_exported(self) -> None:
        for excluded in (
            "SuccessCriteria",
            "metrics",
            "run_artifacts",
            "runner",
            "adapters",
        ):
            with self.subTest(excluded=excluded):
                self.assertFalse(hasattr(hedge_spec, excluded))


if __name__ == "__main__":
    unittest.main()
