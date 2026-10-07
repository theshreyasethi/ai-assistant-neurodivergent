"""Patent claim-support dossier generator (roadmap P5-08).

Parses docs/claims/claim_map.yaml and verifies EVERY code/test pointer
against the actual repository state — the symbol exists (imported and
inspected for Python; a textual search for TypeScript, since no TS
compiler is available to this script), and the referenced test actually
runs and passes (not merely "exists in a file"). Writes
docs/claims/patent_dossier.{md,json} and exits non-zero if anything failed
to resolve.

This is evidence tooling, not legal advice: it proves the cited code and
tests exist and pass today. It says nothing about novelty, validity, or
claim scope — those are determinations for a registered patent attorney
(see docs/PRE_FILING_CHECKLIST.md). A dossier whose own build cannot fail
is documentation, not evidence, which is the entire reason this script
resolves every citation instead of trusting claim_map.yaml to stay
accurate by hand.

Usage:
    python scripts/build_dossier.py
"""

from __future__ import annotations

import hashlib
import importlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Tuple

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent
REPO_ROOT = BACKEND_ROOT.parent
CLAIM_MAP_PATH = REPO_ROOT / "docs" / "claims" / "claim_map.yaml"
OUT_MD = REPO_ROOT / "docs" / "claims" / "patent_dossier.md"
OUT_JSON = REPO_ROOT / "docs" / "claims" / "patent_dossier.json"

sys.path.insert(0, str(BACKEND_ROOT))  # so "services.x" / "routers.x" import the same way the app does


def _resolve_python_symbol(path_sym: str) -> Tuple[bool, str]:
    """"backend/services/dase_engine.py::compute_dase" -> import
    services.dase_engine, getattr(compute_dase). Supports Class.method via
    dotted symbol segments."""
    path_str, _, symbol = path_sym.partition("::")
    file_path = REPO_ROOT / path_str
    if not file_path.exists():
        return False, f"file not found: {path_str}"
    if not path_str.startswith("backend/") or not path_str.endswith(".py"):
        return False, "not a backend .py file path"

    module_rel = path_str[len("backend/"):-len(".py")].replace("/", ".")
    try:
        module = importlib.import_module(module_rel)
    except Exception as exc:  # noqa: BLE001
        return False, f"import failed: {exc}"

    obj = module
    for part in symbol.split("."):
        if not hasattr(obj, part):
            return False, f"symbol not found: {symbol} (stopped at {part!r})"
        obj = getattr(obj, part)
    return True, "ok (imported and inspected)"


def _resolve_frontend_symbol(path_sym: str) -> Tuple[bool, str]:
    """Weaker check than the Python path: a textual search for an exported
    declaration, since this script has no TypeScript compiler available."""
    path_str, _, symbol = path_sym.partition("::")
    file_path = REPO_ROOT / path_str
    if not file_path.exists():
        return False, f"file not found: {path_str}"

    text = file_path.read_text(encoding="utf-8")
    patterns = [
        rf"\bfunction\s+{re.escape(symbol)}\b",
        rf"\bconst\s+{re.escape(symbol)}\s*[=:]",
        rf"\bclass\s+{re.escape(symbol)}\b",
    ]
    if any(re.search(p, text) for p in patterns):
        return True, "ok (textual match only — no TS compiler available to this script)"
    return False, f"symbol not found by textual search: {symbol}"


def _resolve_code(path_sym: str) -> Tuple[bool, str]:
    path_str = path_sym.split("::")[0]
    if path_str.endswith((".ts", ".tsx")):
        return _resolve_frontend_symbol(path_sym)
    return _resolve_python_symbol(path_sym)


_test_cache: Dict[str, Tuple[bool, str]] = {}


