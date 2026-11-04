# Focused standard-library test discovery

Run from this repository root with Python 3.11 or newer. These commands use
Python’s built-in test runner; the listed checks need no third-party Python
package or browser installation. `-S` disables automatic `site` initialization
and its usual site-packages path additions; it is not a complete isolation boundary.

```sh
python -S -m unittest discover -s tests -p test_adaptive_fingerprint.py -v
```

Validated on Linux / CPython 3.12.14: **5 tests, exit 0** (2026-11-03).

To narrow the first command to a test name, use the built-in `-k` filter:

```sh
python -S -m unittest discover -s tests -p test_adaptive_fingerprint.py -v -k test_lazy_gate
```

`-s` is the discovery start directory, `-p` matches test filenames, `-k`
filters test names, `-v` prints each executed test, and `-f` stops at the first
failure. Quote filename patterns so the shell does not expand them. Check the
final `Ran N tests` line: zero tests is not a successful verification, even
though unittest can exit 0. `-k` runs selected tests; it is not a list-only mode.

These are focused checks, not the complete project suite. Keep the existing
pytest/CI command for full coverage and native JUnit or fixture support.
Unittest does not collect module-level pytest functions or apply pytest
fixtures, parametrization, markers, conftest hooks or configured pythonpath.
A broad `test*.py` pattern can import pytest-only modules and fail under `-S`.
Do not add an extra CI pass over tests already owned by pytest just to expose
this local command. No custom discovery runner is required.
