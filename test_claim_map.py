"""Tests for the claim map and the README — the judges' map of the build.

    python3 -m unittest test_claim_map -v

Offline: no lane call, no model, no network. The card's three gates are the
three test methods named `test_the_...`:

  1. every path the table names resolves in the repo;
  2. every number the README quotes appears in a committed output file or in
     the output of the cited command;
  3. a reader can run one cited receipt command and see the cited output.

Gate 2 reads "output file" generously ON PURPOSE: the README quotes 9/14 and
6/14, which are the lane scores against the PLANTED TRUTH (14 items) and are
printed by the scorer, while the committed eval file records the same lanes
against the deterministic gate over the 13 lane-runnable items (9/13, 6/13).
Both numbers are real and both are in the repo; requiring only the raw file
would reject the README's own cited command.
"""
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLAIM_MAP = HERE / "docs" / "CLAIM_MAP.md"
README = HERE / "README.md"
SIGNIFICANT_UPDATE = HERE / "docs" / "SIGNIFICANT_UPDATE.md"

OUTPUT_FILES = [HERE / "eval-results-2026-10-28.json",
                HERE / "benchmark" / "eval-benchmark-2026-10-28.json"]

# A backticked token that names a file or a directory in THIS repo. The
# top-level names are a FIXED list, not a lookup, so the test cannot be
# satisfied by a path that happens to exist.
TOP_LEVEL = ("docs", "benchmark", "evidence", ".github")
PATH_RE = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$")
FILE_RE = re.compile(r"^[A-Za-z0-9_.-]+\.(py|md|json|jsonl|html|txt|yml|yaml)$")


def cited_paths(text: str) -> list[str]:
    """The repo paths a document names, in backticks.

    A model id (`nvidia/Nemotron-3.5-Super-VL`) is not a path: its first
    segment is not one of the repo's top-level names.
    """
    out = []
    for token in re.findall(r"`([^`\n]+)`", text):
        if " " in token or "://" in token:
            continue
        if "/" in token and PATH_RE.match(token) and token.split("/")[0] in TOP_LEVEL:
            out.append(token)
        elif FILE_RE.match(token):
            out.append(token)
    return sorted(set(out))


