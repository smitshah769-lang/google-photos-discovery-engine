from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from pipeline.paths import DEFAULT_TAXONOMY, taxonomy_path_for_version


@dataclass(frozen=True)
class TaxonomyNode:
    id: str
    name: str
    definition: str
    parent_id: str | None
    examples: tuple[str, ...]


@dataclass(frozen=True)
class Taxonomy:
    version: str
    nodes: tuple[TaxonomyNode, ...]

    def get(self, node_id: str) -> TaxonomyNode:
        for node in self.nodes:
            if node.id == node_id:
                return node
        raise KeyError(f"Unknown taxonomy node id: {node_id}")

    def ids(self) -> frozenset[str]:
        return frozenset(n.id for n in self.nodes)


def load_taxonomy(path: Path | None = None, *, version: str | None = None) -> Taxonomy:
    resolved = path or (taxonomy_path_for_version(version) if version else DEFAULT_TAXONOMY)
    raw = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("taxonomy file must be a mapping")
    version = str(raw.get("version", ""))
    nodes_raw = raw.get("nodes") or []
    nodes: list[TaxonomyNode] = []
    for item in nodes_raw:
        if not isinstance(item, dict):
            continue
        node_id = str(item["id"])
        examples = item.get("examples") or []
        nodes.append(
            TaxonomyNode(
                id=node_id,
                name=str(item["name"]),
                definition=str(item["definition"]),
                parent_id=item.get("parent_id"),
                examples=tuple(str(e) for e in examples),
            )
        )
    _validate_taxonomy(version, nodes)
    return Taxonomy(version=version, nodes=tuple(nodes))


def _validate_taxonomy(version: str, nodes: list[TaxonomyNode]) -> None:
    if not version:
        raise ValueError("taxonomy version is required")
    ids = {n.id for n in nodes}
    if len(ids) != len(nodes):
        raise ValueError("duplicate taxonomy node ids")
    for node in nodes:
        if node.parent_id is not None and node.parent_id not in ids:
            raise ValueError(f"unknown parent_id {node.parent_id} for node {node.id}")


def taxonomy_nodes_for_db(taxonomy: Taxonomy) -> list[dict[str, Any]]:
    return [
        {
            "id": n.id,
            "taxonomy_version": taxonomy.version,
            "name": n.name,
            "definition": n.definition,
            "parent_id": n.parent_id,
            "examples_json": json.dumps(list(n.examples)),
        }
        for n in taxonomy.nodes
    ]