def _resolve_test(path_sym: str) -> Tuple[bool, str]:
    """Actually RUNS the referenced test (via -k name substring match, which
    also naturally covers every parametrization of a parametrized test) and
    requires it to pass — not merely that a function with this name exists
    somewhere in the file."""
    if path_sym in _test_cache:
        return _test_cache[path_sym]

    path_str, _, name = path_sym.partition("::")
    file_path = REPO_ROOT / path_str
    if not file_path.exists():
        result = (False, f"test file not found: {path_str}")
        _test_cache[path_sym] = result
        return result

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(file_path), "-k", name, "-q"],
        cwd=str(BACKEND_ROOT), capture_output=True, text=True, timeout=120,
    )
    output = proc.stdout + proc.stderr
    passed = re.search(r"(\d+) passed", output)
    failed = re.search(r"(\d+) (failed|error)", output)

    if "no tests ran" in output.lower() or not passed:
        result = (False, f"no matching test collected or ran for {name!r}")
    elif failed:
        result = (False, f"test(s) failed: ...{output.strip()[-300:]}")
    else:
        result = (True, f"{passed.group(1)} passed")
    _test_cache[path_sym] = result
    return result


def _render_markdown(dossier: dict) -> str:
    lines = [
        "# Patent Claim-Support Dossier",
        "",
        "**Generated automatically by `backend/scripts/build_dossier.py`. This is evidence",
        "tooling, not legal advice** — every citation below is verified against the actual",
        "repository state at build time, but novelty, validity and claim scope are",
        "determinations for a registered patent attorney. See `docs/PRE_FILING_CHECKLIST.md`.",
        "",
        f"Config integrity (`backend/data/dase_profiles.json`): `sha256:{dossier['configSha256']}`",
        "",
    ]
    not_reduced = []
    for claim in dossier["claims"]:
        lines += [f"## {claim['id']}", "", claim["text"], "",
                   "| Element | Code | Test | Status |", "|---|---|---|---|"]
        for el in claim["elements"]:
            status = "resolved" if el["resolved"] else "**NOT REDUCED TO PRACTICE**"
            lines.append(f"| {el['id']} | `{el['code']}` | `{el['test']}` | {status} |")
            if not el["resolved"]:
                not_reduced.append(el)
        lines.append("")

    if not_reduced:
        lines += ["## NOT YET REDUCED TO PRACTICE", ""]
        for el in not_reduced:
            detail = el["code_detail"] if not el["code_resolved"] else el["test_detail"]
            lines.append(f"- **{el['id']}**: {detail}")
        lines.append("")

    return "\n".join(lines)


def build() -> int:
    raw = yaml.safe_load(CLAIM_MAP_PATH.read_text(encoding="utf-8"))
    claims = raw["claims"]

    config_path = REPO_ROOT / raw["build"]["config_hash_source"]
    config_sha256 = hashlib.sha256(config_path.read_bytes()).hexdigest()

    results = []
    any_failed = False

    for claim in claims:
        claim_result = {"id": claim["id"], "text": claim["text"].strip(), "elements": []}
        for element in claim["elements"]:
            code_ok, code_msg = _resolve_code(element["code"])
            test_ok, test_msg = _resolve_test(element["test"])
            resolved = code_ok and test_ok
            any_failed = any_failed or not resolved

            evidence = dict(element.get("evidence") or {})
            if evidence.get("sha256") == "auto":
                evidence["sha256"] = config_sha256

            claim_result["elements"].append({
                "id": element["id"], "text": element.get("text", ""),
                "code": element["code"], "code_resolved": code_ok, "code_detail": code_msg,
                "test": element["test"], "test_resolved": test_ok, "test_detail": test_msg,
                "evidence": evidence, "resolved": resolved,
            })
        results.append(claim_result)

    dossier = {
        "generatedBy": "backend/scripts/build_dossier.py",
        "claimMapVersion": raw.get("version"),
        "configSha256": config_sha256,
        "allResolved": not any_failed,
        "claims": results,
    }

    OUT_JSON.write_text(json.dumps(dossier, indent=2), encoding="utf-8")
    OUT_MD.write_text(_render_markdown(dossier), encoding="utf-8")
    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_MD}")

    if any_failed:
        print("\nFAILED — one or more citations did not resolve. See 'NOT YET REDUCED TO PRACTICE'.")
        return 1
    print("\nAll citations resolved.")
    return 0


if __name__ == "__main__":
    sys.exit(build())
