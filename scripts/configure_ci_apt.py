"""Bound CI apt stalls without changing sources, keys, or authentication.

Only the known GitHub-hosted runner mirror list is reprioritized. The official
HTTPS archive is already in that list; retain every URI and fallback. Unknown
or missing mirror lists are left alone rather than guessing their policy.

``--archives DIR`` also points apt's download directory at DIR, so a workflow can
restore and save the .deb files with actions/cache. ``--finish DIR`` (after the
installs) drops downloads apt can no longer install, makes DIR readable for the
cache upload and prints ``changed=true|false`` for $GITHUB_OUTPUT. apt still checks
every cached file against the signed indexes, so a stale or bad file is fetched again.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys


# Sort after the runner's zz-retries. These are per-file retry / connection and
# data-idle limits, not a total install deadline; workflow steps have their own.
APT_CONFIG = '''Acquire::Retries "1";
Acquire::http::Timeout "15";
Acquire::https::Timeout "15";
APT::Update::Error-Mode "any";
'''
ARCHIVES_CONFIG = 'Dir::Cache::Archives "{}/";\n'
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


def deb_names(archives):
    return sorted(path.name for path in Path(archives).glob("*.deb"))


def snapshot_path(archives):
    """The restored file list lives next to DIR, outside what gets cached."""
    archives = Path(archives)
    return archives.with_name(archives.name + ".restored")


def configure(apt_root, archives=None):
    apt_root = Path(apt_root)
    config = APT_CONFIG
    if archives is not None:
        archives = Path(archives).resolve()
        (archives / "partial").mkdir(parents=True, exist_ok=True)
        snapshot_path(archives).write_text("".join(f"{name}\n" for name in deb_names(archives)),
                                            encoding="utf-8")
        config += ARCHIVES_CONFIG.format(archives)
    (apt_root / "apt.conf.d" / CONFIG_NAME).write_text(config, encoding="utf-8")
    mirrors = apt_root / "apt-mirrors.txt"
    if mirrors.exists():
        original = mirrors.read_bytes().decode("utf-8")
        preferred = prefer_existing_archive(original)
        if preferred != original:
            mirrors.write_text(preferred, encoding="utf-8")
            print("Preferred the existing official HTTPS archive; all mirrors retained.")
            return
    print("Kept existing mirror configuration (not the stock list, or already preferred).")


def finish(archives, run=subprocess.run):
    """Return whether the .deb set differs from what configure() saw restored."""
    archives = Path(archives).resolve()
    run(["apt-get", "autoclean", "-qq"], check=True, timeout=120)
    shutil.rmtree(archives / "partial", ignore_errors=True)
    (archives / "lock").unlink(missing_ok=True)
    # Run under sudo: hand the directory back to the runner user for the cache upload.
    uid = int(os.environ.get("SUDO_UID", os.getuid()))
    gid = int(os.environ.get("SUDO_GID", os.getgid()))
    for path in [archives, *archives.iterdir()]:
        os.chown(path, uid, gid)
    restored = snapshot_path(archives)
    before = restored.read_text(encoding="utf-8").splitlines() if restored.exists() else None
    return deb_names(archives) != before


def main(argv):
    if not argv:
        configure("/etc/apt")
    elif len(argv) == 2 and argv[0] == "--archives":
        configure("/etc/apt", argv[1])
    elif len(argv) == 2 and argv[0] == "--finish":
        print(f"changed={'true' if finish(argv[1]) else 'false'}")
    else:
        sys.exit("usage: configure_ci_apt.py [--archives DIR | --finish DIR]")


if __name__ == "__main__":
    main(sys.argv[1:])
