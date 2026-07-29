from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CAPTURE = REPO_ROOT / "scripts" / "dflash_d4_capture_source.py"
FINAL_SOURCE_COMMIT = "9a01e2df71d6de085b0b2d50ccd687ec5abc7ff1"
FINAL_SOURCE_TREE = "53fc45b1b04963736254dc7ed582047313b8075a"


class D4SourceCaptureContractTests(unittest.TestCase):
    def test_capture_cli_emits_whitespace_clean_zero_context_patch(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix=".dflash-d4-capture-test-",
            dir=REPO_ROOT,
        ) as temp:
            root = Path(temp)
            patch = root / "integration.patch"
            manifest = root / "manifest.json"
            subprocess.run(
                [
                    sys.executable,
                    str(CAPTURE),
                    "--patch-out",
                    str(patch),
                    "--manifest-out",
                    str(manifest),
                ],
                cwd=REPO_ROOT,
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            )

            payload = patch.read_bytes()
            self.assertFalse(
                any(line.startswith(b" ") for line in payload.splitlines())
            )

            git_repo = root / "artifact-repo"
            git_repo.mkdir()
            subprocess.run(
                ["git", "init", "--quiet"],
                cwd=git_repo,
                check=True,
            )
            stored_patch = git_repo / "integration.patch"
            stored_patch.write_bytes(payload)
            subprocess.run(
                ["git", "add", "integration.patch"],
                cwd=git_repo,
                check=True,
            )
            subprocess.run(
                ["git", "diff", "--cached", "--check"],
                cwd=git_repo,
                check=True,
            )

            document = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(
                document["integration_patch"]["format"],
                "unified-zero",
            )
            self.assertEqual(
                document["integration_patch"]["apply_args"],
                ["--unidiff-zero"],
            )
            self.assertEqual(
                document["final_source_commit"],
                FINAL_SOURCE_COMMIT,
            )
            self.assertEqual(document["final_source_tree"], FINAL_SOURCE_TREE)


if __name__ == "__main__":
    unittest.main()
