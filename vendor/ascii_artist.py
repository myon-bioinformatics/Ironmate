# ascii_artist.py
# metadata: __all__=42 | base_sha=7c21bacfac7b60327b77f9b31a87869ef7838a7e | updated_at=2026-09-23T05:39:43Z
"""ASCII art generation, conversion, layout and text-based diagrams in one standard-library file."""

__all__ = [
    "generate_square",
    "generate_triangle",
    "generate_diamond",
    "generate_box",
    "get_template",
    "list_templates",
    "banner",
    "banner_charset",
    "render_table",
    "render_prompt_ascii",
    "to_web_ui_v1_html",
    "SUPPORTED",
    "UNSUPPORTED",
    "Node",
    "Edge",
    "Diagram",
    "diagram",
    "to_dict",
    "from_dict",
    "render_diagram",
    "flow",
    "branch",
    "tree",
    "to_json",
    "from_json",
    "to_edges",
    "from_edges",
    "to_adjacency",
    "from_adjacency",
    "to_mermaid",
    "from_mermaid",
    "to_dot",
    "from_dot",
    "to_markdown_outline",
    "from_markdown_outline",
    "inventory",
    "validate_flow",
    "flow_html",
    "flow_mermaid",
    "flow_document",
    "flow_css",
    "patch_flow",
]

import argparse, csv, html, json, re, sys, unicodedata
from collections import deque; from dataclasses import dataclass; from typing import Any, Callable, Iterable, Literal, Mapping, Protocol

SUPPORTED = {
    "generation": [
        "square / triangle / diamond / box text-art generation",
        "non-empty single-line string tokens, including Unicode",
        "built-in text-art templates",
        "built-in 5-row banner font (A-Z, 0-9, space and common punctuation)",
        "plain-text tables with display_width-based (CJK-aware) padding",
        "Diagram IR with deterministic flow / branch / tree rendering",
        "lossless Diagram <-> dict / JSON serialization",
        "edge-list and adjacency adapters",
        "Mermaid / DOT / Markdown-outline subset conversion",
        "Diagram inventory and topology statistics",
        "web-ui HTML contract v1 document emission for Diagram or text art",
    ],
    "llm_adapter": [
        "plain callable generator",
        "object exposing generate_light(prompt)",
        "string result or object with string .text attribute",
    ],
    "sanitization": [
        "common system/user/assistant wrapper lines",
        "Markdown backtick or tilde fences",
        "common ASCII-art preamble lines",
        "CRLF/CR line-ending normalization",
    ],
    "distribution": [
        "single-file copying and vendoring",
        "Python standard-library-only runtime",
    ],
}

UNSUPPORTED = {
    "layout": [
        "terminal-cell-perfect alignment for wide Unicode or emoji",
        "font-aware glyph measurement",
        "automatic monospace capability detection",
    ],
    "rendering": [
        "ANSI color rendering",
        "terminal capability negotiation",
        "image/raster rendering or image decoding",
        "banner glyphs outside the built-in A-Z / 0-9 / punctuation set",
        "multi-line table cells or automatic column wrapping",
    ],
    "parsing": [
        "full Markdown parsing",
        "general-purpose graph layout or cyclic graph rendering",
        "fuzzy removal of arbitrary prose around generated art",
    ],
    "integration": [
        "direct dependency on a specific LLM SDK",
        "repository-local runtime assets or configuration files",
    ],
}


@dataclass(frozen=True)
class Node:
    """One logical node in the diagram intermediate representation."""

    id: str
    label: str


@dataclass(frozen=True)
class Edge:
    """One directed edge in the diagram intermediate representation."""

    source: str
    target: str


@dataclass(frozen=True)
class Diagram:
    """Small immutable DAG-oriented intermediate representation."""

    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]


def _normalize_node(value: str | Node) -> Node:
    if isinstance(value, Node):
        node = value
    elif isinstance(value, str):
        node = Node(value, value)
    else:
        raise TypeError("nodes must contain strings or Node values")
    if not node.id or "\n" in node.id or "\r" in node.id:
        raise ValueError("node id must be a non-empty single-line string")
    if not node.label or "\n" in node.label or "\r" in node.label:
        raise ValueError("node label must be a non-empty single-line string")
    return node


def _normalize_edge(value: tuple[str, str] | Edge) -> Edge:
    if isinstance(value, Edge):
        edge = value
    elif isinstance(value, tuple) and len(value) == 2:
        edge = Edge(str(value[0]), str(value[1]))
    else:
        raise TypeError("edges must contain Edge values or (source, target) tuples")
    if not edge.source or not edge.target:
        raise ValueError("edge endpoints must be non-empty")
    return edge


def _validate_dag(value: Diagram) -> None:
    node_ids = [node.id for node in value.nodes]
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("node ids must be unique")
    known = set(node_ids)
    for edge in value.edges:
        if edge.source not in known or edge.target not in known:
            raise ValueError("every edge endpoint must reference a known node")
        if edge.source == edge.target:
            raise ValueError("self edges are not supported")

    indegree = {node_id: 0 for node_id in node_ids}
    outgoing = {node_id: [] for node_id in node_ids}
    for edge in value.edges:
        indegree[edge.target] += 1
        outgoing[edge.source].append(edge.target)

    ready = deque(node_id for node_id in node_ids if indegree[node_id] == 0)
    visited = 0
    while ready:
        current = ready.popleft()
        visited += 1
        for target in outgoing[current]:
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
    if visited != len(node_ids):
        raise ValueError("diagram must be acyclic")


def _topological_layers(value: Diagram) -> list[list[str]]:
    _validate_dag(value)
    node_ids = [node.id for node in value.nodes]
    indegree = {node_id: 0 for node_id in node_ids}
    outgoing = {node_id: [] for node_id in node_ids}
    for edge in value.edges:
        indegree[edge.target] += 1
        outgoing[edge.source].append(edge.target)

    rank = {node_id: index for index, node_id in enumerate(node_ids)}
    layer = [node_id for node_id in node_ids if indegree[node_id] == 0]
    layers: list[list[str]] = []
    while layer:
        layers.append(layer)
        following = []
        for source in layer:
            for target in outgoing[source]:
                indegree[target] -= 1
                if indegree[target] == 0:
                    following.append(target)
        # Edge traversal order can differ from input node order.
        layer = sorted(following, key=rank.__getitem__)
    return layers


def diagram(
    nodes: Iterable[str | Node],
    edges: Iterable[tuple[str, str] | Edge] = (),
) -> Diagram:
    """Build and validate a normalized DAG intermediate representation."""

    value = Diagram(
        tuple(_normalize_node(node) for node in nodes),
        tuple(_normalize_edge(edge) for edge in edges),
    )
    _validate_dag(value)
    return value


def to_dict(value: Diagram) -> dict[str, Any]:
    """Serialize a Diagram losslessly to JSON-compatible builtins."""

    _validate_dag(value)
    return {
        "nodes": [{"id": node.id, "label": node.label} for node in value.nodes],
        "edges": [{"source": edge.source, "target": edge.target} for edge in value.edges],
    }


def from_dict(value: Mapping[str, Any]) -> Diagram:
    """Deserialize the canonical dictionary form back into a Diagram."""

    if not isinstance(value, Mapping):
        raise TypeError("diagram data must be a mapping")
    if set(value) - {"nodes", "edges"}:
        raise ValueError("expected nodes/edges Diagram; card flows use validate_flow")
    raw_nodes = value.get("nodes", ())
    raw_edges = value.get("edges", ())
    if not isinstance(raw_nodes, (list, tuple)) or not isinstance(raw_edges, (list, tuple)):
        raise TypeError("nodes and edges must be sequences")

    nodes: list[Node] = []
    for raw in raw_nodes:
        if not isinstance(raw, Mapping):
            raise TypeError("serialized nodes must be mappings")
        node_id = raw.get("id")
        label = raw.get("label")
        if not isinstance(node_id, str):
            raise TypeError(
                f"serialized node id must be str, got {type(node_id).__name__}"
            )
        if not isinstance(label, str):
            raise TypeError(
                f"serialized node {node_id!r} label must be str, got {type(label).__name__}"
            )
        nodes.append(Node(node_id, label))

    edges: list[Edge] = []
    for raw in raw_edges:
        if not isinstance(raw, Mapping):
            raise TypeError("serialized edges must be mappings")
        source = raw.get("source")
        target = raw.get("target")
        if not isinstance(source, str):
            raise TypeError(
                f"serialized edge source must be str, got {type(source).__name__}"
            )
        if not isinstance(target, str):
            raise TypeError(
                f"serialized edge target must be str, got {type(target).__name__}"
            )
        edges.append(Edge(source, target))
    return diagram(nodes, edges)



