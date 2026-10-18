"""Wires the patent claim-support dossier generator (roadmap P5-08) into
the normal test suite: a broken code citation in docs/claims/claim_map.yaml
(a renamed/removed symbol) or a cited test that no longer passes must fail
`pytest tests/`, not only a separately-run script nobody remembers to run
before a submission. build_dossier.py already does the real verification
work (importing + inspecting every cited Python symbol, actually running
every cited test as its own pytest subprocess) — this test just asserts
its own exit status, which is the one thing a human skimming green CI
output would otherwise never notice is broken.

Slow by design (it is itself ~18 pytest subprocess invocations, one per
claim element) — this is the cost of the citations being enforced rather
than merely written down, not a test to make fast.
"""

import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def test_dossier_build_resolves_every_citation():
    proc = subprocess.run(
        [sys.executable, "scripts/build_dossier.py"],
        cwd=str(BACKEND_ROOT), capture_output=True, text=True, timeout=600,
    )
    assert proc.returncode == 0, (
        "The patent claim-support dossier (docs/claims/claim_map.yaml) has an "
        "unresolved code or test citation — see docs/claims/patent_dossier.md "
        "'NOT YET REDUCED TO PRACTICE' for which element and why.\n\n"
        f"stdout:\n{proc.stdout}\n\nstderr:\n{proc.stderr}"
    )
