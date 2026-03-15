# CONTRIBUTING.md

## File Management Guidelines

This document defines the unified rules for all files in this repository.
Follow these conventions when adding or modifying any file.

---

### 1. First-Line File Name Comment (All File Types)

Every file must include its own file name as a comment on the **first line**.

| File type | First-line format |
|-----------|-------------------|
| Python (`.py`) | `# filename.py` |
| Markdown (`.md`) | `# filename.md` |
| YAML (`.yaml` / `.yml`) | `# filename.yaml` |
| Shell script (`.sh`) | `# filename.sh` |

---

### 2. Python Module Exports (`__all__`)

All Python files must declare `__all__` explicitly.

- The **second line** of every Python file must be a comment stating the number of publicly exported names:

```
# __all__: <count>
```

- Immediately after the header comments, define `__all__` as a list of strings.
- Only include names intended for external use (no leading `_` names).

Example:

```python
# ascii_art.py
# __all__: 5

__all__ = [
    "generate_square",
    "generate_triangle",
    "generate_diamond",
    "get_template",
    "list_templates",
]
```

---

### 3. File Naming Convention

File names consist of **two English words joined by an underscore**.

Examples:

```
ascii_art.py
markdown_market.py
gradio_galleria.py
file_finder.py
llm_launchpad.py
```

---

### 4. Python Import Order

Imports must be grouped and sorted alphabetically within each group.

Order:

1. Standard library
2. Third-party libraries
3. Local modules

Example:

```python
import csv, io, json
from pathlib import Path
from typing import Dict

import gradio as gr

from ascii_art import generate_square
from file_finder import find_files_as_map
```

#### Single-line Import Rule

Whenever possible, multiple imports from the same category should be written on **a single line**.

Preferred:

```python
import argparse, json, sys
```

Avoid:

```python
import argparse
import json
import sys
```

This rule applies to both **standard library and third-party modules**.
Only split imports across multiple lines when required for readability
(e.g., long `from module import (...)` statements).

#### Future Import Rule

If a Python file uses `from __future__ import ...`, it **must appear immediately after the header comments** and **before any other statements**, including `__all__`.

Correct structure:

```python

# filename.py
# __all__: 4
from __future__ import annotations
import json, os

__all__ = [...]

```

Incorrect:

```python
# filename.py
# __all__: 4

__all__ = [...]

from __future__ import annotations
```

This requirement comes from Python's language rules.
`from __future__` imports must appear at the beginning of the file.

---

### 5. Variable and Constant Placement

Top-level variables should appear **after imports**.

Sort them alphabetically when practical.

Example:

```python
BASE_DIR = Path(__file__).resolve().parent
MAX_FILE_SIZE = 5 * 1024 * 1024
```

---

### 6. Avoid Unnecessary Constants

Constants should only be introduced when they improve reuse.

Preferred:

```python
if suffix == ".md":
```

Avoid:

```python
_MARKDOWN_EXTENSION = ".md"
```

unless reused across modules.

---

### 7. Helper Function Style

Reusable internal logic should be extracted into helper functions.

Private helpers must start with `_`.

Example:

```python
def _detect_kind(path: Path) -> str:
```

Public functions exported via `__all__` **must not start with `_`**.

---

### 8. Function Order Rule

Python files should follow a consistent structure.

Order:

1. imports
2. constants
3. private helper functions (`_name`)
4. public functions (listed in `__all__`)
5. entry point (`if __name__ == "__main__":`)

Example:

```python
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _helper():
    ...


def public_function():
    ...


if __name__ == "__main__":
    public_function()
```

This ordering makes files easier to scan and maintain.

---

### 9. Prefer Early Returns

Use guard clauses to avoid deep nesting.

Preferred:

```python
if not filepath:
    return "Please specify a file path."
```

---

### 10. Prefer Generator Expressions

Use generator expressions instead of temporary lists when possible.

Preferred:

```python
return "\n".join(
    f"{'#' * sec['level']} {sec['title']}"
    for sec in sections
)
```

Avoid:

```python
lines = []
for sec in sections:
    lines.append(...)
return "\n".join(lines)
```

---

### 11. Tuple Prefix Matching

When checking multiple prefixes, prefer tuple matching.

Preferred:

```python
if raw.startswith(("[error]", "[missing]", "[too_large]")):
```

Avoid:

```python
if raw.startswith("[error]") or raw.startswith("[missing]"):
```

---

### 12. Module Responsibility Rule

Each module should have **a clear single responsibility**.

Examples:

```
ascii_art.py        -> ASCII art generation
markdown_market.py  -> Markdown utilities
file_finder.py      -> file discovery
gradio_galleria.py  -> UI layer
```

Avoid mixing unrelated responsibilities inside the same module.

---

### 13. UI / Logic Separation Rule

User interface code should remain separate from business logic.

Structure example:

```
core logic
    ↓
helper functions
    ↓
UI layer (Gradio / CLI / API)
```

Example:

```python
def process_markdown(text: str) -> str:
    ...


def build_ui():
    ...
```

Benefits:

- logic becomes reusable
- easier testing
- easier future CLI / API support

---

### 14. Design Philosophy

This repository prioritizes:

- clarity over cleverness
- minimal code duplication
- predictable structure
- readable imports and variables

The goal is to keep every module **easy to understand and safe to modify**.