def to_json(value: Diagram, *, indent: int | None = 2) -> str:
    """Serialize Diagram to canonical JSON. LOSSLESS with from_json()."""

    return json.dumps(to_dict(value), ensure_ascii=False, indent=indent)


def from_json(text: str) -> Diagram:
    """Deserialize canonical Diagram JSON."""

    if not isinstance(text, str):
        raise TypeError("json input must be a string")
    return from_dict(json.loads(text))


def to_edges(value: Diagram) -> list[tuple[str, str]]:
    """Return the directed edge list. NORMALIZED: node labels are omitted."""

    _validate_dag(value)
    return [(edge.source, edge.target) for edge in value.edges]


def from_edges(
    edges: Iterable[tuple[str, str] | Edge],
    *,
    labels: Mapping[str, str] | None = None,
) -> Diagram:
    """Build Diagram from edges in first-seen insertion order (Python 3.7+)."""

    normalized = [_normalize_edge(edge) for edge in edges]
    seen: dict[str, None] = {}
    for edge in normalized:
        seen.setdefault(edge.source, None)
        seen.setdefault(edge.target, None)
    labels = labels or {}
    nodes = [Node(node_id, labels.get(node_id, node_id)) for node_id in seen]
    return diagram(nodes, normalized)


def to_adjacency(value: Diagram) -> dict[str, list[str]]:
    """Return deterministic adjacency mapping for every node."""

    _validate_dag(value)
    result = {node.id: [] for node in value.nodes}
    for edge in value.edges:
        result[edge.source].append(edge.target)
    return result


def from_adjacency(
    value: Mapping[str, Iterable[str]],
    *,
    labels: Mapping[str, str] | None = None,
) -> Diagram:
    """Build Diagram preserving first-seen insertion order (Python 3.7+)."""

    if not isinstance(value, Mapping):
        raise TypeError("adjacency input must be a mapping")
    edges: list[Edge] = []
    seen: dict[str, None] = {}
    for source, targets in value.items():
        if not isinstance(source, str):
            raise TypeError("adjacency keys must be strings")
        seen.setdefault(source, None)
        for target in targets:
            if not isinstance(target, str):
                raise TypeError("adjacency targets must be strings")
            seen.setdefault(target, None)
            edges.append(Edge(source, target))
    labels = labels or {}
    nodes = [Node(node_id, labels.get(node_id, node_id)) for node_id in seen]
    return diagram(nodes, edges)


