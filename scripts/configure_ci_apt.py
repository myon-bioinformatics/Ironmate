"""Bound CI apt stalls without changing sources, keys, or authentication.

Only the known GitHub-hosted runner mirror list is reprioritized. The official
HTTPS archive is already in that list; retain every URI and fallback. Unknown
or missing mirror lists are left alone rather than guessing their policy.
"""
from pathlib import Path


# Sort after the runner's zz-retries. These are per-file retry / connection and
# data-idle limits, not a total install deadline; workflow steps have their own.
APT_CONFIG = '''Acquire::Retries "1";
Acquire::http::Timeout "15";
Acquire::https::Timeout "15";
APT::Update::Error-Mode "any";
'''
CONFIG_NAME = "zzz-ironmate-ci"
# Stock format: actions/runner-images images/ubuntu/scripts/build/configure-apt-sources.sh
AZURE = ("http://azure.archive.ubuntu.com/ubuntu/", "priority:1")
ARCHIVE = ("https://archive.ubuntu.com/ubuntu/", "priority:2")
SECURITY = ("https://security.ubuntu.com/ubuntu/", "priority:3")


def prefer_existing_archive(text):
    """Change only the stock list's archive priority, never add a mirror."""
    lines = text.split("\n")
    # APT requires a tab between URI and metadata; spaces alone are not valid.
    entries = [tuple(line.split("\t")) for line in lines
               if line and not line.startswith("#")]
    if len(entries) != 3 or set(entries) != {AZURE, ARCHIVE, SECURITY}:
        return text
    return "\n".join(line.replace("priority:2", "priority:0")
                     if tuple(line.split("\t")) == ARCHIVE else line for line in lines)


def configure(apt_root):
    apt_root = Path(apt_root)
    (apt_root / "apt.conf.d" / CONFIG_NAME).write_text(APT_CONFIG, encoding="utf-8")
    mirrors = apt_root / "apt-mirrors.txt"
    if mirrors.exists():
        original = mirrors.read_bytes().decode("utf-8")
        preferred = prefer_existing_archive(original)
        if preferred != original:
            mirrors.write_text(preferred, encoding="utf-8")
            print("Preferred the existing official HTTPS archive; all mirrors retained.")
            return
    print("Kept existing mirror configuration (not the stock list, or already preferred).")


if __name__ == "__main__":
    configure("/etc/apt")
