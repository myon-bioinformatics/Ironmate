# ascii_artist.py
# __all__: 32

__all__ = [
    "generate_square",
    "generate_triangle",
    "generate_diamond",
    "get_template",
    "list_templates",
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
]

import html
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Literal, Mapping, Protocol

SUPPORTED = {
    "generation": [
        "square / triangle / diamond text-art generation",
        "non-empty single-line string tokens, including Unicode",
        "built-in text-art templates",
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

    ready = [node_id for node_id in node_ids if indegree[node_id] == 0]
    visited = 0
    while ready:
        current = ready.pop(0)
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

    remaining = set(node_ids)
    layers: list[list[str]] = []
    while remaining:
        layer = [node_id for node_id in node_ids if node_id in remaining and indegree[node_id] == 0]
        if not layer:
            raise ValueError("diagram must be acyclic")
        layers.append(layer)
        for source in layer:
            remaining.remove(source)
            for target in outgoing[source]:
                indegree[target] -= 1
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


def render_diagram(value: Diagram, *, charset: str = "unicode") -> str:
    """Render any DAG as an exact adjacency-oriented text representation.

    Specialized convenience renderers such as flow() and branch() may choose a
    prettier topology-specific layout. This generic renderer prioritizes edge
    correctness over pretending to be a full graph-layout engine.
    """

    chars = _charset(charset)
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
}

_DEFAULT_ASCII_PROMPT = "Generate compact ASCII art that represents the user's request."
_DEFAULT_MAX_WIDTH = 60
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


def get_template(name: str) -> str:
    """Return a built-in ASCII art template by name."""
    return _ASCII_TEMPLATES.get(name.strip().lower(), "")


def list_templates() -> list[str]:
    """Return the sorted built-in ASCII template names."""
    return sorted(_ASCII_TEMPLATES)


def render_prompt_ascii(
    prompt: str,
    generator: Callable[[str], Any] | _SupportsGenerateLight,
) -> str:
    """Generate ASCII art using either a callable or generate_light object.

    A callable may return a string directly or an object with a string text
    attribute. This keeps the module independent from any specific LLM SDK.
    """
    base_prompt = _DEFAULT_ASCII_PROMPT
    max_width = _DEFAULT_MAX_WIDTH

    user_prompt = prompt.strip()
    final_prompt = (
        f"{base_prompt}\n\n"
        f"USER_REQUEST:\n{user_prompt}\n\n"
        f"CONSTRAINTS:\n"
        f"- Keep width under {max_width} characters.\n"
        f"- Return ASCII art only.\n"
        f"- No explanations.\n"
    )

    return _sanitize_ascii_output(_generated_text(generator, final_prompt))
