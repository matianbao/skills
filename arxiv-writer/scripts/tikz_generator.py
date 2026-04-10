#!/usr/bin/env python3
"""
tikz_generator.py — JSON → TikZ 两阶段图生成器

LLM 只需生成结构化 JSON 描述（节点、边、分组），
本脚本自动计算坐标、检测碰撞、生成 TikZ 代码。

用法:
    python3 tikz_generator.py input.json -o output.tex
    python3 tikz_generator.py input.json  # 输出到 stdout
"""

import json
import sys
import argparse
import math
import os
import subprocess
import tempfile
import re
from dataclasses import dataclass, field
from typing import Optional


# ============================================================
# Data Structures
# ============================================================

@dataclass
class BBox:
    """Bounding box in cm."""
    x: float
    y: float
    w: float
    h: float

    @property
    def left(self): return self.x - self.w / 2
    @property
    def right(self): return self.x + self.w / 2
    @property
    def top(self): return self.y + self.h / 2
    @property
    def bottom(self): return self.y - self.h / 2

    def overlaps(self, other: "BBox", margin: float = 0.05) -> bool:
        return not (self.right + margin <= other.left or
                    other.right + margin <= self.left or
                    self.top + margin <= other.bottom or
                    other.top + margin <= self.bottom)


@dataclass
class NodeInfo:
    id: str
    label: str
    node_type: str = "module"
    group: Optional[str] = None
    row: int = 0
    col: int = 0
    col_span: int = 1
    dim: Optional[str] = None
    dim_pos: str = "above"  # above, below, left, right
    min_width: Optional[float] = None  # cm, override
    min_height: Optional[float] = None
    custom_fill: Optional[str] = None
    x: float = 0.0  # computed
    y: float = 0.0  # computed
    bbox: Optional[BBox] = None


@dataclass
class EdgeInfo:
    from_id: str
    to_ids: list  # single target or list for fork
    style: str = "default"  # default, fork, residual, dashed, signal


@dataclass
class GroupInfo:
    id: str
    label: str
    style: str = "dashed"
    node_ids: list = field(default_factory=list)


# ============================================================
# Default Styles
# ============================================================

DEFAULT_FILLS = {
    "input":     "gray!8",
    "encoder":   "orange!12",
    "core":      "blue!10",
    "output":    "green!10",
    "loss":      "red!12",
    "prediction": "green!15",
    "frozen":    "gray!10",
    "gate":      "purple!10",
    "norm":      "gray!8",
    "pool":      "blue!6",
    "concat":    "green!10",
    "module":    "white",
}

DEFAULT_MIN_WIDTH = {
    "input":     8.0,
    "encoder":   2.2,
    "core":      2.2,
    "output":    1.2,
    "loss":      2.0,
    "prediction": 1.8,
    "pool":      1.8,
    "concat":    4.0,
    "module":    2.2,
}

DEFAULT_MIN_HEIGHT = 0.7  # cm


# ============================================================
# Layout Engine
# ============================================================

class LayoutEngine:
    def __init__(self, config: dict, layout: str = "bottom-to-top"):
        self.row_gap = config.get("row_gap", 1.5)
        self.col_gap = config.get("col_gap", 3.2)
        self.inter_group_extra = config.get("inter_group_gap", 0.6)
        self.dim_offset = 0.2  # cm offset for dim annotations
        self.layout = layout

    def compute_positions(self, nodes: list[NodeInfo], groups: list[GroupInfo]):
        """Assign physical (x, y) coordinates from logical (row, col).
        bottom-to-top: row→Y (up), col→X (right)
        left-to-right: row→X (right), col→Y (down, flipped so col=0 is top)"""

        # Find group boundaries
        group_top_rows = {}
        for g in groups:
            member_rows = set()
            for n in nodes:
                if n.group == g.id:
                    member_rows.add(n.row)
            if member_rows:
                group_top_rows[max(member_rows)] = g.id

        all_rows = sorted(set(n.row for n in nodes))
        all_cols = sorted(set(n.col for n in nodes))
        if not all_rows or not all_cols:
            return

        # Compute row positions (primary axis) with inter-group gaps
        row_pos = {}
        current = 0.0
        for i, row in enumerate(all_rows):
            row_pos[row] = current
            if i < len(all_rows) - 1:
                gap = self.row_gap
                if row in group_top_rows:
                    gap += self.inter_group_extra
                current += gap

        # Compute col positions (secondary axis), centered around 0
        mid_col = (min(all_cols) + max(all_cols)) / 2.0
        col_pos = {}
        for c in all_cols:
            col_pos[c] = (c - mid_col) * self.col_gap

        # Assign positions based on layout direction
        for n in nodes:
            primary = row_pos.get(n.row, 0.0)

            if n.col_span > 1:
                start_col = n.col - (n.col_span - 1) // 2
                span_cols = [c for c in all_cols if start_col <= c < start_col + n.col_span]
                if not span_cols:
                    span_cols = all_cols
                secondary = sum(col_pos[c] for c in span_cols) / len(span_cols)
            else:
                secondary = col_pos.get(n.col, 0.0)

            if self.layout == "left-to-right":
                n.x = primary       # row drives horizontal position
                n.y = -secondary     # col drives vertical (flip so col=0 is top)
            else:
                n.x = secondary      # col drives horizontal position
                n.y = primary        # row drives vertical position

    def compute_bboxes(self, nodes: list[NodeInfo], style_overrides: dict):
        """Compute bounding boxes for collision detection."""
        for n in nodes:
            fill = style_overrides.get(n.node_type, {}).get("fill", DEFAULT_FILLS.get(n.node_type, "white"))
            w = n.min_width if n.min_width else DEFAULT_MIN_WIDTH.get(n.node_type, 2.2)
            h = n.min_height if n.min_height else DEFAULT_MIN_HEIGHT
            # Estimate height from label line count
            line_count = n.label.count("\\\\") + 1
            if line_count > 1:
                h = max(h, 0.4 * line_count + 0.3)
            n.bbox = BBox(n.x, n.y, w, h)