def prose_numbers(text: str) -> list[str]:
    """The figures a document quotes.

    A figure is a measurement. So the things that are NOT measurements go
    first: fenced code blocks (command arguments), code spans (model ids and
    paths), dates, and version or licence numbers (`Apache-2.0`, `Python
    3.10+`) — a reader is not being shown a claim by the version of a
    dependency.
    """
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`[^`\n]+`", " ", text)
    text = re.sub(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)", " ", text)
    text = re.sub(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}\b",
                  " ", text)
    # "Python 3.10+" is a minimum version, not a measurement.
    text = re.sub(r"\d+(?:\.\d+)?\+", " ", text)
    text = re.sub(r"(?<=[A-Za-z-])\d+(?:\.\d+)?", " ", text)
    return sorted(set(re.findall(r"\d+(?:\.\d+)?(?:/\d+)*", text)))


class ClaimMapTests(unittest.TestCase):
    """The map a judge reads."""

    def test_the_map_has_a_row_for_each_new_lane(self):
        text = CLAIM_MAP.read_text(encoding="utf-8")
        for lane in ("nemotron", "Tavily", "VL", "MCP"):
            self.assertIn(lane, text, f"the map has no row for {lane}")

    def test_the_significant_update_document_exists(self):
        self.assertTrue(SIGNIFICANT_UPDATE.is_file(),
                        "the card asks for docs/SIGNIFICANT_UPDATE.md")
        text = SIGNIFICANT_UPDATE.read_text(encoding="utf-8")
        for section in ("What pre-existed", "What was added", "honest limits"):
            self.assertIn(section, text)

    def test_the_significant_update_document_says_there_are_no_users_or_revenue(self):
        # The card's out-of-scope line: marketing claims about users, revenue or
        # adoption (none exist; say none).
        text = SIGNIFICANT_UPDATE.read_text(encoding="utf-8").lower()
        self.assertIn("no users", text)
        self.assertIn("revenue", text)
        self.assertIn("adoption", text)


class Gate1PathsTests(unittest.TestCase):
    """Every path the documents name resolves in the repo."""

    def test_every_path_the_claim_map_names_resolves(self):
        for path in cited_paths(CLAIM_MAP.read_text(encoding="utf-8")):
            self.assertTrue((HERE / path).exists(),
                            f"the claim map names {path}, which is not in the repo")

    def test_every_path_the_readme_names_resolves(self):
        for path in cited_paths(README.read_text(encoding="utf-8")):
            self.assertTrue((HERE / path).exists(),
                            f"the README names {path}, which is not in the repo")

    def test_every_path_the_significant_update_names_resolves(self):
        for path in cited_paths(SIGNIFICANT_UPDATE.read_text(encoding="utf-8")):
            self.assertTrue((HERE / path).exists(),
                            f"SIGNIFICANT_UPDATE.md names {path}, which is not in the repo")


class Gate2NumbersTests(unittest.TestCase):
    """Every number the README quotes is a number the repo actually produced."""

    def _recorded_output(self) -> str:
        """Everything the repo recorded: the output files and the tools' output."""
        blob = []
        for path in OUTPUT_FILES:
            blob.append(path.read_text(encoding="utf-8"))
        scorer = subprocess.run(
            [sys.executable, str(HERE / "benchmark" / "score.py"),
             "--cases", str(HERE / "benchmark" / "cases.jsonl"),
             "--truth", str(HERE / "benchmark" / "truth.json"),
             "--eval-results", str(HERE / "benchmark" / "eval-benchmark-2026-10-28.json")],
            capture_output=True, text=True, cwd=str(HERE))
        blob.append(scorer.stdout)
        ledger = subprocess.run(
            [sys.executable, str(HERE / "tier_ledger.py"), "--check"],
            capture_output=True, text=True, cwd=str(HERE))
        blob.append(ledger.stdout)
        blob.append(ledger.stderr)
        # The ledger's own rendered output is where the per-tier costs live.
        sys.path.insert(0, str(HERE))
        import tier_ledger as ledger_module
        blob.append(ledger_module.render())
        return "\n".join(blob)

    def test_every_number_the_readme_quotes_is_one_the_repo_produced(self):
        recorded = self._recorded_output()
        missing = [n for n in prose_numbers(README.read_text(encoding="utf-8"))
                   if n not in recorded]
        self.assertEqual(missing, [],
                         f"the README quotes figures the repo never recorded: {missing}")

    def test_every_number_the_significant_update_quotes_is_one_the_repo_produced(self):
        recorded = self._recorded_output()
        missing = [n for n in prose_numbers(SIGNIFICANT_UPDATE.read_text(encoding="utf-8"))
                   if n not in recorded]
        self.assertEqual(missing, [],
                         f"SIGNIFICANT_UPDATE.md quotes figures the repo never recorded: {missing}")


class Gate3CommandTests(unittest.TestCase):
    """A reader can run one cited command and see the cited output."""

    def test_the_cited_receipt_command_prints_the_cited_output(self):
        # The README cites this command; a reader runs it and must see the
        # numbers the README quotes.
        proc = subprocess.run(
            [sys.executable, "benchmark/score.py",
             "--eval-results", "benchmark/eval-benchmark-2026-10-28.json"],
            capture_output=True, text=True, cwd=str(HERE))
        self.assertIn("[deterministic] 14/14 correct", proc.stdout)
        self.assertIn("[lane:deep] 9/14 correct", proc.stdout)
        self.assertIn("[lane:fast] 6/14 correct", proc.stdout)

    def test_the_cited_ledger_command_matches_the_committed_doc(self):
        proc = subprocess.run([sys.executable, "tier_ledger.py", "--check"],
                              capture_output=True, text=True, cwd=str(HERE))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_the_claim_map_cites_a_runnable_command_for_its_mcp_row(self):
        text = CLAIM_MAP.read_text(encoding="utf-8")
        self.assertIn("pytest -q test_mcp_server.py", text,
                      "the MCP row must cite the test run that proves it")
        proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "test_mcp_server.py"],
                              capture_output=True, text=True, cwd=str(HERE))
        self.assertEqual(proc.returncode, 0, proc.stdout[-400:])


if __name__ == "__main__":
    unittest.main()
