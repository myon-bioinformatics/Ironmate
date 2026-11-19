"""Write JUnit evidence from GitHub Actions setup-step outcomes."""

import os
import sys
from pathlib import Path
from xml.etree import ElementTree as ET


def main():
    suite_name, destination = sys.argv[1:]
    suite = ET.Element("testsuite", name=suite_name)
    errors = skipped = 0
    for line in os.environ["SETUP_OUTCOMES"].splitlines():
        step, outcome = line.split("=", 1)
        case = ET.SubElement(suite, "testcase", classname=suite_name, name=step)
        if outcome == "failure":
            ET.SubElement(case, "error", type="SetupError", message=f"{step} failed")
            errors += 1
        elif outcome in ("", "skipped", "cancelled"):
            ET.SubElement(case, "skipped", message=outcome or "not run")
            skipped += 1
        elif outcome != "success":
            raise ValueError(f"Unexpected step outcome: {outcome!r}")
    suite.attrib.update(tests=str(len(suite)), errors=str(errors), failures="0", skipped=str(skipped))
    report = Path(destination)
    report.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(suite).write(report, encoding="utf-8", xml_declaration=True)


if __name__ == "__main__":
    main()