# ============================================================
# Collision Detector
# ============================================================

class CollisionDetector:
    def __init__(self, min_gap: float = 0.3):
        self.min_gap = min_gap

    def _estimate_dim_bbox(self, n: NodeInfo) -> Optional[BBox]:
        """Estimate bounding box for a node's dim annotation."""
        if not n.dim or not n.bbox:
            return None
        # Estimate dim text width: ~0.12cm per char (tiny font), min 1.0cm
        text_len = len(n.dim.replace("$", "").replace("\\", "").replace("{", "").replace("}", ""))
        dim_w = max(text_len * 0.12, 1.0)
        # Math content renders taller than plain text in \tiny
        has_math = "$" in n.dim
        dim_h = 0.45 if has_math else 0.3
        dim_gap = 0.15
        if n.dim_pos == "above":
            dim_y = n.bbox.top + dim_gap + dim_h / 2
            return BBox(n.x, dim_y, dim_w, dim_h)
        elif n.dim_pos == "below":
            dim_y = n.bbox.bottom - dim_gap - dim_h / 2
            return BBox(n.x, dim_y, dim_w, dim_h)
        elif n.dim_pos == "left":
            dim_x = n.bbox.left - dim_gap - dim_w / 2
            return BBox(dim_x, n.y, dim_w, dim_h)
        elif n.dim_pos == "right":
            dim_x = n.bbox.right + dim_gap + dim_w / 2
            return BBox(dim_x, n.y, dim_w, dim_h)
        return None

    def detect_and_fix(self, nodes: list[NodeInfo]) -> list[str]:
        """Detect overlapping nodes and fix. Handles same-row and cross-row dim overlaps."""
        log = []
        # Phase 1: Fix same-row node-node collisions (horizontal push)
        max_iterations = 10
        for iteration in range(max_iterations):
            found_collision = False
            for i in range(len(nodes)):
                for j in range(i + 1, len(nodes)):
                    ni, nj = nodes[i], nodes[j]
                    if ni.bbox is None or nj.bbox is None:
                        continue
                    if ni.row != nj.row:
                        continue
                    if ni.bbox.overlaps(nj.bbox, self.min_gap):
                        found_collision = True
                        overlap = (ni.bbox.right + self.min_gap) - nj.bbox.left
                        if overlap > 0:
                            shift = overlap / 2 + 0.1
                            ni.x -= shift
                            ni.bbox.x -= shift
                            nj.x += shift
                            nj.bbox.x += shift
                            log.append(f"  Fixed horizontal: '{ni.id}' <-> '{nj.id}' (shifted ±{shift:.2f}cm)")
            if not found_collision:
                break

        # Phase 2: Fix cross-row dim-annotation vs node overlaps (vertical push)
        # Build list of (dim_bbox, owner_node) pairs
        dim_bboxes = []
        for n in nodes:
            db = self._estimate_dim_bbox(n)
            if db:
                dim_bboxes.append((db, n))

        for iteration in range(max_iterations):
            found_collision = False
            for dim_bb, dim_owner in dim_bboxes:
                # Recompute dim bbox after any shifts
                db = self._estimate_dim_bbox(dim_owner)
                if not db:
                    continue
                for n in nodes:
                    if n.id == dim_owner.id or n.bbox is None:
                        continue
                    if n.row == dim_owner.row:
                        continue  # same-row handled in Phase 1
                    if db.overlaps(n.bbox, 0.1):
                        found_collision = True
                        # Push the rows apart: shift all nodes in the higher row upward
                        # Use generous padding (0.35cm) to account for TikZ rendering variance
                        overlap_y = db.top - n.bbox.bottom + 0.35
                        if dim_owner.row < n.row and overlap_y > 0:
                            # dim is above owner, overlaps with higher-row node
                            # Push higher row up
                            for m in nodes:
                                if m.row >= n.row:
                                    m.y += overlap_y
                                    if m.bbox:
                                        m.bbox.y += overlap_y
                            log.append(f"  Fixed vertical: dim of '{dim_owner.id}' overlapped '{n.id}' (shifted row {n.row}+ up {overlap_y:.2f}cm)")
                        elif dim_owner.row > n.row and overlap_y > 0:
                            # dim is below owner, overlaps with lower-row node
                            overlap_y = n.bbox.top - db.bottom + 0.35
                            if overlap_y > 0:
                                for m in nodes:
                                    if m.row >= dim_owner.row:
                                        m.y += overlap_y
                                        if m.bbox:
                                            m.bbox.y += overlap_y
                                log.append(f"  Fixed vertical: dim of '{dim_owner.id}' overlapped '{n.id}' (shifted row {dim_owner.row}+ up {overlap_y:.2f}cm)")
            if not found_collision:
                break
        return log

    def detect_and_fix_with_real_dims(self, nodes: list[NodeInfo],
                                       real_dim_bboxes: dict[str, BBox]) -> list[str]:
        """Phase 3: Use real measured dim bboxes for cross-row collision detection."""
        log = []
        max_iterations = 10

        for iteration in range(max_iterations):
            found_collision = False
            for n in nodes:
                dim_id = f"dim-{n.id}"
                if dim_id not in real_dim_bboxes:
                    continue
                # Get the real bbox and shift it to match node's current position
                real_bb = real_dim_bboxes[dim_id]
                # The real bbox was measured at the original position;
                # we need to adjust for any position shifts that happened
                db = BBox(n.x + (real_bb.x - real_bb.x),  # center at node x
                          real_bb.y + (n.y - n.y),  # keep measured y offset
                          real_bb.w, real_bb.h)
                # Actually, we should reconstruct the dim bbox position relative to the node
                if n.dim_pos in ("above", "below"):
                    db = BBox(n.x, db.y, real_bb.w, real_bb.h)
                elif n.dim_pos == "left":
                    db = BBox(n.bbox.left - 0.15 - real_bb.w / 2 if n.bbox else n.x - 1.0,
                              n.y, real_bb.w, real_bb.h)
                elif n.dim_pos == "right":
                    db = BBox(n.bbox.right + 0.15 + real_bb.w / 2 if n.bbox else n.x + 1.0,
                              n.y, real_bb.w, real_bb.h)

                if n.dim_pos == "above" and n.bbox:
                    db = BBox(n.x, n.bbox.top + 0.15 + real_bb.h / 2, real_bb.w, real_bb.h)
                elif n.dim_pos == "below" and n.bbox:
                    db = BBox(n.x, n.bbox.bottom - 0.15 - real_bb.h / 2, real_bb.w, real_bb.h)

                for other in nodes:
                    if other.id == n.id or other.bbox is None:
                        continue
                    if other.row == n.row:
                        continue
                    if db.overlaps(other.bbox, 0.1):
                        found_collision = True
                        overlap_y = db.top - other.bbox.bottom + 0.25
                        if n.row < other.row and overlap_y > 0:
                            for m in nodes:
                                if m.row >= other.row:
                                    m.y += overlap_y
                                    if m.bbox:
                                        m.bbox.y += overlap_y
                            log.append(f"  Fixed (real): dim of '{n.id}' overlapped '{other.id}' (shifted row {other.row}+ up {overlap_y:.2f}cm)")
                        elif n.row > other.row and overlap_y > 0:
                            overlap_y = other.bbox.top - db.bottom + 0.25
                            if overlap_y > 0:
                                for m in nodes:
                                    if m.row >= n.row:
                                        m.y += overlap_y
                                        if m.bbox:
                                            m.bbox.y += overlap_y
                                log.append(f"  Fixed (real): dim of '{n.id}' overlapped '{other.id}' (shifted row {n.row}+ up {overlap_y:.2f}cm)")
            if not found_collision:
                break
        return log

    def check_edge_crossing(self, nodes: list[NodeInfo], edges: list[EdgeInfo]) -> list[str]:
        """Check if edges would cross through nodes. Returns warnings."""
        warnings = []
        node_map = {n.id: n for n in nodes}
        for e in edges:
            src = node_map.get(e.from_id)
            targets = e.to_ids if isinstance(e.to_ids, list) else [e.to_ids]
            for tid in targets:
                tgt = node_map.get(tid)
                if not src or not tgt or not src.bbox or not tgt.bbox:
                    continue
                # Check if direct line would cross any intermediate node
                for n in nodes:
                    if n.id in (e.from_id, tid) or n.bbox is None:
                        continue
                    if self._line_crosses_bbox(src.x, src.y, tgt.x, tgt.y, n.bbox):
                        warnings.append(f"  Edge {e.from_id}->{tid} crosses node '{n.id}' (will use L-route)")
        return warnings

    @staticmethod
    def _line_crosses_bbox(x1, y1, x2, y2, box: BBox) -> bool:
        """Rough check: does a straight line between two points cross a bbox?"""
        # Only check if the bbox is between the two y-coords
        min_y, max_y = min(y1, y2), max(y1, y2)
        if box.top < min_y or box.bottom > max_y:
            return False
        min_x, max_x = min(x1, x2), max(x1, x2)
        if box.right < min_x or box.left > max_x:
            return False
        # If same column (roughly), no crossing
        if abs(x1 - x2) < 0.1:
            return box.left < x1 < box.right and box.bottom < (y1 + y2) / 2 < box.top
        # Linear interpolation at box center y
        t = (box.y - y1) / (y2 - y1) if abs(y2 - y1) > 0.01 else 0.5
        if not (0 < t < 1):
            return False
        x_at_box = x1 + t * (x2 - x1)
        return box.left < x_at_box < box.right


