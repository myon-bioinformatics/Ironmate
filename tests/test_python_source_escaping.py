"""Guard against accidental literal backslash-n source line separators.

Use Python's tokenizer: legitimate string literals containing \\n remain allowed.
"""
import io
from pathlib import Path
import tokenize

ROOT = Path(__file__).resolve().parents[1]


def test_python_sources_do_not_contain_stray_escaped_newlines():
    failures = []
    for path in sorted(ROOT.rglob("*.py")):
        if any(part in {".git", ".venv", "node_modules", "build", ".vendor-sync-tools"} for part in path.relative_to(ROOT).parts):
            continue
        data = path.read_bytes()
        try:
            compile(data, str(path), "exec")
        except SyntaxError as exc:
            failures.append(f"{path.relative_to(ROOT)}:{exc.lineno}: {exc.msg}")
            continue
        tokens = tokenize.tokenize(io.BytesIO(data).readline)
        for token in tokens:
            if token.type == tokenize.ERRORTOKEN and token.string == "\\":
                failures.append(f"{path.relative_to(ROOT)}:{token.start[0]}: stray backslash")
    assert not failures, "\n".join(failures)
