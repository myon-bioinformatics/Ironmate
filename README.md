# Ironmate

## Local LLM (Transformers)

### Install
```bash
pip install -r requirements.txt
```

### Defaults (overrideable)
- light: `Qwen/Qwen2.5-1.5B-Instruct`
- tool : `Qwen/Qwen2.5-7B-Instruct`

Override:
```bash
export IRONMATE_LIGHT_MODEL="Qwen/Qwen2.5-1.5B-Instruct"
export IRONMATE_TOOL_MODEL="Qwen/Qwen2.5-7B-Instruct"
export IRONMATE_LOAD_4BIT="1"
```

### Light
```bash
python i_am_ironmate.py light --prompt "Markdownで実験ログのテンプレを作って"
```

### Tool (safe whitelist)
The tool model outputs one-line JSON:
```json
{"tool":"save_markdown","args":{"content":"# Hello","filepath":"notes/test.md"}}
```

Run:
```bash
python i_am_ironmate.py tool --prompt "notes/test.md に '# Hello' を保存して"
```

Dry-run:
```bash
python i_am_ironmate.py tool --dry-run --prompt "notes/test.md に '# Hello' を保存して"
```