# ============================================================
# TikZ Code Generator
# ============================================================

class TikZGenerator:
    def __init__(self, diagram: dict, nodes: list[NodeInfo], edges: list[EdgeInfo],
                 groups: list[GroupInfo], style_overrides: dict, measure_mode: bool = False):
        self.diagram = diagram
        self.nodes = nodes
        self.edges = edges
        self.groups = groups
        self.style_overrides = style_overrides
        self.node_map = {n.id: n for n in nodes}
        self.lines = []
        self.measure_mode = measure_mode

    def generate(self) -> str:
        self.lines = []
        scale = self.diagram.get("scale", 0.75)
        double_col = self.diagram.get("double_column", True)
        fig_env = "figure*" if double_col else "figure"

        self._emit(f"\\begin{{{fig_env}}}[t]")
        self._emit("\\centering")
        self._emit(f"\\begin{{tikzpicture}}[")
        self._emit(f"    scale={scale}, every node/.style={{scale={scale}}},")
        self._emit_styles()
        self._emit("]")
        self._emit("")

        # Measurement file setup (two-pass mode)
        if self.measure_mode:
            self._emit("% === Measurement macros (two-pass mode) ===")
            self._emit("\\newwrite\\bboxfile")
            self._emit("\\immediate\\openout\\bboxfile=\\jobname.bbox")
            self._emit("")

        # Group nodes by group, then by row
        self._emit_nodes()
        self._emit("")
        self._emit_edges()
        self._emit("")
        self._emit_groups()
        self._emit_group_labels()

        # Decorations (e.g., cdots ellipsis between nodes)
        if "decorations" in self.diagram:
            self._emit("")
            self._emit_decorations(self.diagram["decorations"])

        # Zoom-in sub-diagram
        if "zoom_in" in self.diagram:
            self._emit("")
            self._emit_zoom_in(self.diagram["zoom_in"])

        self._emit("")
        if self.measure_mode:
            self._emit("\\immediate\\closeout\\bboxfile")
        self._emit("\\end{tikzpicture}")

        caption = self.diagram.get("caption", "TODO: Add caption.")
        label = self.diagram.get("label", "fig:diagram")
        self._emit(f"\\caption{{{caption}}}")
        self._emit(f"\\label{{{label}}}")
        self._emit(f"\\end{{{fig_env}}}")

        return "\n".join(self.lines) + "\n"

    def _emit(self, line: str):
        self.lines.append(line)

    def _emit_styles(self):
        self._emit("    module/.style={draw, rounded corners=3pt, minimum height=0.7cm, align=center, font=\\footnotesize},")
        self._emit("    stage/.style={draw, dashed, rounded corners=5pt, inner sep=12pt, gray!60},")
        self._emit("    arr/.style={-{Stealth[length=2.5mm]}, thick},")
        self._emit("    resarr/.style={-{Stealth[length=2mm]}, thick, dashed, color=gray!50},")
        self._emit("    sigarr/.style={-{Stealth[length=2mm]}, thick, dashed, color=red!60},")
        self._emit("    dim/.style={font=\\tiny, color=gray!60!black},")
        self._emit("    stagelabel/.style={font=\\footnotesize\\bfseries, color=gray!50!black, fill=white, inner sep=2pt},")

    def _get_fill(self, node: NodeInfo) -> str:
        if node.custom_fill:
            return node.custom_fill
        override = self.style_overrides.get(node.node_type, {}).get("fill")
        if override:
            return override
        return DEFAULT_FILLS.get(node.node_type, "white")

    def _get_min_width(self, node: NodeInfo) -> float:
        if node.min_width:
            return node.min_width
        return DEFAULT_MIN_WIDTH.get(node.node_type, 2.2)

    def _emit_nodes(self):
        # Sort by row then col for readability
        sorted_nodes = sorted(self.nodes, key=lambda n: (n.row, n.col))

        current_group = None
        for n in sorted_nodes:
            if n.group != current_group:
                current_group = n.group
                group_label = current_group or "ungrouped"
                self._emit(f"% ============ {group_label} ============")

            fill = self._get_fill(n)
            mw = self._get_min_width(n)
            mh = n.min_height if n.min_height else DEFAULT_MIN_HEIGHT

            # Build style options
            opts = [f"fill={fill}", f"minimum width={mw}cm"]
            line_count = n.label.count("\\\\") + 1
            if line_count > 1 or mh > DEFAULT_MIN_HEIGHT:
                actual_h = max(mh, 0.4 * line_count + 0.3) if line_count > 1 else mh
                opts.append(f"minimum height={actual_h:.1f}cm")
            if n.node_type == "frozen":
                opts.append("dashed")

            opts_str = ", ".join(opts)
            self._emit(f"\\node[module, {opts_str}] ({n.id}) at ({n.x:.2f}, {n.y:.2f}) {{{n.label}}};")

            # Dim annotation
            if n.dim:
                dim_id = f"dim-{n.id}"
                pos_map = {
                    "above": f"above={self._dim_offset(n)}cm of {n.id}",
                    "below": f"below={self._dim_offset(n)}cm of {n.id}",
                    "left":  f"anchor=east, left=0.15cm of {n.id}",
                    "right": f"anchor=west, right=0.15cm of {n.id}",
                }
                pos = pos_map.get(n.dim_pos, f"above={self._dim_offset(n)}cm of {n.id}")
                self._emit(f"\\node[dim, {pos}] ({dim_id}) {{{n.dim}}};")
                # Two-pass: measure dim node bounding box using PGF internals
                if self.measure_mode:
                    self._emit(f"\\makeatletter")
                    self._emit(f"\\pgfpointanchor{{{dim_id}}}{{south west}}")
                    self._emit(f"\\pgf@xa=\\pgf@x \\pgf@ya=\\pgf@y")
                    self._emit(f"\\pgfpointanchor{{{dim_id}}}{{north east}}")
                    self._emit(f"\\immediate\\write\\bboxfile{{{dim_id},\\the\\pgf@xa,\\the\\pgf@ya,\\the\\pgf@x,\\the\\pgf@y}}")
                    self._emit(f"\\makeatother")

    def _dim_offset(self, n: NodeInfo) -> str:
        return "0.15"

    def _emit_edges(self):
        self._emit("% ============ Connections ============")
        layout = self.diagram.get("layout", "bottom-to-top")

        # Pre-scan: build convergence map (target_id -> list of source_ids)
        # Used for multi-to-one: distribute arrival offsets evenly
        convergence: dict[str, list[str]] = {}
        for e in self.edges:
            targets = e.to_ids if isinstance(e.to_ids, list) else [e.to_ids]
            if len(targets) == 1:
                tid = targets[0]
                convergence.setdefault(tid, [])
                convergence[tid].append(e.from_id)

        for e in self.edges:
            targets = e.to_ids if isinstance(e.to_ids, list) else [e.to_ids]
            src = self.node_map.get(e.from_id)
            if not src:
                self._emit(f"% WARNING: source node '{e.from_id}' not found")
                continue

            if len(targets) == 1:
                tgt = self.node_map.get(targets[0])
                if not tgt:
                    self._emit(f"% WARNING: target node '{targets[0]}' not found")
                    continue
                # Pass convergence info for multi-to-one offset calculation
                sources_to_tgt = convergence.get(targets[0], [])
                self._emit_single_edge(src, tgt, e.style, sources_to_tgt, layout)
            else:
                self._emit_fork_edge(src, targets, e.style, layout)

    def _emit_single_edge(self, src: NodeInfo, tgt: NodeInfo, style: str,
                          all_sources: list[str], layout: str):
        arr_style = self._edge_style(style)

        if style == "bidirectional":
            self._emit(f"\\draw[{{Stealth[length=2.5mm]}}-{{Stealth[length=2.5mm]}}, thick] ({src.id}) -- ({tgt.id});")
            return

        if style == "residual":
            self._emit_residual_edge(src, tgt, arr_style)
            return

        is_vertical = layout == "bottom-to-top"
        if is_vertical:
            same_axis = abs(src.x - tgt.x) < 0.1
        else:
            same_axis = abs(src.y - tgt.y) < 0.1

        if same_axis:
            self._emit(f"\\draw[{arr_style}] ({src.id}) -- ({tgt.id});")
        else:
            # Cross-axis: L-route with adaptive offset
            offset = self._compute_convergence_offset(src, tgt, all_sources, layout)
            if is_vertical:
                if tgt.y > src.y:
                    self._emit(f"\\draw[{arr_style}] ({src.id}.north) -- ++(0, 0.6) -| ($({tgt.id}.south) + ({offset:.1f}, 0)$);")
                else:
                    self._emit(f"\\draw[{arr_style}] ({src.id}.south) -- ++(0, -0.6) -| ($({tgt.id}.north) + ({offset:.1f}, 0)$);")
            else:
                # left-to-right layout
                if tgt.x > src.x:
                    self._emit(f"\\draw[{arr_style}] ({src.id}.east) -- ++(0.6, 0) |- ($({tgt.id}.west) + (0, {offset:.1f})$);")
                else:
                    self._emit(f"\\draw[{arr_style}] ({src.id}.west) -- ++(-0.6, 0) |- ($({tgt.id}.east) + (0, {offset:.1f})$);")

    def _compute_convergence_offset(self, src: NodeInfo, tgt: NodeInfo,
                                     all_sources: list[str], layout: str) -> float:
        """Compute arrival offset for multi-to-one convergence.
        If only one source hits this target cross-axis, use near-side offset.
        If multiple sources converge, distribute them evenly across target width."""
        is_vertical = layout == "bottom-to-top"

        # Filter to only cross-axis sources (same-axis ones use direct line, no offset)
        cross_sources = []
        for sid in all_sources:
            s = self.node_map.get(sid)
            if not s:
                continue
            if is_vertical and abs(s.x - tgt.x) >= 0.1:
                cross_sources.append(s)
            elif not is_vertical and abs(s.y - tgt.y) >= 0.1:
                cross_sources.append(s)

        if len(cross_sources) <= 1:
            # Single cross-axis source: near-side offset (same side as source)
            if is_vertical:
                dist = abs(src.x - tgt.x)
                offset_mag = min(1.0, dist * 0.3)  # adaptive: scale with distance
                return -offset_mag if src.x < tgt.x else offset_mag
            else:
                dist = abs(src.y - tgt.y)
                offset_mag = min(1.0, dist * 0.3)
                return -offset_mag if src.y < tgt.y else offset_mag

        # Multiple cross-axis sources: distribute evenly
        cross_sources_sorted = sorted(cross_sources,
                                       key=lambda s: s.x if is_vertical else s.y)
        tgt_half_w = (tgt.min_width or DEFAULT_MIN_WIDTH.get(tgt.node_type, 2.2)) / 2 - 0.2
        n = len(cross_sources_sorted)
        idx = next((i for i, s in enumerate(cross_sources_sorted) if s.id == src.id), 0)
        if n == 1:
            return 0.0
        # Spread from -tgt_half_w to +tgt_half_w
        return -tgt_half_w + (2 * tgt_half_w) * idx / (n - 1)

    def _emit_residual_edge(self, src: NodeInfo, tgt: NodeInfo, arr_style: str):
        """Residual/skip connection: route along the outside, auto-choose side."""
        # Choose the side with more space (further from center)
        all_x = [n.x for n in self.nodes]
        center_x = (min(all_x) + max(all_x)) / 2 if all_x else 0
        avg_x = (src.x + tgt.x) / 2

        if avg_x <= center_x:
            # Node pair is on the left side or center → route via left
            self._emit(f"\\draw[{arr_style}] ({src.id}.west) -- ++(-0.6, 0) |- ({tgt.id}.west);")
        else:
            # Node pair is on the right side → route via right
            self._emit(f"\\draw[{arr_style}] ({src.id}.east) -- ++(0.6, 0) |- ({tgt.id}.east);")

    def _emit_fork_edge(self, src: NodeInfo, target_ids: list, style: str, layout: str):
        arr_style = self._edge_style(style)
        targets = [self.node_map[tid] for tid in target_ids if tid in self.node_map]
        if not targets:
            return

        fork_rise = 0.3
        is_vertical = layout == "bottom-to-top"
        targets_sorted = sorted(targets, key=lambda t: t.x if is_vertical else t.y)

        for tgt in targets_sorted:
            if is_vertical:
                if abs(tgt.x - src.x) < 0.1:
                    self._emit(f"\\draw[{arr_style}] ({src.id}.north) -- ({tgt.id}.south);")
                else:
                    self._emit(f"\\draw[{arr_style}] ({src.id}.north) -- ++(0, {fork_rise}) -| ({tgt.id}.south);")
            else:
                if abs(tgt.y - src.y) < 0.1:
                    self._emit(f"\\draw[{arr_style}] ({src.id}.east) -- ({tgt.id}.west);")
                else:
                    self._emit(f"\\draw[{arr_style}] ({src.id}.east) -- ++({fork_rise}, 0) |- ({tgt.id}.west);")

    def _edge_style(self, style: str) -> str:
        return {
            "default": "arr",
            "fork": "arr",
            "residual": "resarr",
            "dashed": "sigarr",
            "signal": "sigarr",
            "bidirectional": "arr",
        }.get(style, "arr")

    def _emit_groups(self):
        if not self.groups:
            return
        self._emit("% ============ Stage Grouping Boxes ============")
        for g in self.groups:
            members = [n for n in self.nodes if n.group == g.id]
            if not members:
                continue
            # Collect all node ids + their dim annotation ids
            fit_ids = []
            for n in members:
                fit_ids.append(n.id)
                if n.dim:
                    fit_ids.append(f"dim-{n.id}")
            fit_str = ")(".join(fit_ids)
            self._emit(f"\\node[stage, fit=({fit_str})] ({g.id}box) {{}};")

    def _emit_group_labels(self):
        if not self.groups:
            return
        layout = self.diagram.get("layout", "bottom-to-top")
        self._emit("")
        self._emit("% ============ Stage Labels ============")
        for g in self.groups:
            members = [n for n in self.nodes if n.group == g.id]
            if not members:
                continue
            if layout == "left-to-right":
                self._emit(f"\\node[stagelabel, anchor=south east, rotate=90] at ({g.id}box.north west) {{{g.label}}};")
            else:
                self._emit(f"\\node[stagelabel, anchor=south west] at ({g.id}box.north west) {{{g.label}}};")

    def _emit_decorations(self, decorations: list):
        """Emit decorative elements like cdots, labels, arrows between nodes."""
        self._emit("% ============ Decorations ============")
        for d in decorations:
            dtype = d.get("type", "cdots")
            if dtype == "cdots":
                # Place $\cdots$ midway between two nodes
                n1 = d.get("between", [None, None])[0]
                n2 = d.get("between", [None, None])[1]
                if n1 and n2:
                    self._emit(f"\\node[dim] at ($({n1})!0.5!({n2})$) {{$\\cdots$}};")
            elif dtype == "text":
                # Arbitrary text at midpoint or absolute position
                n1 = d.get("between", [None, None])[0]
                n2 = d.get("between", [None, None])[1]
                text = d.get("text", "")
                if n1 and n2:
                    self._emit(f"\\node[dim] at ($({n1})!0.5!({n2})$) {{{text}}};")

    def _emit_zoom_in(self, zoom: dict):
        """Generate a zoom-in sub-diagram connected to a target node.
        Sub-nodes use row/col layout (same logic as main diagram) for positioning."""
        self._emit("% ============ Zoom-In Detail ============")
        target_id = zoom.get("target_node", "")
        position = zoom.get("position", "right")
        sub_nodes_data = zoom.get("nodes", [])
        sub_edges = zoom.get("edges", [])
        box_label = zoom.get("label", "Detail")

        if not sub_nodes_data:
            return

        target = self.node_map.get(target_id)
        if not target:
            self._emit(f"% WARNING: zoom target '{target_id}' not found")
            return

        # Parse sub-nodes into NodeInfo objects for layout
        sub_nodes = []
        for sn in sub_nodes_data:
            sub_nodes.append(NodeInfo(
                id=sn.get("id", "zn"),
                label=sn.get("label", ""),
                node_type=sn.get("type", "module"),
                row=sn.get("row", 0),
                col=sn.get("col", 0),
                col_span=sn.get("col_span", 1),
                dim=sn.get("dim"),
                dim_pos=sn.get("dim_pos", "above"),
                min_width=sn.get("min_width", 1.4),
                min_height=sn.get("min_height"),
                custom_fill=sn.get("fill"),
            ))

        # Use layout engine for sub-nodes (tighter spacing)
        sub_config = zoom.get("layout_config", {"row_gap": 0.8, "col_gap": 2.0})
        sub_engine = LayoutEngine(sub_config, self.diagram.get("layout", "bottom-to-top"))
        sub_engine.compute_positions(sub_nodes, [])

        # Compute bounding box of all sub-nodes
        if sub_nodes:
            min_x = min(n.x for n in sub_nodes) - 1.0
            max_x = max(n.x for n in sub_nodes) + 1.0
            min_y = min(n.y for n in sub_nodes) - 0.6
            max_y = max(n.y for n in sub_nodes) + 0.6
        else:
            min_x, max_x, min_y, max_y = -1.5, 1.5, -1.0, 1.0

        box_w = max_x - min_x + 0.8
        box_h = max_y - min_y + 0.8
        sub_center_x = (min_x + max_x) / 2
        sub_center_y = (min_y + max_y) / 2

        # Position zoom box relative to target
        x_offset = (box_w / 2 + 2.5) if position == "right" else -(box_w / 2 + 2.5)
        base_x = target.x + x_offset
        base_y = target.y

        # Shift sub-nodes to zoom box position
        shift_x = base_x - sub_center_x
        shift_y = base_y - sub_center_y
        for n in sub_nodes:
            n.x += shift_x
            n.y += shift_y

        # Emit zoom box background
        self._emit(f"\\node[draw, dashed, rounded corners=4pt, fill={DEFAULT_FILLS.get('encoder', 'orange!5')}!3, "
                   f"minimum width={box_w:.1f}cm, minimum height={box_h:.1f}cm, inner sep=6pt] "
                   f"(zoombox) at ({base_x:.2f}, {base_y:.2f}) {{}};")
        self._emit(f"\\node[font=\\footnotesize\\bfseries, anchor=south] at (zoombox.north) {{{box_label}}};")

        # Emit sub-nodes
        for n in sub_nodes:
            fill = n.custom_fill or DEFAULT_FILLS.get(n.node_type, "red!6")
            mw = n.min_width or 1.4
            opts = f"draw, rounded corners=2pt, fill={fill}, minimum width={mw}cm, font=\\scriptsize, align=center"
            self._emit(f"\\node[{opts}] ({n.id}) at ({n.x:.2f}, {n.y:.2f}) {{{n.label}}};")
            if n.dim:
                dim_id = f"dim-{n.id}"
                self._emit(f"\\node[dim, above=0.1cm of {n.id}] ({dim_id}) {{{n.dim}}};")

        # Sub-edges
        for se in sub_edges:
            self._emit(f"\\draw[arr, thin] ({se['from']}) -- ({se['to']});")

        # Connect zoom box to target with a dotted leader
        anchor = "west" if position == "right" else "east"
        target_anchor = "east" if position == "right" else "west"
        self._emit(f"\\draw[dotted, thick, gray!50] ({target_id}.{target_anchor}) -- (zoombox.{anchor});")