def _quote_label(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _unquote_label(text: str) -> str:
    result: list[str] = []
    escaped = False
    for char in text:
        if escaped:
            result.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        else:
            result.append(char)
    if escaped:
        result.append("\\")
    return "".join(result)


def _unquote_json_string(encoded: str) -> str:
    """Decode one JSON quoted-string layer used by Mermaid node metadata."""

    return json.loads(f'"{encoded}"')


def to_mermaid(value: Diagram, *, direction: str = "TD") -> str:
    """Serialize a Mermaid subset using compact JSON node metadata for round-trip."""

    _validate_dag(value)
    if direction not in {"TD", "TB", "LR", "RL", "BT"}:
        raise ValueError("unsupported Mermaid direction")
    aliases = {node.id: f"n{index}" for index, node in enumerate(value.nodes)}
    lines = [f"flowchart {direction}"]
    for node in value.nodes:
        # Preserve the original ID inside the emitted label metadata.
        payload = json.dumps(
            {"id": node.id, "label": node.label},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        lines.append(f'    {aliases[node.id]}["{_quote_label(payload)}"]')
    for edge in value.edges:
        lines.append(f"    {aliases[edge.source]} --> {aliases[edge.target]}")
    return "\n".join(lines)


_MERMAID_NODE_RE = re.compile(r'^\s*([A-Za-z0-9_.-]+)\["((?:\\.|[^"])*)"\]\s*$')
_MERMAID_EDGE_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*-->\s*([A-Za-z0-9_.-]+)\s*$")


def from_mermaid(text: str) -> Diagram:
    """Parse the flowchart subset emitted by to_mermaid()."""

    if not isinstance(text, str):
        raise TypeError("Mermaid input must be a string")
    nodes: list[Node] = []
    edges: list[Edge] = []
    for index, line in enumerate(text.splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        if index == 0 and stripped.startswith("flowchart "):
            continue
        node_match = _MERMAID_NODE_RE.fullmatch(line)
        if node_match:
            encoded_payload = node_match.group(2)
            payload_text = _unquote_json_string(encoded_payload)
            payload = json.loads(payload_text)
            if not isinstance(payload, dict):
                raise ValueError("Mermaid node payload must be an object")
            node_id = payload.get("id")
            label = payload.get("label")
            if not isinstance(node_id, str) or not isinstance(label, str):
                raise ValueError("Mermaid node payload requires string id and label")
            nodes.append(Node(node_id, label))
            continue
        edge_match = _MERMAID_EDGE_RE.fullmatch(line)
        if edge_match:
            edges.append(
                Edge(_unquote_label(edge_match.group(1)), _unquote_label(edge_match.group(2)))
            )
            continue
        raise ValueError(f"unsupported Mermaid line: {line!r}")

    alias_to_id = {f"n{index}": node.id for index, node in enumerate(nodes)}
    resolved_edges = [
        Edge(alias_to_id.get(edge.source, edge.source), alias_to_id.get(edge.target, edge.target))
        for edge in edges
    ]
    return diagram(nodes, resolved_edges)


def to_dot(value: Diagram) -> str:
    """Serialize to a small Graphviz DOT digraph subset."""

    _validate_dag(value)
    lines = ["digraph G {"]
    for node in value.nodes:
        lines.append(f'  "{_quote_label(node.id)}" [label="{_quote_label(node.label)}"];')
    for edge in value.edges:
        lines.append(f'  "{_quote_label(edge.source)}" -> "{_quote_label(edge.target)}";')
    lines.append("}")
    return "\n".join(lines)


# Matches one quoted DOT token while allowing backslash-escaped characters.
_DOT_TOKEN = r'"((?:\\.|[^"\\])*)"'
_DOT_NODE_RE = re.compile(
    rf"^\s*{_DOT_TOKEN}\s+\[label={_DOT_TOKEN}\];\s*$"
)
_DOT_EDGE_RE = re.compile(
    rf"^\s*{_DOT_TOKEN}\s*->\s*{_DOT_TOKEN};\s*$"
)


def from_dot(text: str) -> Diagram:
    """Parse the narrow DOT subset emitted by to_dot()."""

    if not isinstance(text, str):
        raise TypeError("DOT input must be a string")
    nodes: list[Node] = []
    edges: list[Edge] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped == "digraph G {" or stripped == "}":
            continue
        node_match = _DOT_NODE_RE.fullmatch(line)
        if node_match:
            nodes.append(
                Node(_unquote_label(node_match.group(1)), _unquote_label(node_match.group(2)))
            )
            continue
        edge_match = _DOT_EDGE_RE.fullmatch(line)
        if edge_match:
            edges.append(
                Edge(_unquote_label(edge_match.group(1)), _unquote_label(edge_match.group(2)))
            )
            continue
        raise ValueError(f"unsupported DOT line: {line!r}")
    return diagram(nodes, edges)


def to_markdown_outline(value: Diagram) -> str:
    """Render a DAG as a normalized ATX-heading outline by topological layer."""

    layers = _topological_layers(value)
    labels = {node.id: node.label for node in value.nodes}
    lines: list[str] = []
    for depth, layer in enumerate(layers, start=1):
        prefix = "#" * min(depth, 6)
        for node_id in layer:
            lines.append(f"{prefix} {labels[node_id]}")
    return "\n".join(lines)


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def from_markdown_outline(text: str) -> Diagram:
    """Parse ATX headings; generated IDs are local n0, n1, ... identifiers.

    Markdown carries no original Diagram IDs, so these generated IDs are a
    normalized representation and must not be treated as preserved source IDs.
    """

    if not isinstance(text, str):
        raise TypeError("Markdown outline input must be a string")
    nodes: list[Node] = []
    edges: list[Edge] = []
    stack: list[tuple[int, str]] = []
    counter = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        match = _HEADING_RE.fullmatch(line)
        if not match:
            raise ValueError(f"unsupported Markdown outline line: {line!r}")
        level = len(match.group(1))
        node_id = f"n{counter}"
        counter += 1
        nodes.append(Node(node_id, match.group(2)))
        while stack and stack[-1][0] >= level:
            stack.pop()
        if stack:
            edges.append(Edge(stack[-1][1], node_id))
        stack.append((level, node_id))
    return diagram(nodes, edges)


def inventory(value: Diagram) -> dict[str, Any]:
    """Return deterministic structural statistics without mutating the Diagram."""

    _validate_dag(value)
    indegree = {node.id: 0 for node in value.nodes}
    outdegree = {node.id: 0 for node in value.nodes}
    for edge in value.edges:
        indegree[edge.target] += 1
        outdegree[edge.source] += 1
    layers = _topological_layers(value)
    return {
        "nodes": len(value.nodes),
        "edges": len(value.edges),
        "roots": [node.id for node in value.nodes if indegree[node.id] == 0],
        "leaves": [node.id for node in value.nodes if outdegree[node.id] == 0],
        "layers": layers,
        "max_depth": max((index + 1 for index, layer in enumerate(layers) if layer), default=0),
        "is_dag": True,
    }


def _charset(name: str) -> dict[str, str]:
    if name == "unicode":
        return {"down": "↓", "tee": "├", "last": "└", "h": "─", "arrow": "→", "pipe": "│"}
    if name == "ascii":
        return {"down": "v", "tee": "+", "last": "\\", "h": "-", "arrow": ">", "pipe": "|"}
    raise ValueError("charset must be 'unicode' or 'ascii'")


def _render_layered_diagram(value: Diagram, *, arrow: str) -> str:
    layers = _topological_layers(value)
    refs = {node.id: index for index, node in enumerate(value.nodes, start=1)}
    labels = {node.id: node.label for node in value.nodes}
    rank = {node_id: index for index, layer in enumerate(layers) for node_id in layer}
    edges_by_layer: list[list[Edge]] = [[] for _ in layers]
    for edge in value.edges:
        edges_by_layer[rank[edge.source]].append(edge)

    sections = []
    for index, layer in enumerate(layers):
        lines = [f"Layer {index + 1}"]
        lines.extend(f"  [{refs[node_id]}] {labels[node_id]}" for node_id in layer)
        lines.extend(
            f"  [{refs[edge.source]}] {arrow} [{refs[edge.target]}]"
            for edge in edges_by_layer[index]
        )
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def render_diagram(
    value: Diagram, *, charset: str = "unicode", layout: str = "adjacency"
) -> str:
    """Render a DAG in text, preserving the default adjacency output.

    The optional layered layout lists nodes once in topological layers.
    Connectors are shown under their source layer with numbered references,
    so edges that skip layers or link identically labeled nodes stay unambiguous.
    The charset controls the diagram symbols, not the user-supplied labels.
    """

    chars = _charset(charset)
    if layout == "layered":
        return _render_layered_diagram(value, arrow=chars["arrow"])
    if layout != "adjacency":
        raise ValueError("layout must be 'adjacency' or 'layered'")
    _validate_dag(value)
    labels = {node.id: node.label for node in value.nodes}
    outgoing = {node.id: [] for node in value.nodes}
    for edge in value.edges:
        outgoing[edge.source].append(edge.target)

    lines: list[str] = []
    for node in value.nodes:
        lines.append(labels[node.id])
        targets = outgoing[node.id]
        for index, target in enumerate(targets):
            prefix = chars["last"] if index == len(targets) - 1 else chars["tee"]
            lines.append(f"{prefix}{chars['h']}{chars['arrow']} {labels[target]}")
    return "\n".join(lines)


def flow(items: Iterable[str], *, charset: str = "unicode") -> str:
    """Render a deterministic vertical linear flow."""

    labels = [str(item) for item in items]
    if not labels:
        return ""
    if any(not label or "\n" in label or "\r" in label for label in labels):
        raise ValueError("flow labels must be non-empty single-line strings")
    chars = _charset(charset)
    nodes = [Node(str(index), label) for index, label in enumerate(labels)]
    edges = [Edge(str(index), str(index + 1)) for index in range(len(nodes) - 1)]
    _validate_dag(Diagram(tuple(nodes), tuple(edges)))
    return f"\n {chars['down']}\n".join(labels)


def branch(
    root: str,
    branches: Iterable[str],
    target: str | None = None,
    *,
    charset: str = "unicode",
) -> str:
    """Render a one-to-many, optionally many-to-one, topology."""

    branch_labels = [str(label) for label in branches]
    labels = [root, *branch_labels] + ([target] if target is not None else [])
    if any(not isinstance(label, str) or not label or "\n" in label or "\r" in label for label in labels):
        raise ValueError("branch labels must be non-empty single-line strings")
    if not branch_labels:
        return root if target is None else flow([root, target], charset=charset)

    nodes = [Node("root", root)]
    nodes.extend(Node(f"branch_{index}", label) for index, label in enumerate(branch_labels))
    edges = [Edge("root", f"branch_{index}") for index in range(len(branch_labels))]
    if target is not None:
        nodes.append(Node("target", target))
        edges.extend(Edge(f"branch_{index}", "target") for index in range(len(branch_labels)))
    _validate_dag(Diagram(tuple(nodes), tuple(edges)))

    chars = _charset(charset)
    gap = 4
    branch_line = (" " * gap).join(branch_labels)
    centers: list[int] = []
    cursor = 0
    for label in branch_labels:
        centers.append(cursor + len(label) // 2)
        cursor += len(label) + gap
    total_width = len(branch_line)
    root_start = max(0, (total_width - len(root)) // 2)
    root_line = " " * root_start + root

    connector = [" "] * max(total_width, root_start + len(root))
    root_center = root_start + len(root) // 2
    left, right = centers[0], centers[-1]
    if left == right:
        # Single-branch case: keep a straight vertical connector.
        connector[left] = chars["pipe"]
    else:
        # Multi-branch case: span the first/last branch centers and split at root.
        for pos in range(left, right + 1):
            connector[pos] = chars["h"]
        connector[root_center] = "┼" if charset == "unicode" else "+"
        connector[left] = "┌" if charset == "unicode" else "+"
        connector[right] = "┐" if charset == "unicode" else "+"
    arrows = [" "] * len(connector)
    for center in centers:
        arrows[center] = chars["down"]

    lines = [root_line, " " * root_center + chars["pipe"], "".join(connector).rstrip(), "".join(arrows).rstrip(), branch_line]
    if target is not None:
        join = [" "] * len(connector)
        if left == right:
            # Single-branch convergence is a straight vertical path.
            join[left] = chars["pipe"]
        else:
            # Multi-branch convergence mirrors the fan-out above.

            for pos in range(left, right + 1):
                join[pos] = chars["h"]
            join[left] = "└" if charset == "unicode" else "+"
            join[right] = "┘" if charset == "unicode" else "+"
            join[root_center] = "┴" if charset == "unicode" else "+"
        target_start = max(0, (total_width - len(target)) // 2)
        lines.extend(["".join(join).rstrip(), " " * root_center + chars["down"], " " * target_start + target])
    return "\n".join(lines)


def _tree_lines(
    value: Mapping[str, Any],
    *,
    prefix: str,
    charset: str,
) -> list[str]:
    """Render mapping-shaped descendants iteratively to avoid recursion limits."""

    chars = _charset(charset)
    lines: list[str] = []
    stack: list[tuple[list[tuple[str, Any]], int, str]] = [
        (list(value.items()), 0, prefix)
    ]

    while stack:
        entries, index, current_prefix = stack.pop()
        if index >= len(entries):
            continue

        label, children = entries[index]
        last = index == len(entries) - 1
        elbow = chars["last"] if last else chars["tee"]
        lines.append(f"{current_prefix}{elbow}{chars['h']}{chars['arrow']} {label}")

        # LIFO invariant: push the sibling-resume frame first, then children.
        # The child frame below is popped first, so descendants are fully
        # rendered before this saved frame resumes the next sibling.
        stack.append((entries, index + 1, current_prefix))

        if children:
            if not isinstance(children, Mapping):
                raise TypeError("tree children must be mappings")
            child_prefix = current_prefix + (
                "   " if last else f"{chars['pipe']}  "
            )
            stack.append((list(children.items()), 0, child_prefix))

    return lines

def tree(root: str, children: Mapping[str, Any], *, charset: str = "unicode") -> str:
    """Render a deterministic nested tree from mapping-shaped children."""

    if not root or "\n" in root or "\r" in root:
        raise ValueError("tree root must be a non-empty single-line string")
    if not isinstance(children, Mapping):
        raise TypeError("tree children must be a mapping")
    return "\n".join([root, *_tree_lines(children, prefix="", charset=charset)])


_ASCII_TEMPLATES = {
    "icon_ironmate": "   _______\n  /       \\\n | () | () |\n |   ___   |\n  \\_______/\n  [ IRONMATE ]\n",
    "ironmate": "  _____                                _\n |_   _|  _ __    ___    _ __   _ __  | |__    __ _   ___   ___\n   | |   | '__|  / _ \\  | '_ \\ | '_ \\ | '_ \\  / _` | / __| / __|\n   | |   | |    | (_) | | | | || | | || | | || (_| || (__ | (__\n   |_|   |_|     \\___/  |_| |_||_| |_||_| |_| \\__,_| \\___| \\___|\n  IRONMATE - Your J.A.R.V.I.S-inspired assistant\n",
    "welcome": " __        __   _\n \\ \\      / /__| | ___ ___  _ __ ___   ___\n  \\ \\ /\\ / / _ \\ |/ __/ _ \\| '_ ` _ \\ / _ \\\n   \\ V  V /  __/ | (_| (_) | | | | | |  __/\n    \\_/\\_/ \\___|_|\\___\\___/|_| |_| |_|\\___|\n  to IRONMATE!\n",
    "cat": " /\\_/\\\n( o.o )\n > ^ <\n",
    "heart": " **   **\n***** *****\n *********\n  *******\n   *****\n    ***\n     *\n",
    "tree": "    *\n   ***\n  *****\n *******\n    |\n",
    "coffee": "   ( (\n    ) )\n  ........\n  |      |]\n  \\      /\n   `----'\n",
    "dog": "  __\no-''|\\_____/)\n \\_/|_)     )\n    \\  __  /\n    (_/ (_/\n",
    "fish": "    __\n><((('>\n    ``\n",
    "owl": " ,_,\n(O,O)\n(   )\n-\"-\"-\n",
    "rocket": "    /\\\n   /  \\\n   |()|\n   |  |\n  /|  |\\\n /_|__|_\\\n   /\\/\\\n",
    "star": "     /\\\n____/  \\____\n\\          /\n \\        /\n /   /\\   \\\n/___/  \\___\\\n",
}

_FENCE_LINE_RE = re.compile(r"^\s*(?:`{3,}|~{3,})(?:[A-Za-z0-9_.+-]+)?\s*$")
_PREAMBLE_LINE_RE = re.compile(r"^\s*(?:here(?:\'s| is) your ascii art|ascii art)\s*:\s*$", re.IGNORECASE)
_ROLE_LINE_RE = re.compile(r"^\s*(?:\[(?:system|user|assistant)\]|(?:system|user|assistant))\s*:?\s*$", re.IGNORECASE)


class _SupportsGenerateLight(Protocol):
    def generate_light(self, prompt: str) -> Any:
        ...


def _validate_token(token: str) -> str:
    if not isinstance(token, str):
        raise TypeError("char must be a string token")
    if not token:
        raise ValueError("char must not be empty")
    if "\n" in token or "\r" in token:
        raise ValueError("char must be a single-line token")
    return token


def _generated_text(
    generator: Callable[[str], Any] | _SupportsGenerateLight,
    prompt: str,
) -> str:
    method = getattr(generator, "generate_light", None)
    if callable(method):
        result = method(prompt)
    elif callable(generator):
        result = generator(prompt)
    else:
        raise TypeError("generator must be callable or provide generate_light(prompt)")

    if isinstance(result, str):
        return result
    text = getattr(result, "text", None)
    if isinstance(text, str):
        return text
    raise TypeError("generator result must be a string or provide a string .text attribute")


def _sanitize_ascii_output(text: str) -> str:
    """Remove common chat/Markdown wrappers from generated ASCII text."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    lines = text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    filtered: list[str] = []
    for line in lines:
        stripped = line.rstrip()
        if _ROLE_LINE_RE.fullmatch(stripped):
            continue
        if _FENCE_LINE_RE.fullmatch(stripped):
            continue
        if _PREAMBLE_LINE_RE.fullmatch(stripped):
            continue
        filtered.append(stripped)

    while filtered and not filtered[0].strip():
        filtered.pop(0)
    while filtered and not filtered[-1].strip():
        filtered.pop()
    return "\n".join(filtered)



def to_web_ui_v1_html(
    value: Diagram | str,
    *,
    title: str = "ASCII art",
    theme: Literal["modern", "github-like"] = "modern",
    charset: Literal["unicode", "ascii"] = "unicode",
) -> str:
    """Render Diagram/text art inside the stable web-ui HTML contract v1.

    Semantic HTML only is emitted; CSS remains consumer-owned. Diagram values
    are rendered with ``render_diagram`` first. Text and title are escaped so
    ASCII characters such as ``<`` and ``&`` remain text rather than markup.\n    ``charset`` is passed to ``render_diagram`` and is currently limited to\n    ``unicode`` or ``ascii`` for Diagram input.
    """
    if theme not in {"modern", "github-like"}:
        raise ValueError("theme must be 'modern' or 'github-like'")
    if isinstance(value, Diagram):
        rendered = render_diagram(value, charset=charset)
    elif isinstance(value, str):
        rendered = value
    else:
        raise TypeError("value must be Diagram or str")
    return "\n".join([
        "<!doctype html>",
        '<html lang="en">',
        '<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>',
        f'<body data-ui-theme="{theme}">',
        '<main class="ui-page">',
        f'<h1 class="ui-title">{html.escape(title)}</h1>',
        '<section class="ui-panel">',
        f'<pre class="ui-output">{html.escape(rendered)}</pre>',
        "</section>",
        "</main>",
        "</body>",
        "</html>",
    ])

def generate_square(size: int, char: str = "*") -> str:
    """Generate a square by repeating a non-empty single-line token.

    size counts token repetitions, not terminal display cells. Unicode and
    multi-code-point tokens are preserved as-is.
    """
    token = _validate_token(char)
    if size <= 0:
        return ""
    row = token * size
    return "\n".join(row for _ in range(size))


def generate_triangle(height: int, char: str = "*") -> str:
    """Generate a left-aligned triangle using token repetition counts."""
    token = _validate_token(char)
    if height <= 0:
        return ""
    return "\n".join(token * i for i in range(1, height + 1))


def generate_diamond(half_height: int, char: str = "*") -> str:
    """Generate a diamond using token repetition counts.

    Padding is ASCII-space based; terminal-cell-perfect alignment for wide
    Unicode tokens is intentionally outside this stdlib-only helper contract.
    """
    token = _validate_token(char)
    if half_height <= 0:
        return ""
    width = 2 * half_height - 1
    upper = [
        " " * ((width - (2 * i - 1)) // 2) + token * (2 * i - 1)
        for i in range(1, half_height + 1)
    ]
    lower = [
        " " * ((width - (2 * i - 1)) // 2) + token * (2 * i - 1)
        for i in range(half_height - 1, 0, -1)
    ]
    return "\n".join(upper + lower)


_BOX_STYLES = {
    "single": {
        "tl": "┌", "tr": "┐", "bl": "└", "br": "┘", "h": "─", "v": "│"
    },
    "double": {
        "tl": "╔", "tr": "╗", "bl": "╚", "br": "╝", "h": "═", "v": "║"
    },
    "rounded": {
        "tl": "╭", "tr": "╮", "bl": "╰", "br": "╯", "h": "─", "v": "│"
    },
    "ascii": {
        "tl": "+", "tr": "+", "bl": "+", "br": "+", "h": "-", "v": "|"
    },
    "heavy": {
        "tl": "┏", "tr": "┓", "bl": "┗", "br": "┛", "h": "━", "v": "┃"
    },
}


def display_width(text: str) -> int:
    """Terminal cell width: East Asian wide/fullwidth count 2, combining marks and zero-width count 0."""
    width = 0
    for ch in text:
        if unicodedata.combining(ch) or unicodedata.category(ch) in ("Mn", "Me", "Cf"):
            continue
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def _box_padding(padding: int | tuple[int, int]) -> tuple[int, int]:
    """Return (horizontal, vertical) padding. A single int is horizontal only."""
    if isinstance(padding, int) and not isinstance(padding, bool):
        if padding < 0:
            raise ValueError("padding must be a non-negative integer")
        return padding, 0
    if (
        isinstance(padding, tuple)
        and len(padding) == 2
        and all(isinstance(part, int) and not isinstance(part, bool) and part >= 0 for part in padding)
    ):
        return padding[0], padding[1]
    raise ValueError("padding must be a non-negative integer or an H,V pair")


def _clusters(text: str) -> list[str]:
    """Split into base characters plus any following combining or format marks."""
    clusters: list[str] = []
    for char in text:
        if clusters and (unicodedata.combining(char) or unicodedata.category(char) in ("Mn", "Me", "Cf")):
            clusters[-1] += char
        else:
            clusters.append(char)
    return clusters


def _wrap_display(text: str, width: int) -> list[str]:
    """Wrap a single line to a maximum display width, preferring breaks at spaces."""
    if width < 1:
        raise ValueError("wrap width must be a positive integer")
    if display_width(text) <= width:
        return [text]
    lines: list[str] = []
    current = ""
    for cluster in _clusters(text):
        trial = current + cluster
        if current and display_width(trial) > width:
            broken = current.rsplit(" ", 1)
            if len(broken) == 2:
                lines.append(broken[0])
                current = broken[1] + cluster
            else:
                lines.append(current)
                current = cluster
        else:
            current = trial
    lines.append(current)
    return lines


def _pad_align(text: str, width: int, align: str) -> str:
    """Pad text to a display width with left, center, or right alignment."""
    gap = width - display_width(text)
    if align == "right":
        return " " * gap + text
    if align == "center":
        left = gap // 2
        return " " * left + text + " " * (gap - left)
    return text + " " * gap


def _box_top(chars: dict[str, str], inner: int, title: str | None) -> str:
    """Build the top border, optionally embedding a single-line title."""
    if title is None:
        return chars["tl"] + chars["h"] * inner + chars["tr"]
    body = chars["h"] + " " + title + " "
    return chars["tl"] + body + chars["h"] * (inner - display_width(body)) + chars["tr"]


def _box_shadow(text: str, *, ascii_style: bool) -> str:
    """Add a one-cell drop shadow to the right and below a box."""
    mark = "#" if ascii_style else "░"
    lines = text.split("\n")
    width = max(display_width(line) for line in lines)
    shadowed = [line + " " * (width - display_width(line)) + mark for line in lines]
    shadowed.append(" " + mark * width)
    return "\n".join(shadowed)


def generate_box(
    text: str,
    *,
    padding: int | tuple[int, int] = 1,
    style: Literal["single", "double", "rounded", "ascii", "heavy"] = "single",
    align: Literal["left", "center", "right"] = "left",
    title: str | None = None,
    width: int | None = None,
    shadow: bool = False,
) -> str:
    """Generate a bordered text box around single or multi-line text.

    ``padding`` is a non-negative integer (horizontal only, for compatibility)
    or an ``(horizontal, vertical)`` pair. ``align`` is CJK-aware via
    ``display_width``. ``title`` is embedded in the top border. ``width`` is a
    minimum outer width in display cells and wraps text; a drop ``shadow`` is
    drawn to the right and below and is not counted in ``width``.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    horizontal, vertical = _box_padding(padding)
    if not isinstance(style, str) or style not in _BOX_STYLES:
        raise ValueError(f"style must be one of {sorted(_BOX_STYLES.keys())!r}")
    if align not in {"left", "center", "right"}:
        raise ValueError("align must be 'left', 'center', or 'right'")
    if title is not None:
        if not isinstance(title, str) or "\n" in title or "\r" in title:
            raise ValueError("title must be a single-line string")
        if not title:
            title = None
    if width is not None and (not isinstance(width, int) or isinstance(width, bool) or width < 1):
        raise ValueError("width must be a positive integer")
    if not isinstance(shadow, bool):
        raise ValueError("shadow must be a bool")

    chars = _BOX_STYLES[style]
    lines = text.replace("\r\n", "\n").replace("\r", "\n").splitlines() or [""]
    if width is not None:
        wrap_at = width - 2 - 2 * horizontal
        if wrap_at < 1:
            wrap_at = 1
        lines = [part for line in lines for part in _wrap_display(line, wrap_at)]

    content = max(display_width(line) for line in lines)
    inner = content + 2 * horizontal
    if title is not None:
        inner = max(inner, display_width(title) + 4)
    if width is not None:
        inner = max(inner, width - 2)
    content = inner - 2 * horizontal
    pad = " " * horizontal
    blank = f"{chars['v']}{pad}{' ' * content}{pad}{chars['v']}"
    body = [
        f"{chars['v']}{pad}{_pad_align(line, content, align)}{pad}{chars['v']}"
        for line in lines
    ]
    mid = [blank] * vertical + body + [blank] * vertical
    box = "\n".join([_box_top(chars, inner, title), *mid, chars["bl"] + chars["h"] * inner + chars["br"]])
    if shadow:
        return _box_shadow(box, ascii_style=style == "ascii")
    return box


_TABLE_JUNCTIONS = {
    "single": {"t": "┬", "m": "┼", "b": "┴", "l": "├", "r": "┤"},
    "double": {"t": "╦", "m": "╬", "b": "╩", "l": "╠", "r": "╣"},
    "rounded": {"t": "┬", "m": "┼", "b": "┴", "l": "├", "r": "┤"},
    "ascii": {"t": "+", "m": "+", "b": "+", "l": "+", "r": "+"},
    "heavy": {"t": "┳", "m": "╋", "b": "┻", "l": "┣", "r": "┫"},
}
_TABLE_ALIGN = {"l": "left", "r": "right", "c": "center", "left": "left", "right": "right", "center": "center"}


def _table_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    if "\n" in text or "\r" in text:
        raise ValueError("table cells must be single-line")
    return text


def _pad_cell(text: str, width: int, align: str) -> str:
    gap = width - display_width(text)
    if align == "right":
        return " " * gap + text
    if align == "center":
        left = gap // 2
        return " " * left + text + " " * (gap - left)
    return text + " " * gap


def render_table(
    rows: Iterable[Iterable[Any]],
    *,
    headers: Iterable[Any] | None = None,
    style: Literal["single", "double", "rounded", "ascii", "heavy"] = "ascii",
    align: str | Iterable[str] | None = None,
    padding: int = 1,
) -> str:
    """Render rows (and optional headers) as a bordered plain-text table.

    Cells are converted with ``str()`` (``None`` becomes empty) and must be
    single-line. Short rows are padded with empty cells. Column widths use
    ``display_width`` so CJK wide characters count as two cells. ``align`` is
    one entry per column (``l``/``r``/``c`` or ``left``/``right``/``center``,
    or a string such as ``"lrc"``); missing columns align left. A table with
    no headers and no rows returns ``""``.
    """
    if not isinstance(style, str) or style not in _BOX_STYLES:
        raise ValueError(f"style must be one of {sorted(_BOX_STYLES.keys())!r}")
    if not isinstance(padding, int) or isinstance(padding, bool) or padding < 0:
        raise ValueError("padding must be a non-negative integer")
    if isinstance(rows, (str, bytes)):
        raise TypeError("rows must be an iterable of row iterables")
    body: list[list[str]] = []
    for row in rows:
        if isinstance(row, (str, bytes)):
            raise TypeError("each row must be an iterable of cells, not a string")
        body.append([_table_cell(cell) for cell in row])
    head: list[str] | None = None
    if headers is not None:
        if isinstance(headers, (str, bytes)):
            raise TypeError("headers must be an iterable of cells, not a string")
        head = [_table_cell(cell) for cell in headers]
    lines_in = ([head] if head is not None else []) + body
    columns = max((len(line) for line in lines_in), default=0)
    if columns == 0:
        return ""
    if align is None:
        aligns: list[str] = []
    else:
        raw = list(align)
        if len(raw) > columns:
            raise ValueError(f"align has {len(raw)} entries for {columns} columns")
        if any(not isinstance(a, str) or a.lower() not in _TABLE_ALIGN for a in raw):
            raise ValueError("align entries must be l/r/c or left/right/center")
        aligns = [_TABLE_ALIGN[a.lower()] for a in raw]
    aligns += ["left"] * (columns - len(aligns))
    for line in lines_in:
        line.extend([""] * (columns - len(line)))
    widths = [max(display_width(line[i]) for line in lines_in) for i in range(columns)]
    box, junction = _BOX_STYLES[style], _TABLE_JUNCTIONS[style]
    pad = " " * padding

    def rule(left: str, mid: str, right: str) -> str:
        return left + mid.join(box["h"] * (w + 2 * padding) for w in widths) + right

    def text_row(line: list[str], header: bool) -> str:
        cells = [_pad_cell(cell, widths[i], "center" if header else aligns[i]) for i, cell in enumerate(line)]
        return box["v"] + box["v"].join(pad + cell + pad for cell in cells) + box["v"]

    out = [rule(box["tl"], junction["t"], box["tr"])]
    if head is not None:
        out.append(text_row(head, True))
        out.append(rule(junction["l"], junction["m"], junction["r"]))
    out.extend(text_row(line, False) for line in body)
    out.append(rule(box["bl"], junction["b"], box["br"]))
    return "\n".join(out)


def get_template(name: str) -> str:
    """Return a built-in ASCII art template by name."""
    return _ASCII_TEMPLATES.get(name.strip().lower(), "")


def list_templates() -> list[str]:
    """Return the sorted built-in ASCII template names."""
    return sorted(_ASCII_TEMPLATES)


# Each glyph is five rows of equal width; "#" marks an ink cell.
_BANNER_FONT: dict[str, tuple[str, ...]] = {
    "A": (" ### ", "#   #", "#####", "#   #", "#   #"),
    "B": ("#### ", "#   #", "#### ", "#   #", "#### "),
    "C": (" ####", "#    ", "#    ", "#    ", " ####"),
    "D": ("#### ", "#   #", "#   #", "#   #", "#### "),
    "E": ("#####", "#    ", "#### ", "#    ", "#####"),
    "F": ("#####", "#    ", "#### ", "#    ", "#    "),
    "G": (" ####", "#    ", "#  ##", "#   #", " ####"),
    "H": ("#   #", "#   #", "#####", "#   #", "#   #"),
    "I": ("###", " # ", " # ", " # ", "###"),
    "J": ("  ###", "   # ", "   # ", "#  # ", " ##  "),
    "K": ("#   #", "#  # ", "###  ", "#  # ", "#   #"),
    "L": ("#    ", "#    ", "#    ", "#    ", "#####"),
    "M": ("#   #", "## ##", "# # #", "#   #", "#   #"),
    "N": ("#   #", "##  #", "# # #", "#  ##", "#   #"),
    "O": (" ### ", "#   #", "#   #", "#   #", " ### "),
    "P": ("#### ", "#   #", "#### ", "#    ", "#    "),
    "Q": (" ### ", "#   #", "# # #", "#  # ", " ## #"),
    "R": ("#### ", "#   #", "#### ", "#  # ", "#   #"),
    "S": (" ####", "#    ", " ### ", "    #", "#### "),
    "T": ("#####", "  #  ", "  #  ", "  #  ", "  #  "),
    "U": ("#   #", "#   #", "#   #", "#   #", " ### "),
    "V": ("#   #", "#   #", "#   #", " # # ", "  #  "),
    "W": ("#   #", "#   #", "# # #", "## ##", "#   #"),
    "X": ("#   #", " # # ", "  #  ", " # # ", "#   #"),
    "Y": ("#   #", " # # ", "  #  ", "  #  ", "  #  "),
    "Z": ("#####", "   # ", "  #  ", " #   ", "#####"),
    "0": (" ### ", "#  ##", "# # #", "##  #", " ### "),
    "1": (" # ", "## ", " # ", " # ", "###"),
    "2": (" ### ", "#   #", "  ## ", " #   ", "#####"),
    "3": ("#### ", "    #", " ### ", "    #", "#### "),
    "4": ("#   #", "#   #", "#####", "    #", "    #"),
    "5": ("#####", "#    ", "#### ", "    #", "#### "),
    "6": (" ### ", "#    ", "#### ", "#   #", " ### "),
    "7": ("#####", "    #", "   # ", "  #  ", "  #  "),
    "8": (" ### ", "#   #", " ### ", "#   #", " ### "),
    "9": (" ### ", "#   #", " ####", "    #", " ### "),
    " ": ("   ", "   ", "   ", "   ", "   "),
    "!": ("#", "#", "#", " ", "#"),
    "?": (" ### ", "#   #", "  ## ", "     ", "  #  "),
    ".": (" ", " ", " ", " ", "#"),
    ",": ("  ", "  ", "  ", " #", "# "),
    ":": (" ", "#", " ", "#", " "),
    "'": ("#", "#", " ", " ", " "),
    "-": ("    ", "    ", "####", "    ", "    "),
    "_": ("    ", "    ", "    ", "    ", "####"),
    "+": ("   ", " # ", "###", " # ", "   "),
    "=": ("    ", "####", "    ", "####", "    "),
    "/": ("    #", "   # ", "  #  ", " #   ", "#    "),
    "(": (" #", "# ", "# ", "# ", " #"),
    ")": ("# ", " #", " #", " #", "# "),
}
_BANNER_ROWS = 5


def banner_charset() -> str:
    """Return every character the built-in banner font draws, in a stable order.

    ASCII lowercase ``a``-``z`` are also accepted by ``banner`` and drawn with
    the uppercase glyphs.
    """
    return "".join(_BANNER_FONT)


def banner(text: str, *, char: str = "#", spacing: int = 1, fallback: str | None = None) -> str:
    """Draw single-line ``text`` with the built-in 5-row big-letter font.

    ASCII lowercase letters use the uppercase glyphs. Any other character not
    in ``banner_charset()`` raises ``ValueError`` unless ``fallback`` names a
    supported character to draw instead. ``char`` is the ink token; blank
    cells are padded to its ``display_width`` so wide tokens stay aligned.
    Trailing spaces are stripped from every row; empty text returns ``""``.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if "\n" in text or "\r" in text:
        raise ValueError("banner text must be a single line")
    token = _validate_token(char)
    if not isinstance(spacing, int) or isinstance(spacing, bool) or spacing < 0:
        raise ValueError("spacing must be a non-negative integer")
    if fallback is not None:
        if not isinstance(fallback, str) or len(fallback) != 1:
            raise ValueError("fallback must be one supported banner character")
        fallback = fallback.upper() if "a" <= fallback <= "z" else fallback
        if fallback not in _BANNER_FONT:
            raise ValueError(f"fallback {fallback!r} is not in the banner font")
    if not text:
        return ""
    glyphs: list[tuple[str, ...]] = []
    missing: list[str] = []
    for ch in text:
        key = ch.upper() if "a" <= ch <= "z" else ch
        if key not in _BANNER_FONT:
            if fallback is None:
                if ch not in missing:
                    missing.append(ch)
                continue
            key = fallback
        glyphs.append(_BANNER_FONT[key])
    if missing:
        listed = ", ".join(repr(ch) for ch in missing)
        raise ValueError(f"unsupported banner characters: {listed} (see banner_charset())")
    blank = " " * display_width(token)
    gap = blank * spacing
    rows = []
    for row in range(_BANNER_ROWS):
        cells = gap.join(glyph[row] for glyph in glyphs)
        rows.append("".join(token if cell == "#" else blank for cell in cells).rstrip())
    return "\n".join(rows)


def render_prompt_ascii(
    prompt: str,
    generator: Callable[[str], Any] | _SupportsGenerateLight,
) -> str:
    """Generate ASCII art using either a callable or generate_light object.

    A callable may return a string directly or an object with a string text
    attribute. This keeps the module independent from any specific LLM SDK.
    """
    user_prompt = prompt.strip()
    final_prompt = (
        "Generate compact ASCII art that represents the user's request.\n\n"
        f"USER_REQUEST:\n{user_prompt}\n\n"
        f"CONSTRAINTS:\n"
        "- Keep width under 60 characters.\n"
        f"- Return ASCII art only.\n"
        f"- No explanations.\n"
    )

    return _sanitize_ascii_output(_generated_text(generator, final_prompt))


# --- command-line entry point -------------------------------------------------

_CLI_READERS: dict[str, Callable[[str], Diagram]] = {
    "json": from_json,
    "mermaid": from_mermaid,
    "dot": from_dot,
    "outline": from_markdown_outline,
}


# Card-flow implementation adapted from web-ui (MIT, Copyright (c) 2026 myon).
# Source and behavioral provenance: docs/card-flows.md.
FLOW_MAX_INPUT = 256 * 1024
FLOW_THEMES = ("modern", "github-like")

def _has_control(text):
    """C0 controls, DEL or unpaired surrogates: rejected in card labels and asset paths."""
    return any(ord(char) < 32 or ord(char) == 127 or 0xD800 <= ord(char) <= 0xDFFF for char in text)

def _flow_label(value, required=True, length=240):
    if not isinstance(value, str) or len(value) > length:
        raise ValueError("labels must be bounded strings")
    if _has_control(value):
        raise ValueError("control characters or unpaired surrogates in label")
    if required and not value.strip():
        raise ValueError("empty label")
    return value

def _flow_cards(value, kind):
    if not isinstance(value, list) or not 1 <= len(value) <= 8:
        raise ValueError(f"{kind} must contain 1..8 cards")
    result = []
    for card in value:
        if not isinstance(card, dict) or "title" not in card or set(card) - {"title", "note"}:
            raise ValueError("cards require title and optional note only")
        result.append({"title": _flow_label(card["title"], length=120),
                       "note": _flow_label(card.get("note", ""), required=False)})
    return result

def validate_flow(spec):
    """Return a detached canonical source/step card flow; reject unknown fields."""
    if not isinstance(spec, dict) or set(spec) - {"title", "sources_label", "sources", "steps"}:
        raise ValueError("expected flow object")
    return {"title": _flow_label(spec.get("title", ""), length=120),
            "sources_label": _flow_label(spec.get("sources_label", "Sources"), length=120),
            "sources": _flow_cards(spec.get("sources"), "sources"),
            "steps": _flow_cards(spec.get("steps"), "steps")}

def _card_html(card):
    title = '<strong class="ui-flow-card-title">' + html.escape(card["title"]) + '</strong>'
    note = ('<span class="ui-flow-card-note">' + html.escape(card["note"]) + '</span>') if card["note"] else ""
    return '<div class="ui-flow-card">' + title + note + '</div>'

def flow_html(spec):
    """Render an escaped static figure fragment without styles or scripts."""
    data = validate_flow(spec)
    sources = "".join('<li class="ui-flow-source">' + _card_html(c) + '</li>' for c in data["sources"])
    steps = "".join('<li class="ui-flow-step">' + _card_html(c) + '</li>' for c in data["steps"])
    return ('<figure class="ui-flow" aria-label="' + html.escape(data["title"], quote=True) + '">'
            '<figcaption class="ui-flow-caption">' + html.escape(data["title"]) + '</figcaption>'
            '<ul class="ui-flow-sources" aria-label="' + html.escape(data["sources_label"], quote=True) + '">'
            + sources + '</ul><div class="ui-flow-arrow" aria-hidden="true">↓</div>'
            '<ol class="ui-flow-steps">' + steps + '</ol></figure>')

def _mermaid_label(value):
    entities = {'"': "#quot;", "<": "#lt;", ">": "#gt;", "&": "#amp;",
                "[": "#91;", "]": "#93;", "\\": "#92;", "\n": "#10;"}
    return "".join(entities.get(char, char) for char in value)

def _card_mermaid(card):
    label = _mermaid_label(card["title"])
    return label + "<br/>" + _mermaid_label(card["note"]) if card["note"] else label

def flow_mermaid(spec):
    """Render fenced Mermaid with generated IDs and entity-escaped labels."""
    data = validate_flow(spec)
    lines = ["```mermaid", "flowchart TB",
             '    subgraph input["' + _mermaid_label(data["sources_label"]) + '"]',
             "        direction LR"]
    lines += [f'        S{i}["{_card_mermaid(card)}"]' for i, card in enumerate(data["sources"])]
    lines.append("    end")
    lines += [f'    T{i}["{_card_mermaid(card)}"]' for i, card in enumerate(data["steps"])]
    for i in range(len(data["sources"])):
        lines.append(f"    S{i} --> T0")
    for i in range(1, len(data["steps"])):
        lines.append(f"    T{i-1} --> T{i}")
    return "\n".join(lines + ["```", ""])

def flow_document(spec, *, asset_base=".", theme="github-like", embed_css=True):
    """Build standalone HTML in memory; linked mode expects exported flow.css."""
    if theme not in FLOW_THEMES:
        raise ValueError("unknown theme")
    if not isinstance(asset_base, str) or not asset_base or any(
        c in asset_base for c in ('<', '>', '"', "'", "\\", "?", "#", "\n", "\r")
    ) or ":" in asset_base or asset_base.startswith("//") or _has_control(asset_base):
        raise ValueError("asset_base must be a local path")
    if embed_css:
        css = "<style>" + flow_css(theme=theme) + "</style>"
    else:
        prefix = asset_base.rstrip("/")
        css = '<link rel="stylesheet" href="' + html.escape(prefix + "/flow.css", quote=True) + '">'
    data = validate_flow(spec)
    return ('<!doctype html>\n<html lang="ja"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>' + html.escape(data["title"]) + '</title>' + css + '</head>'
            '<body data-ui-theme="' + theme + '"><main class="ui-page">'
            + flow_html(data) + '</main></body></html>\n')

# Canonical stylesheet stays in this file: vendoring requires no runtime assets.
_FLOW_CSS = '*{box-sizing:border-box}body{margin:0;font:16px/1.6 Meiryo,メイリオ,sans-serif;background:var(--ui-bg);color:var(--ui-fg)}.ui-page{max-width:960px;margin:auto;padding:1.25rem}\n/* Optional flow diagram component: no JS and no changes to contract/v1. */\n@layer components {\n.ui-flow{padding:clamp(.8rem,3vw,1.8rem);margin:1.25rem 0;border:1px solid var(--ui-border);border-radius:1.5rem;background:var(--ui-bg);color:var(--ui-fg)}\n.ui-flow-caption{margin:0 0 1.25rem;font-size:clamp(1rem,2.25vw,1.25rem);font-weight:700;text-align:center}\n.ui-flow-sources{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,10.5rem),1fr));gap:.85rem;list-style:none;margin:0;padding:0}\n.ui-flow-steps{list-style:none;padding:0;margin:0}\n.ui-flow-source,.ui-flow-step{min-width:0}\n.ui-flow-card{border:1px solid var(--ui-border);border-radius:1.2rem;background:var(--ui-panel);padding:clamp(1rem,3vw,1.7rem);text-align:center;overflow-wrap:anywhere}\n.ui-flow-card-title{display:block;font-weight:750;font-size:clamp(1.15rem,2.5vw,1.9rem);line-height:1.4}\n.ui-flow-card-note{display:block;margin-top:.5rem;color:var(--ui-muted);line-height:1.5}\n.ui-flow-arrow,.ui-flow-step+.ui-flow-step::before{display:block;content:"↓";margin:.85rem auto;width:fit-content;color:var(--ui-muted);font-size:1.8rem;line-height:1.4;font-weight:700;text-align:center}\n@media(max-width:520px){.ui-flow-sources{grid-template-columns:1fr}.ui-flow-card{padding:.85rem}}\n@media print{.ui-flow,.ui-flow-card{break-inside:avoid}}\n}\n'
_FLOW_PALETTES = {
    "github-like": "--ui-bg:#fff;--ui-fg:#1f2328;--ui-border:#d0d7de;--ui-panel:#f6f8fa;--ui-muted:#59636e",
    "modern": "--ui-bg:#0d1117;--ui-fg:#d1f7c4;--ui-border:#58a6ff;--ui-panel:#101820;--ui-muted:#8b949e;color-scheme:dark",
}


def flow_css(*, theme="github-like"):
    """Build a self-contained card stylesheet in memory (no I/O or JS)."""
    if theme not in FLOW_THEMES:
        raise ValueError("unknown theme")
    return ":root{" + _FLOW_PALETTES[theme] + "}\n" + _FLOW_CSS


FLOW_MAX_PATCH = 64 * 1024
FLOW_MAX_OPS = 64
_FLOW_FIELDS = frozenset({"title", "note"})


def patch_flow(spec, operations):
    """Apply a batch atomically; invalid operations never mutate caller state."""
    result = validate_flow(spec)  # detached, JSON-serializable copy
    if not isinstance(operations, list) or len(operations) > FLOW_MAX_OPS:
        raise ValueError("patch must be an array with at most 64 operations")
    for operation in operations:
        if not isinstance(operation, dict) or set(operation) != {"path", "value"}:
            raise ValueError("patch entries require path and value")
        path = operation["path"]
        if not isinstance(path, str):
            raise ValueError("patch path must be a string")
        if path in ("/title", "/sources_label"):
            result[path[1:]] = operation["value"]
            continue
        parts = path.split("/")
        if len(parts) != 4 or parts[0] != "" or parts[1] not in ("sources", "steps") or parts[3] not in _FLOW_FIELDS:
            raise ValueError("unsupported patch path")
        index = parts[2]
        if not index.isascii() or not index.isdecimal() or str(int(index)) != index:
            raise ValueError("patch index must be canonical decimal")
        collection = result[parts[1]]
        if int(index) >= len(collection):
            raise ValueError("patch index out of range")
        collection[int(index)][parts[3]] = operation["value"]
    return validate_flow(result)


def _apply_flow_patch_document(document):
    if not isinstance(document, dict) or set(document) != {"spec", "patch"}:
        raise ValueError("expected spec and patch")
    return patch_flow(document["spec"], document["patch"])



def _cli_flow(args):
    budget = FLOW_MAX_INPUT + (FLOW_MAX_PATCH if args.command == "flow-patch" else 0)
    raw = sys.stdin.buffer.read(budget + 1)
    if len(raw) > budget:
        raise ValueError("flow document exceeds byte budget")
    try:
        document = json.loads(raw.decode("utf-8"))
    except RecursionError as exc:
        raise ValueError("flow JSON nesting is too deep") from exc
    if args.command == "flow-patch":
        return json.dumps(_apply_flow_patch_document(document), ensure_ascii=False,
                          indent=2 if args.pretty else None)
    if args.format == "mermaid":
        return flow_mermaid(document)
    if args.format == "fragment":
        return flow_html(document)
    return flow_document(document, theme=args.theme, asset_base=args.asset_base,
                         embed_css=not args.no_embed_css)


def _cli_read(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _cli_convert(args: argparse.Namespace) -> str:
    if args.layout is not None and args.target_format != "render":
        raise ValueError("--layout requires --to render")
    value = _CLI_READERS[args.source_format](_cli_read(args.input))
    if args.target_format == "render":
        return render_diagram(value, charset=args.charset, layout=args.layout or "adjacency")
    if args.target_format == "inventory":
        return json.dumps(inventory(value), ensure_ascii=False, indent=2)
    writers: dict[str, Callable[[Diagram], str]] = {
        "json": to_json,
        "mermaid": to_mermaid,
        "dot": to_dot,
        "outline": to_markdown_outline,
    }
    return writers[args.target_format](value)


def _cli_padding(value: str) -> int | tuple[int, int]:
    """Parse --padding N or H,V. Negative values are left for generate_box."""
    parts = value.split(",")
    if len(parts) == 1:
        try:
            return int(parts[0], 10)
        except ValueError as exc:
            raise argparse.ArgumentTypeError("padding must be N or H,V") from exc
    if len(parts) == 2:
        try:
            return (int(parts[0], 10), int(parts[1], 10))
        except ValueError as exc:
            raise argparse.ArgumentTypeError("padding must be N or H,V") from exc
    raise argparse.ArgumentTypeError("padding must be N or H,V")


def _cli_table(args: argparse.Namespace) -> str:
    reader = csv.reader(_cli_read(args.input).splitlines(), delimiter="\t" if args.table_format == "tsv" else ",")
    rows = [row for row in reader if row]
    if not rows:
        raise ValueError("table input has no rows")
    headers = None if args.no_header else rows.pop(0)
    return render_table(rows, headers=headers, style=args.style, align=args.align)



def _cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ascii_artist.py",
        description=(
            "Generate text art and convert text diagrams (stdlib only).\n"
            "exit 0: output written to stdout.\n"
            "exit 1: input file could not be read.\n"
            "exit 2: usage error or invalid input (one stderr error line)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")
    for name, label in (("square", "SIZE"), ("triangle", "HEIGHT"), ("diamond", "HALF_HEIGHT")):
        shape = commands.add_parser(name, help=f"generate a {name}", allow_abbrev=False)
        shape.add_argument("size", type=int, metavar=label, help="token repetition count")
        shape.add_argument("--char", default="*", help="non-empty single-line token (default: *)")
    box = commands.add_parser("box", help="draw a box around text", allow_abbrev=False)
    box.add_argument("input", nargs="?", default="-", metavar="FILE",
                     help="UTF-8 text file; - or omitted reads stdin")
    box.add_argument("--padding", type=_cli_padding, default=1,
                     help="N (horizontal, default: 1) or H,V (horizontal, vertical)")
    box.add_argument("--style", choices=sorted(_BOX_STYLES), default="single",
                     help="border style (default: single)")
    box.add_argument("--align", choices=("left", "center", "right"), default="left",
                     help="text alignment (default: left)")
    box.add_argument("--title", default=None, help="heading embedded in the top border")
    box.add_argument("--width", type=int, default=None,
                     help="minimum outer width in display cells; wraps text")
    box.add_argument("--shadow", action="store_true", help="draw a one-cell drop shadow")
    for name, help_text in (("flow", "render a vertical flow"), ("tree", "render ITEMS as children of ROOT"),
                            ("branch", "render a one-to-many, optionally many-to-one, branch")):
        sub = commands.add_parser(name, help=help_text, allow_abbrev=False)
        if name in ("tree", "branch"):
            sub.add_argument("root", metavar="ROOT", help="root label")
        nargs = "*" if name == "branch" else "+"
        sub.add_argument("items", nargs=nargs, metavar="ITEM", help="single-line label")
        if name == "branch":
            sub.add_argument("--target", default=None, metavar="TARGET",
                             help="optional convergence label")
        sub.add_argument("--charset", choices=("unicode", "ascii"), default="unicode",help="box-drawing characters or plain ASCII (default: %(default)s)")
    big = commands.add_parser("banner", help="draw TEXT in the built-in big-letter font", allow_abbrev=False)
    big.add_argument("text", nargs="+", metavar="TEXT", help="words joined with one space; a-z use A-Z glyphs")
    big.add_argument("--char", default="#", help="non-empty single-line ink token (default: #)")
    big.add_argument("--spacing", type=int, default=1, help="blank cells between letters (default: 1)")
    big.add_argument("--fallback", default=None, help="supported character drawn for unsupported ones (default: error)")
    table = commands.add_parser("table", help="render CSV/TSV rows as a text table", allow_abbrev=False)
    table.add_argument("input", nargs="?", default="-", metavar="FILE",
                       help="UTF-8 CSV/TSV file; - or omitted reads stdin")
    table.add_argument("--format", dest="table_format", choices=("csv", "tsv"), default="csv",
                       help="input delimiter (default: %(default)s)")
    table.add_argument("--no-header", action="store_true", help="treat the first row as data, not headers")
    table.add_argument("--style", choices=sorted(_BOX_STYLES), default="ascii",
                       help="border style (default: %(default)s)")
    table.add_argument("--align", default=None, metavar="SPEC",
                       help="one of l/r/c per column, e.g. lrc (default: all left)")
    template = commands.add_parser("template", help="print a built-in template", allow_abbrev=False)
    template.add_argument("name", metavar="NAME", help="template name (see: templates)")
    commands.add_parser("templates", help="list built-in template names", allow_abbrev=False)
    convert = commands.add_parser("convert", help="convert a text diagram", allow_abbrev=False)
    convert.add_argument("input", nargs="?", default="-", metavar="FILE",
                         help="UTF-8 diagram file; - or omitted reads stdin")
    convert.add_argument("--from", dest="source_format", choices=sorted(_CLI_READERS), required=True,help="input diagram format")
    convert.add_argument("--to", dest="target_format", required=True,
                         choices=sorted([*_CLI_READERS, "render", "inventory"]),help="output format; render draws it, inventory prints structural statistics")
    convert.add_argument("--charset", choices=("unicode", "ascii"), default="unicode",
                         help="charset for --to render (default: unicode)")
    convert.add_argument("--layout", choices=("adjacency", "layered"),
                         help="layout for --to render (default: adjacency)")
    cards = commands.add_parser("flow-cards", help="render bounded JSON cards from stdin", allow_abbrev=False)
    cards.add_argument("--format", choices=("html", "fragment", "mermaid"), default="html",help="full page, HTML fragment, or Mermaid (default: %(default)s)")
    cards.add_argument("--theme", choices=FLOW_THEMES, default="github-like",help="color theme (default: %(default)s)")
    cards.add_argument("--asset-base", default=".",help="local path prefix for linked assets (default: %(default)s)")
    cards.add_argument("--no-embed-css", action="store_true",help="link the stylesheet instead of embedding it")
    patch = commands.add_parser("flow-patch", help="atomically patch JSON cards from stdin", allow_abbrev=False)
    patch.add_argument("--pretty", action="store_true",help="indent the patched JSON")
    for each in (parser, *commands.choices.values()):
        each.suggest_on_error = True  # 🤔 argparse 3.14+: "maybe you meant" for commands and choices; older Pythons ignore it
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    """Run the command-line interface; returns the process exit code."""
    parser = _cli_parser()
    args = parser.parse_args(None if argv is None else list(argv))
    try:
        if args.command is None:
            parser.error("command required")
        if args.command in ("square", "triangle", "diamond"):
            generate = {"square": generate_square, "triangle": generate_triangle,
                        "diamond": generate_diamond}[args.command]
            text = generate(args.size, args.char)
        elif args.command in ("flow-cards", "flow-patch"):
            text = _cli_flow(args)
        elif args.command == "box":
            text = generate_box(
                _cli_read(args.input),
                padding=args.padding,
                style=args.style,
                align=args.align,
                title=args.title,
                width=args.width,
                shadow=args.shadow,
            )
        elif args.command == "flow":
            text = flow(args.items, charset=args.charset)
        elif args.command == "branch":
            text = branch(args.root, args.items, args.target, charset=args.charset)
        elif args.command == "tree":
            if any(not item or "\n" in item or "\r" in item for item in args.items):
                raise ValueError("tree items must be non-empty single-line strings")
            text = tree(args.root, {item: {} for item in args.items}, charset=args.charset)
        elif args.command == "banner":
            text = banner(" ".join(args.text), char=args.char, spacing=args.spacing, fallback=args.fallback)
        elif args.command == "table":
            text = _cli_table(args)
        elif args.command == "template":
            text = get_template(args.name)
            if not text:
                parser.error(f"unknown template: {args.name!r}")
        elif args.command == "templates":
            text = "\n".join(list_templates())
        else:
            text = _cli_convert(args)
    except OSError as exc:
        print(f"ascii_artist.py: error: {exc.strerror or exc}: {exc.filename}", file=sys.stderr)
        return 1
    except (ValueError, TypeError, KeyError) as exc:
        print(f"ascii_artist.py: error: {exc}", file=sys.stderr)
        return 2
    output = text if not text or text.endswith("\n") else text + "\n"
    if args.command in ("flow-cards", "flow-patch") and hasattr(sys.stdout, "buffer"):
        # Card-flow JSON/HTML is UTF-8 even when redirected Windows stdout is not.
        sys.stdout.buffer.write(output.encode("utf-8"))
    else:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
