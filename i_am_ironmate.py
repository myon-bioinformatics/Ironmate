# i_am_ironmate.py
# __all__: 2

from __future__ import annotations

import argparse, json, sys
from pathlib import Path

from ascii_art import get_template, render_prompt_ascii
from markdown_market import save_markdown
from llm_launchpad import DEFAULT_LIGHT_MODEL, DEFAULT_TOOL_MODEL, TransformersDualLLM, default_tool_schema, execute_allowed_tool

__all__ = ["build_parser", "main"]

def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--light-model", default=None, help="Override light model id (HF repo or local path)")
    common.add_argument("--tool-model", default=None, help="Override tool model id (HF repo or local path)")
    common.add_argument("--no-4bit", action="store_true", help="Disable 4-bit quantization")

    p = argparse.ArgumentParser(prog="i_am_ironmate.py")
    sub = p.add_subparsers(dest="mode", required=True)

    p_light = sub.add_parser(
        "light",
        parents=[common],
        help="Use the light model for text generation",
    )
    p_light.add_argument("--prompt", required=True, help="User prompt")

    p_tool = sub.add_parser(
        "tool",
        parents=[common],
        help="Use the tool model to output JSON tool call",
    )
    p_tool.add_argument("--prompt", required=True, help="User prompt")
    p_tool.add_argument("--dry-run", action="store_true", help="Do not execute tool; only print JSON")
    p_tool.add_argument("--print-raw", action="store_true", help="Print raw model text too")

    p_repl = sub.add_parser(
        "tool-repl",
        parents=[common],
        help="Keep the tool model loaded and accept prompts interactively",
    )
    p_repl.add_argument("--print-raw", action="store_true", help="Print raw model text too")

    p_ascii = sub.add_parser(
        "ascii",
        parents=[common],
        help="Generate ASCII art directly with the light model",
    )
    p_ascii.add_argument("--prompt", required=True, help="ASCII art prompt")

    p_ascii_save = sub.add_parser(
        "ascii-save",
        parents=[common],
        help="Generate ASCII art directly with the light model and save it to a file",
    )
    p_ascii_save.add_argument("--prompt", required=True, help="ASCII art prompt")
    p_ascii_save.add_argument("--output", required=True, help="Output file path")

    p_template_save = sub.add_parser(
        "template-save",
        parents=[common],
        help="Save a predefined ASCII template to a file",
    )
    p_template_save.add_argument("--name", required=True, help="Template name")
    p_template_save.add_argument("--output", required=True, help="Output file path")

    return p


def _normalize_output_path(output: str) -> str:
    return str(Path(output).resolve())


def _run_ascii_prompt(llm: TransformersDualLLM, prompt: str) -> int:
    content = render_prompt_ascii(prompt, llm)
    if not content:
        print("Failed to generate ASCII art.", file=sys.stderr)
        return 2
    print(content)
    return 0


def _run_ascii_save(llm: TransformersDualLLM, prompt: str, output: str) -> int:
    filepath = _normalize_output_path(output)
    content = render_prompt_ascii(prompt, llm)
    if not content:
        print("Failed to generate ASCII art.", file=sys.stderr)
        return 2

    msg = save_markdown(content.rstrip() + "\n", filepath)
    print(msg)
    return 0


def _run_template_save(name: str, output: str) -> int:
    filepath = _normalize_output_path(output)
    content = get_template(name.strip().lower())
    if not content:
        print(f"Unknown ASCII template: {name}", file=sys.stderr)
        return 2

    msg = save_markdown(content.rstrip() + "\n", filepath)
    print(msg)
    return 0


def _run_tool_prompt(llm: TransformersDualLLM, prompt: str, dry_run: bool = False, print_raw: bool = False) -> int:
    schema = default_tool_schema()
    res = llm.generate_tool(prompt, tool_schema=schema)

    if print_raw:
        print("----- RAW MODEL TEXT -----", file=sys.stderr)
        print(res.text, file=sys.stderr)
        print("--------------------------", file=sys.stderr)

    tool_json = llm.extract_first_json(res.text)
    if tool_json is None:
        print("Failed to parse tool JSON from model output.", file=sys.stderr)
        print("Raw:", res.text, file=sys.stderr)
        return 2

    print(json.dumps(tool_json, ensure_ascii=False))

    if dry_run:
        return 0

    msg, raw = execute_allowed_tool(tool_json, llm=llm)
    print(msg)

    content = raw.get("result", {}).get("content", "") if isinstance(raw, dict) else ""
    if tool_json.get("tool") == "generate_ascii_art" and content:
        print(content)

    return 0


def _run_tool_repl(llm: TransformersDualLLM, print_raw: bool = False) -> int:
    print("Ironmate tool REPL. Type 'exit' or 'quit' to stop.")
    while True:
        try:
            prompt = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if prompt.lower() in {"exit", "quit"}:
            return 0
        if not prompt:
            continue

        code = _run_tool_prompt(llm, prompt=prompt, dry_run=False, print_raw=print_raw)
        if code != 0:
            print(f"[warn] command returned exit code {code}", file=sys.stderr)


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)

    llm = TransformersDualLLM(
        light_model=args.light_model or DEFAULT_LIGHT_MODEL,
        tool_model=args.tool_model or DEFAULT_TOOL_MODEL,
        load_4bit=not args.no_4bit,
    )

    if args.mode == "light":
        res = llm.generate_light(args.prompt)
        print(res.text)
        return 0

    if args.mode == "tool":
        return _run_tool_prompt(
            llm,
            prompt=args.prompt,
            dry_run=args.dry_run,
            print_raw=args.print_raw,
        )

    if args.mode == "tool-repl":
        return _run_tool_repl(llm, print_raw=args.print_raw)

    if args.mode == "ascii":
        return _run_ascii_prompt(llm, prompt=args.prompt)

    if args.mode == "ascii-save":
        return _run_ascii_save(llm, prompt=args.prompt, output=args.output)

    if args.mode == "template-save":
        return _run_template_save(name=args.name, output=args.output)

    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