# ============================================================
# Main Pipeline
# ============================================================

def parse_diagram(data: dict):
    """Parse JSON into structured objects."""
    nodes = []
    for nd in data.get("nodes", []):
        nodes.append(NodeInfo(
            id=nd["id"],
            label=nd["label"],
            node_type=nd.get("type", "module"),
            group=nd.get("group"),
            row=nd.get("row", 0),
            col=nd.get("col", 0),
            col_span=nd.get("col_span", 1),
            dim=nd.get("dim"),
            dim_pos=nd.get("dim_pos", "above"),
            min_width=nd.get("min_width"),
            min_height=nd.get("min_height"),
            custom_fill=nd.get("fill"),
        ))

    edges = []
    for ed in data.get("edges", []):
        to = ed["to"]
        if isinstance(to, str):
            to_ids = [to]
        else:
            to_ids = to
        edges.append(EdgeInfo(
            from_id=ed["from"],
            to_ids=to_ids,
            style=ed.get("style", "default"),
        ))

    groups = []
    for gd in data.get("groups", []):
        groups.append(GroupInfo(
            id=gd["id"],
            label=gd.get("label", ""),
            style=gd.get("style", "dashed"),
        ))

    style_overrides = data.get("styles", {})
    return nodes, edges, groups, style_overrides


