#!/usr/bin/env python3
"""Encode stdin as one JSON string for the Phase 01A shell watchdog."""

from __future__ import annotations

import json
import sys


def main() -> None:
    json.dump(sys.stdin.read(), sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
