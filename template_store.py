# template_store.py
# __all__: 4

__all__ = [
    "list_ascii_templates",
    "load_ascii_template",
    "list_prompt_templates",
    "load_prompt_template",
]

import json
from pathlib import Path

import yaml

ASCII_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates_ascii"
PROMPT_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates_prompt"


def _load_json_file(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return {}
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _load_yaml_file(path: Path) -> dict:
    if yaml is None:
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError:
        return {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def list_ascii_templates() -> list[str]:
    """Return available ASCII template names from templates_ascii/*.txt."""
    if not ASCII_TEMPLATE_DIR.exists():
        return []
    return sorted(path.stem for path in ASCII_TEMPLATE_DIR.glob("*.txt"))


def load_ascii_template(name: str) -> str:
    """Load a single ASCII template by name from templates_ascii/<name>.txt."""
    filename = f"{name.strip().lower()}.txt"
    path = ASCII_TEMPLATE_DIR / filename
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def list_prompt_templates() -> list[str]:
    """Return available prompt template base names from yaml/json files."""
    if not PROMPT_TEMPLATE_DIR.exists():
        return []
    names = {
        path.stem
        for path in PROMPT_TEMPLATE_DIR.glob("*.yaml")
    } | {
        path.stem
        for path in PROMPT_TEMPLATE_DIR.glob("*.yml")
    } | {
        path.stem
        for path in PROMPT_TEMPLATE_DIR.glob("*.json")
    }
    return sorted(names)


def load_prompt_template(name: str) -> dict:
    """Load a prompt template by base name from yaml/yml/json."""
    base = name.strip()
    yaml_path = PROMPT_TEMPLATE_DIR / f"{base}.yaml"
    yml_path = PROMPT_TEMPLATE_DIR / f"{base}.yml"
    json_path = PROMPT_TEMPLATE_DIR / f"{base}.json"

    if yaml_path.exists():
        return _load_yaml_file(yaml_path)
    if yml_path.exists():
        return _load_yaml_file(yml_path)
    if json_path.exists():
        return _load_json_file(json_path)
    return {}