def generate(json_path: str, output_path: str = None, two_pass: bool = True):
    """Main entry point."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    nodes, edges, groups, style_overrides = parse_diagram(data)

    # Layout config
    layout_config = data.get("layout_config", {})
    layout_config.setdefault("row_gap", 1.5)
    layout_config.setdefault("col_gap", 3.2)
    layout_dir = data.get("layout", "bottom-to-top")

    # Step 1: Layout
    engine = LayoutEngine(layout_config, layout_dir)
    engine.compute_positions(nodes, groups)
    engine.compute_bboxes(nodes, style_overrides)

    print("=== Layout computed ===", file=sys.stderr)
    for n in sorted(nodes, key=lambda n: (n.row, n.col)):
        print(f"  {n.id:20s}  row={n.row} col={n.col}  -> ({n.x:.2f}, {n.y:.2f})", file=sys.stderr)

    # Step 2: Collision detection (Pass 1 — estimated bboxes)
    detector = CollisionDetector()
    fix_log = detector.detect_and_fix(nodes)
    if fix_log:
        print("\n=== Collision fixes (estimated) ===", file=sys.stderr)
        for msg in fix_log:
            print(msg, file=sys.stderr)
        engine.compute_bboxes(nodes, style_overrides)

    # Step 2b: Two-pass — measure real dim bboxes via pdflatex
    if two_pass:
        real_bboxes = _two_pass_measure(data, nodes, edges, groups, style_overrides)
        if real_bboxes:
            print(f"\n=== Two-pass: measured {len(real_bboxes)} real dim bboxes ===", file=sys.stderr)
            # Re-run collision detection with real dim bboxes
            fix_log_2 = detector.detect_and_fix_with_real_dims(nodes, real_bboxes)
            if fix_log_2:
                print("\n=== Collision fixes (real measurements) ===", file=sys.stderr)
                for msg in fix_log_2:
                    print(msg, file=sys.stderr)
                engine.compute_bboxes(nodes, style_overrides)
        else:
            print("\n=== Two-pass: measurement failed, using estimates ===", file=sys.stderr)

    cross_warnings = detector.check_edge_crossing(nodes, edges)
    if cross_warnings:
        print("\n=== Edge crossing warnings ===", file=sys.stderr)
        for w in cross_warnings:
            print(w, file=sys.stderr)

    # Step 3: Generate final TikZ (no measurement macros)
    gen = TikZGenerator(data, nodes, edges, groups, style_overrides, measure_mode=False)
    tikz_code = gen.generate()

    # Output
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(tikz_code)
        print(f"\n=== Output written to {output_path} ===", file=sys.stderr)
    else:
        print(tikz_code)

    # Summary
    print(f"\nSummary: {len(nodes)} nodes, {len(edges)} edges, {len(groups)} groups", file=sys.stderr)
    if not fix_log and not cross_warnings:
        print("No collisions or crossing issues detected.", file=sys.stderr)


def _two_pass_measure(data: dict, nodes: list[NodeInfo], edges: list[EdgeInfo],
                      groups: list[GroupInfo], style_overrides: dict) -> dict[str, BBox]:
    """Pass 1: generate TikZ with measurement macros, compile, parse .bbox file.
    Returns dict of dim-id -> BBox with real measurements."""
    # Generate TikZ with measurement mode
    gen = TikZGenerator(data, nodes, edges, groups, style_overrides, measure_mode=True)
    tikz_code = gen.generate()

    # Create standalone LaTeX document for compilation
    standalone = _wrap_standalone(tikz_code, data)

    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = os.path.join(tmpdir, "measure.tex")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(standalone)

        # Compile
        try:
            result = subprocess.run(
                ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "measure.tex"],
                cwd=tmpdir, capture_output=True, timeout=30,
                env={**os.environ, "PATH": f"/Library/TeX/texbin:/usr/local/texlive/2026basic/bin/universal-darwin:{os.environ.get('PATH', '')}"}
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            print(f"  Two-pass compile failed: {e}", file=sys.stderr)
            return {}

        if result.returncode != 0:
            # Try to extract useful error info
            log_path = os.path.join(tmpdir, "measure.log")
            if os.path.exists(log_path):
                with open(log_path, "r") as f:
                    log_content = f.read()
                errors = [line for line in log_content.split("\n") if line.startswith("!")]
                if errors:
                    print(f"  Two-pass compile errors: {errors[:3]}", file=sys.stderr)
            return {}

        # Parse .bbox file
        bbox_path = os.path.join(tmpdir, "measure.bbox")
        if not os.path.exists(bbox_path):
            print("  Two-pass: no .bbox file generated", file=sys.stderr)
            return {}

        return _parse_bbox_file(bbox_path, data.get("scale", 0.75))


def _wrap_standalone(tikz_code: str, data: dict) -> str:
    """Wrap TikZ code in a standalone LaTeX document for measurement compilation."""
    # Extract just the tikzpicture from the generated code
    # Remove figure environment wrapper
    lines = tikz_code.strip().split("\n")
    tikz_lines = []
    in_tikz = False
    for line in lines:
        if "\\begin{tikzpicture}" in line:
            in_tikz = True
        if in_tikz:
            tikz_lines.append(line)
        if "\\end{tikzpicture}" in line:
            break

    tikz_body = "\n".join(tikz_lines)

    return f"""\\documentclass{{article}}
