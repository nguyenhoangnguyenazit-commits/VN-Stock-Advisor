#!/usr/bin/env python3
"""Master CLI Test Runner for Vietnamese Stock Market Advisor (VN-Advisor).

Executes the 4-Tier Opaque-Box E2E Testing Suite:
- Tier 1: Core Feature Coverage (test_tier1_features.py)
- Tier 2: Boundary & Corner Cases (test_tier2_boundaries.py)
- Tier 3: Cross-Feature Interactions (test_tier3_cross_feature.py)
- Tier 4: Real-World Persona Scenarios (test_tier4_scenarios.py)

Usage:
    python tests/run_tests.py                   # Run all 4 tiers
    python tests/run_tests.py --tier 1          # Run Tier 1 only
    python tests/run_tests.py --tier 2          # Run Tier 2 only
    python tests/run_tests.py --tier 3          # Run Tier 3 only
    python tests/run_tests.py --tier 4          # Run Tier 4 only
    python tests/run_tests.py --tier all        # Explicit all tiers
    python tests/run_tests.py --verbose         # Detailed pytest logs
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

import pytest

# Tier mapping definitions
TIER_SPECS = {
    "1": {
        "name": "Tier 1",
        "description": "Core Feature Coverage (R1-R5)",
        "file": str(PROJECT_ROOT / "tests" / "e2e" / "test_tier1_features.py"),
        "min_tests": 25,
    },
    "2": {
        "name": "Tier 2",
        "description": "Boundary & Corner Cases (R1-R5)",
        "file": str(PROJECT_ROOT / "tests" / "e2e" / "test_tier2_boundaries.py"),
        "min_tests": 25,
    },
    "3": {
        "name": "Tier 3",
        "description": "Cross-Feature Interactions",
        "file": str(PROJECT_ROOT / "tests" / "e2e" / "test_tier3_cross_feature.py"),
        "min_tests": 10,
    },
    "4": {
        "name": "Tier 4",
        "description": "Real-World Persona Scenarios",
        "file": str(PROJECT_ROOT / "tests" / "e2e" / "test_tier4_scenarios.py"),
        "min_tests": 5,
    },
}


class TierResultCollector:
    """Pytest plugin to collect test execution telemetry categorized by tier."""

    def __init__(self):
        self.results: Dict[str, List[Dict[str, any]]] = {
            "1": [],
            "2": [],
            "3": [],
            "4": [],
        }
        self.failures: List[any] = []

    def pytest_runtest_logreport(self, report):
        if report.when == "call" or (report.failed and report.when in ["setup", "call"]):
            fspath = str(report.fspath)
            tier_key = None
            if "test_tier1_features" in fspath:
                tier_key = "1"
            elif "test_tier2_boundaries" in fspath:
                tier_key = "2"
            elif "test_tier3_cross_feature" in fspath:
                tier_key = "3"
            elif "test_tier4_scenarios" in fspath:
                tier_key = "4"

            if tier_key:
                self.results[tier_key].append({
                    "nodeid": report.nodeid,
                    "passed": report.passed,
                    "failed": report.failed,
                    "skipped": report.skipped,
                    "duration": getattr(report, "duration", 0.0),
                })

            if report.failed:
                self.failures.append(report)


def print_summary_table(collector: TierResultCollector, selected_tiers: List[str], total_elapsed: float):
    """Render a clean, institutional ASCII summary table."""
    border = "+--------+------------------------------------+-------+--------+--------+----------+--------------+"
    header = "| Tier   | Description                        | Total | Passed | Failed | Duration | Pass Rate    |"

    print("\n" + border)
    print("|                               VN-ADVISOR E2E TEST EXECUTION SUMMARY                             |")
    print(border)
    print(header)
    print(border)

    grand_total = 0
    grand_passed = 0
    grand_failed = 0
    grand_duration = 0.0

    for tier_id in selected_tiers:
        spec = TIER_SPECS[tier_id]
        records = collector.results[tier_id]
        total = len(records)
        passed = sum(1 for r in records if r["passed"])
        failed = sum(1 for r in records if r["failed"])
        duration = sum(r["duration"] for r in records)
        pass_rate = (passed / total * 100.0) if total > 0 else 0.0

        grand_total += total
        grand_passed += passed
        grand_failed += failed
        grand_duration += duration

        print(
            f"| {spec['name']:<6} | {spec['description']:<34} | {total:>5} | {passed:>6} | {failed:>6} | {duration:>7.2f}s | {pass_rate:>10.1f}% |"
        )

    print(border)
    grand_rate = (grand_passed / grand_total * 100.0) if grand_total > 0 else 0.0
    print(
        f"| {'TOTAL':<6} | {'All Targeted Verification Tiers':<34} | {grand_total:>5} | {grand_passed:>6} | {grand_failed:>6} | {grand_duration:>7.2f}s | {grand_rate:>10.1f}% |"
    )
    print(border)
    print(f"Total Wall Time: {total_elapsed:.2f} seconds\n")


def run(tiers: Optional[List[str]] = None, verbose: bool = False) -> int:
    """Run specified test tiers and return exit code."""
    if not tiers or "all" in tiers:
        selected_tiers = ["1", "2", "3", "4"]
    else:
        selected_tiers = [t for t in ["1", "2", "3", "4"] if t in tiers]

    target_files = [TIER_SPECS[t]["file"] for t in selected_tiers]

    collector = TierResultCollector()
    pytest_args = ["-q"]
    if verbose:
        pytest_args.append("-v")
    else:
        pytest_args.append("--tb=short")

    pytest_args.extend(target_files)

    start_time = time.time()
    exit_code = pytest.main(pytest_args, plugins=[collector])
    elapsed = time.time() - start_time

    print_summary_table(collector, selected_tiers, elapsed)

    if collector.failures:
        print("FAILURES DETECTED:")
        for fail in collector.failures:
            print(f"  FAILED: {fail.nodeid}")
            if hasattr(fail, "longreprtext"):
                print(fail.longreprtext)
        return 1

    # Verify minimum test thresholds
    for t in selected_tiers:
        count = len(collector.results[t])
        min_req = TIER_SPECS[t]["min_tests"]
        if count < min_req:
            print(f"ERROR: {TIER_SPECS[t]['name']} produced {count} tests, minimum required is {min_req}!")
            return 1

    print("ALL TESTS PASSED! Strict Vietnamese Regulatory & System Invariants Verified.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="VN-Advisor Master E2E Test Runner")
    parser.add_argument(
        "--tier",
        type=str,
        default="all",
        choices=["1", "2", "3", "4", "all"],
        help="Select specific test tier to execute (1, 2, 3, 4, or all)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output from pytest",
    )
    args = parser.parse_args()

    tier_selection = ["all"] if args.tier == "all" else [args.tier]
    code = run(tiers=tier_selection, verbose=args.verbose)
    sys.exit(code)


if __name__ == "__main__":
    main()
