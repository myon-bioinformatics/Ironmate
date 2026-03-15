# i_am_ironmate.py
# __all__: 2

__all__ = ["build_parser", "main"]

from __future__ import annotations

import argparse, json, sys

from llm_launchpad import (
    DEFAULT_LIGHT_MODEL,
    DEFAULT_TOOL_MODEL,
    TransformersDualLLM,
    default_tool_schema,
    execute_allowed_tool,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="i_am_ironmate.py")
    sub = p.add_subparsers(dest="mode", required=True)

    p_light = sub.add_parser("light", help="Use the light (~2B) model for text generation")
    p_light.add_argument("--prompt", required=True, help="User prompt")

    p_tool = sub.add_parser("tool", help="Use the tool (~8B) model to output JSON tool call")
    p_tool.add_argument("--prompt", required=True, help="User prompt")
    p_tool.add_argument("--dry-run", action="store_true", help="Do not execute tool; only print JSON")
    p_tool.add_argument("--print-raw", action="store_true", help="Print raw model text too")

    p.add_argument("--light-model", default=None, help="Override light model id (HF repo or local path)")
    p.add_argument("--tool-model", default=None, help="Override tool model id (HF repo or local path)")
    p.add_argument("--no-4bit", action="store_true", help="Disable 4-bit quantization")
    return p


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
        schema = default_tool_schema()
        res = llm.generate_tool(args.prompt, tool_schema=schema)

        if args.print_raw:
            print("----- RAW MODEL TEXT -----", file=sys.stderr)
            print(res.text, file=sys.stderr)
            print("--------------------------", file=sys.stderr)

        tool_json = llm.extract_first_json(res.text)
        if tool_json is None:
            print("Failed to parse tool JSON from model output.", file=sys.stderr)
            print("Raw:", res.text, file=sys.stderr)
            return 2

        # Print JSON for transparency/logging
        print(json.dumps(tool_json, ensure_ascii=False))

        if args.dry_run:
            return 0

        msg, _raw = execute_allowed_tool(tool_json, llm=llm)
        print(msg)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