\\usepackage[paperwidth=50cm,paperheight=50cm,margin=1cm]{{geometry}}
\\usepackage{{tikz}}
\\usetikzlibrary{{arrows.meta, calc, fit, positioning}}
\\usepackage{{amsmath, amssymb}}
\\newcommand{{\\R}}{{\\mathbb{{R}}}}
\\newcommand{{\\ours}}{{\\textsc{{Method}}}}
\\pagestyle{{empty}}
\\begin{{document}}
{tikz_body}
\\end{{document}}
"""


def _parse_bbox_file(bbox_path: str, scale: float) -> dict[str, BBox]:
    """Parse the .bbox file produced by measurement pass.
    Each line: dim-id,sw_x,sw_y,ne_x,ne_y (in pt, already scaled by TikZ)"""
    result = {}
    pt_to_cm = 1.0 / 28.4528  # 1cm = 28.4528pt

    with open(bbox_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            if len(parts) != 5:
                continue
            dim_id = parts[0].strip()
            try:
                # Parse pt values (e.g., "123.45pt" or "123.45")
                vals = []
                for p in parts[1:]:
                    p = p.strip().replace("pt", "")
                    vals.append(float(p) * pt_to_cm)
                sw_x, sw_y, ne_x, ne_y = vals
                # Convert to center + width/height
                cx = (sw_x + ne_x) / 2
                cy = (sw_y + ne_y) / 2
                w = abs(ne_x - sw_x)
                h = abs(ne_y - sw_y)
                if w > 0 and h > 0:
                    result[dim_id] = BBox(cx, cy, w, h)
            except (ValueError, IndexError):
                continue

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JSON → TikZ diagram generator")
    parser.add_argument("input", help="Input JSON file")
    parser.add_argument("-o", "--output", help="Output .tex file (default: stdout)")
    parser.add_argument("--single-pass", action="store_true",
                        help="Skip two-pass measurement (faster, less accurate collision detection)")
    args = parser.parse_args()
    generate(args.input, args.output, two_pass=not args.single_pass)
