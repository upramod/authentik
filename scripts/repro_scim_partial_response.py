"""Verify the reported failure and a full-response control on unchanged upstream."""
import json
import pathlib
import subprocess
import xml.etree.ElementTree as ET

out = pathlib.Path("evidence")
out.mkdir(exist_ok=True)
report = pathlib.Path("unittest.xml")
report.unlink(missing_ok=True)
prefix = "authentik.providers.scim.tests.test_user.SCIMUserTests."
run = subprocess.run(
    ["uv", "run", "python", "manage.py", "test", "--noinput",
     prefix + "test_unchanged_sync_partial_response",
     prefix + "test_unchanged_sync_full_response"],
    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
)
(out / "baseline.log").write_text(run.stdout)
print(run.stdout)
valid = False
if report.exists():
    (out / "baseline.xml").write_bytes(report.read_bytes())
    root = ET.parse(report).getroot()
    cases = root.findall(".//testcase")
    failures = root.findall(".//failure")
    partial = [c for c in cases if c.get("name") == "test_unchanged_sync_partial_response"]
    control = [c for c in cases if c.get("name") == "test_unchanged_sync_full_response"]
    valid = (
        run.returncode == 1 and len(cases) == 2 and len(failures) == 1
        and len(partial) == 1 and partial[0].find("failure") is not None
        and len(control) == 1 and control[0].find("failure") is None
        and not root.findall(".//error") and not root.findall(".//skipped")
        and "2 != 0" in (failures[0].get("message", "") + (failures[0].text or ""))
    )
(out / "result.json").write_text(json.dumps({
    "baseline": "4e8e48233e639c558e433488506268c382e57b99",
    "returncode": run.returncode,
    "partial_response_two_redundant_puts_full_response_zero": valid,
}, indent=2))
if not valid:
    raise SystemExit("Expected regression/control outcome not reproduced")
