"""Contract tests for reusing vendor Markdown's opaque Mermaid helpers."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "markdown.py"


def vendor_markdown():
    spec = importlib.util.spec_from_file_location("ironmate_vendor_markdown", VENDOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mermaid_flowchart_roundtrip_without_custom_parser():
    markdown = vendor_markdown()
    source = 'flowchart LR\n  A["Box A"] --> B["Box B"]\n  B --> C["Box C"]'
    fenced = markdown.mermaid_block(source)
    assert markdown.extract_mermaid_blocks(fenced) == [source]
    assert fenced.count("mermaid") == 1


def test_mermaid_opaque_source_does_not_claim_editable_pptx():
    markdown = vendor_markdown()
    source = 'flowchart RL\n  C["Box C"] --> A["Box A"]'
    fenced = markdown.mermaid_block(source)
    assert markdown.extract_mermaid_blocks(fenced) == [source]
    # Mermaid edges are diagram source, not a PPTX edge-anchor contract.
    assert "RL" in fenced and "C" in fenced
