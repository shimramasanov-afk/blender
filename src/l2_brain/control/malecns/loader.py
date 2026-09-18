"""Compact visuo-motor extract. Not a downloaded FlyEM / MaleCNS dump."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

Mode = Literal["bio", "shuffled", "random_sparse"]

EXTRACT_ID = "synthetic_visuomotor_extract_v0"
EXTRACT_VERSION = "0.1.0"
TRANSMITTER_SIGN = {"ach": 1.0, "glu": 1.0, "gaba": -1.0}
W_SCALE = 1.35


@dataclass(frozen=True, slots=True)
class NodeRec:
    index: int
    role: str
    transmitter: str


@dataclass(frozen=True, slots=True)
class EdgeRec:
    pre: int
    post: int
    contacts: int
    transmitter: str


@dataclass(frozen=True, slots=True)
class Subgraph:
    nodes: tuple[NodeRec, ...]
    edges: tuple[EdgeRec, ...]
    mode: Mode
    extract_id: str = EXTRACT_ID
    version: str = EXTRACT_VERSION
    source: str = "synthetic_extract"
    biological_claim: bool = False

    @property
    def n(self) -> int:
        return len(self.nodes)

    @property
    def e(self) -> int:
        return len(self.edges)

    @property
    def density(self) -> float:
        denom = self.n * (self.n - 1)
        return self.e / denom if denom else 0.0

    def metadata(self) -> dict[str, Any]:
        return {
            "extract_id": self.extract_id,
            "version": self.version,
            "source": self.source,
            "biological_claim": self.biological_claim,
            "mode": self.mode,
            "n": self.n,
            "e": self.e,
            "density": self.density,
            "transmitters": sorted({node.transmitter for node in self.nodes}),
            "full_connectome_loaded": False,
        }


def transmitter_sign(name: str) -> float:
    if name not in TRANSMITTER_SIGN:
        raise ValueError(f"unknown transmitter {name!r}")
    return TRANSMITTER_SIGN[name]


def build_extract() -> tuple[tuple[NodeRec, ...], tuple[EdgeRec, ...]]:
    """Deterministic visuo-motor motif: visual LNs, CX ring, descending neurons."""
    roles: list[tuple[str, str, int]] = [
        ("vis_left", "ach", 16),
        ("vis_right", "ach", 16),
        ("vis_conf", "ach", 16),
        ("vis_risk", "gaba", 8),
        ("cx", "ach", 48),
        ("cx_inh", "gaba", 16),
        ("dn_left", "ach", 16),
        ("dn_right", "ach", 16),
        ("dn_fwd", "ach", 24),
        ("i_anti_left", "gaba", 16),
        ("i_anti_right", "gaba", 16),
    ]
    nodes: list[NodeRec] = []
    groups: dict[str, list[int]] = {}
    index = 0
    for role, tx, count in roles:
        groups[role] = []
        for _ in range(count):
            nodes.append(NodeRec(index, role, tx))
            groups[role].append(index)
            index += 1
    edges: list[EdgeRec] = []

    def link(pres: list[int], posts: list[int], tx: str, contacts: int, stride: int) -> None:
        if not pres or not posts:
            return
        for i, pre in enumerate(pres):
            for k in range(stride):
                post = posts[(i * stride + k) % len(posts)]
                if pre == post:
                    continue
                edges.append(EdgeRec(pre, post, contacts, tx))

    link(groups["vis_left"], groups["dn_left"], "ach", 6, 4)
    link(groups["vis_left"], groups["i_anti_right"], "ach", 4, 2)
    link(groups["vis_right"], groups["dn_right"], "ach", 6, 4)
    link(groups["vis_right"], groups["i_anti_left"], "ach", 4, 2)
    link(groups["vis_conf"], groups["dn_fwd"], "ach", 5, 3)
    link(groups["vis_conf"], groups["cx"], "ach", 2, 2)
    link(groups["vis_risk"], groups["dn_fwd"], "gaba", 4, 3)
    link(groups["i_anti_right"], groups["dn_right"], "gaba", 5, 3)
    link(groups["i_anti_left"], groups["dn_left"], "gaba", 5, 3)
    cx = groups["cx"]
    for i, pre in enumerate(cx):
        edges.append(EdgeRec(pre, cx[(i + 1) % len(cx)], 3, "ach"))
        edges.append(EdgeRec(pre, cx[(i + 2) % len(cx)], 2, "ach"))
        edges.append(EdgeRec(pre, groups["cx_inh"][i % len(groups["cx_inh"])], 3, "ach"))
    link(groups["cx_inh"], groups["cx"], "gaba", 2, 2)
    link(groups["cx"], groups["dn_fwd"], "ach", 2, 1)
    return tuple(nodes), tuple(edges)


def load_subgraph(mode: Mode = "bio", *, seed: int = 0) -> Subgraph:
    nodes, edges = build_extract()
    if mode == "bio":
        return Subgraph(nodes, edges, mode="bio")
    if mode == "shuffled":
        return Subgraph(nodes, _shuffle_edges(edges, seed), mode="shuffled")
    if mode == "random_sparse":
        return Subgraph(nodes, _erdos_renyi(nodes, edges, seed), mode="random_sparse")
    raise ValueError(f"unknown mode {mode}")


def _shuffle_edges(edges: tuple[EdgeRec, ...], seed: int) -> tuple[EdgeRec, ...]:
    rng = np.random.default_rng(seed + 11)
    posts = [edge.post for edge in edges]
    rng.shuffle(posts)
    n = 1 + max(edge.pre for edge in edges)
    out: list[EdgeRec] = []
    for edge, post in zip(edges, posts, strict=True):
        if post == edge.pre:
            post = int((post + 1) % n)
        out.append(EdgeRec(edge.pre, post, edge.contacts, edge.transmitter))
    return tuple(out)


def _erdos_renyi(nodes: tuple[NodeRec, ...], edges: tuple[EdgeRec, ...], seed: int) -> tuple[EdgeRec, ...]:
    rng = np.random.default_rng(seed + 23)
    n = len(nodes)
    p = len(edges) / max(n * (n - 1), 1)
    out: list[EdgeRec] = []
    for i, node in enumerate(nodes):
        for j in range(n):
            if i == j or rng.random() >= p:
                continue
            out.append(EdgeRec(i, j, 2, node.transmitter))
    return tuple(out)


def weight_matrix(graph: Subgraph) -> np.ndarray:
    weights = np.zeros((graph.n, graph.n), dtype=np.float64)
    if not graph.edges:
        return weights
    peak = max(edge.contacts for edge in graph.edges)
    for edge in graph.edges:
        sign = transmitter_sign(edge.transmitter)
        weights[edge.post, edge.pre] += sign * W_SCALE * (np.log1p(edge.contacts) / np.log1p(peak))
    np.fill_diagonal(weights, 0.0)
    return weights


def input_matrix(graph: Subgraph, n_input: int = 6, scale: float = 1.80) -> np.ndarray:
    w = np.zeros((graph.n, n_input), dtype=np.float64)
    for node in graph.nodes:
        if node.role == "vis_left":
            w[node.index, 0] = scale
        elif node.role == "vis_right":
            w[node.index, 1] = scale
        elif node.role == "vis_conf":
            w[node.index, 2] = scale
            w[node.index, 5] = 0.65 * scale
            w[node.index, 4] = 0.20 * scale
        elif node.role == "vis_risk":
            w[node.index, 3] = 0.90 * scale
    return w


def role_indices(graph: Subgraph, role: str) -> np.ndarray:
    return np.array([node.index for node in graph.nodes if node.role == role], dtype=np.int32)


def has_input_to_output_path(graph: Subgraph) -> bool:
    starts = [node.index for node in graph.nodes if node.role.startswith("vis_")]
    goals = {node.index for node in graph.nodes if node.role.startswith("dn_")}
    adj: list[list[int]] = [[] for _ in range(graph.n)]
    for edge in graph.edges:
        adj[edge.pre].append(edge.post)
    seen = set(starts)
    stack = list(starts)
    while stack:
        cur = stack.pop()
        if cur in goals:
            return True
        for nxt in adj[cur]:
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return False


def out_degrees(graph: Subgraph) -> np.ndarray:
    deg = np.zeros(graph.n, dtype=np.int32)
    for edge in graph.edges:
        deg[edge.pre] += 1
    return deg


def to_public_dict(graph: Subgraph) -> dict[str, Any]:
    return graph.metadata() | {"node_roles": sorted({node.role for node in graph.nodes})}
