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

- The **second line** of every Python file must be a comment stating the number of
  publicly exported names: `# __all__: <count>`
- Immediately after the header comments, define `__all__` as a list of strings.
- Only include names intended for external use (i.e., no leading-underscore names).

**Example:**

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

File names consist of **two English words joined by an underscore**, chosen so
the meaning is clear at a glance.

Examples: `ascii_art.py`, `markdown_market.py`, `llm_launchpad.py`,
`gradio_galleria.py`, `file_finder.py`

---

### 4. Examples by File Type

#### Python

```python
# my_module.py
# __all__: 2

__all__ = ["public_func_a", "public_func_b"]


def public_func_a() -> str:
    ...


def public_func_b() -> int:
    ...
```

#### Markdown

```markdown
# my_doc.md

Content goes here.
```

#### YAML

```yaml
# config.yaml
key1: value1
key2: value2
```

#### Shell Script

```bash
# setup.sh
#!/bin/bash
echo "Setting up the environment..."
```

---

### 5. Summary

- **All files**: first line = `# <filename>`
- **Python files**: second line = `# __all__: <count>`, followed by an explicit
  `__all__` list
- **File names**: two descriptive English words separated by `_`
