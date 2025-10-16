from __future__ import annotations
import re
from typing import List, Dict, Any, Tuple, Optional

# Only accept headers like 'Pregunta 05', 'PREGUNTA Nº 12.' per new spec
HEADER_RE = re.compile(r"^\s*pregunta\s*(n[ºo]\s*)?\d+\s*[)\.]?\s*", re.IGNORECASE)
# Choices must explicitly include a closing parenthesis, e.g., 'A)' (dot not accepted to avoid false positives)
CHOICE_RE = re.compile(r"^[A-E]\s*\)\s*")
SOLUTION_RE = re.compile(r"(\bResoluci[óo]n\b|\bRpta\.?\b)", re.IGNORECASE)


def xyxy(i):
    xs = [v["x"] for v in i]
    ys = [v["y"] for v in i]
    return min(xs), min(ys), max(xs), max(ys)


def overlap_y(b1, b2) -> float:
    _, y0a, _, y1a = b1
    _, y0b, _, y1b = b2
    inter = max(0.0, min(y1a, y1b) - max(y0a, y0b))
    den = max(1e-6, max(y1a - y0a, y1b - y0b))
    return inter / den


def resolve_columns(blocks: List[Dict[str, Any]], forced_columns: Optional[int] = None) -> List[Dict[str, Any]]:
    # Prefer using text paragraphs to infer columns
    candidates = [
        (xyxy(b["bbox"]), idx)
        for idx, b in enumerate(blocks)
        if (b.get("type") in {"paragraph", "line"}) and (b.get("text") or "").strip()
    ]
    if not candidates:
        candidates = [(xyxy(b["bbox"]), idx) for idx, b in enumerate(blocks)]
    if not candidates:
        return [{"blocks": blocks, "xrange": (0.0, 1.0)}]

    # Sort by left x and find largest gap
    lefts = sorted((bb[0], idx) for bb, idx in candidates)
    xs = [x for x, _ in lefts]
    gaps = [(xs[i+1] - xs[i], i) for i in range(len(xs)-1)]
    if not gaps:
        col_blocks = sorted(blocks, key=lambda b: xyxy(b["bbox"])[1])
        xr = (min(xyxy(b["bbox"])[0] for b in col_blocks), max(xyxy(b["bbox"])[2] for b in col_blocks))
        return [{"blocks": col_blocks, "xrange": xr}]
    gap, gi = max(gaps)
    # Forced single-column
    if forced_columns == 1:
        col_blocks = sorted(blocks, key=lambda b: xyxy(b["bbox"])[1])
        xr = (min(xyxy(b["bbox"])[0] for b in col_blocks), max(xyxy(b["bbox"])[2] for b in col_blocks))
        return [{"blocks": col_blocks, "xrange": xr}]
    # Forced double-column: choose best split by minimizing within-cluster variance of center-x
    if forced_columns == 2:
        centers = sorted(((bb[0]+bb[2])/2.0, idx) for bb, idx in candidates)
        best_i = None
        best_ss = None
        xs_only = [c[0] for c in centers]
        # try all split points
        for i in range(1, len(centers)):
            left = xs_only[:i]
            right = xs_only[i:]
            if not left or not right:
                continue
            ml = sum(left)/len(left)
            mr = sum(right)/len(right)
            ssl = sum((x-ml)**2 for x in left)
            ssr = sum((x-mr)**2 for x in right)
            ss = ssl + ssr
            if best_ss is None or ss < best_ss:
                best_ss = ss
                best_i = i
        if best_i is None:
            best_i = len(centers)//2
        left_idxs = {centers[j][1] for j in range(best_i)}
        col1 = [blocks[j] for j in sorted(left_idxs)]
        col2 = [blocks[j] for j in range(len(blocks)) if j not in left_idxs]
        def col_range(col):
            x0s = [xyxy(b["bbox"])[0] for b in col]
            x1s = [xyxy(b["bbox"])[2] for b in col]
            if not x0s:
                return (0.0, 1.0)
            return (max(0.0, min(x0s) - 0.01), min(1.0, max(x1s) + 0.01))
        col1.sort(key=lambda b: xyxy(b["bbox"])[1])
        col2.sort(key=lambda b: xyxy(b["bbox"])[1])
        return [
            {"blocks": col1, "xrange": col_range(col1)},
            {"blocks": col2, "xrange": col_range(col2)},
        ]
    elif gap < 0.15:
        col_blocks = sorted(blocks, key=lambda b: xyxy(b["bbox"])[1])
        xr = (min(xyxy(b["bbox"])[0] for b in col_blocks), max(xyxy(b["bbox"])[2] for b in col_blocks))
        return [{"blocks": col_blocks, "xrange": xr}]
    # Two columns: split indices by gap index
    left_idxs = {lefts[j][1] for j in range(gi+1)}
    col1 = [blocks[j] for j in sorted(left_idxs)]
    col2 = [blocks[j] for j in range(len(blocks)) if j not in left_idxs]
    # Compute xrange for each
    def col_range(col):
        x0s = [xyxy(b["bbox"])[0] for b in col]
        x1s = [xyxy(b["bbox"])[2] for b in col]
        if not x0s:
            return (0.0, 1.0)
        # Add a tiny margin
        return (max(0.0, min(x0s) - 0.01), min(1.0, max(x1s) + 0.01))
    col1.sort(key=lambda b: xyxy(b["bbox"])[1])
    col2.sort(key=lambda b: xyxy(b["bbox"])[1])
    return [
        {"blocks": col1, "xrange": col_range(col1)},
        {"blocks": col2, "xrange": col_range(col2)},
    ]


def segment_page(blocks: List[Dict[str, Any]], page_index: Optional[int] = None, forced_columns: Optional[int] = None) -> List[Dict[str, Any]]:
    # blocks: [{text, bbox, type}]
    # Split into columns first
    columns = resolve_columns(blocks, forced_columns=forced_columns)
    problems: List[Dict[str, Any]] = []

    for col in columns:
        col_blocks = col["blocks"]
        x0c, x1c = col["xrange"]
        i = 0
        while i < len(col_blocks):
            b = col_blocks[i]
            text = (b.get("text") or "").strip()
            if not (HEADER_RE.match(text)):
                i += 1
                continue
            # Start a new problem. Some PDFs split 'Pregunta' and the number in adjacent blocks.
            header_block = b
            # Try to merge with next block if together they form a header
            if i + 1 < len(col_blocks):
                nxt = col_blocks[i+1]
                merged_text = (text + " " + (nxt.get("text") or "").strip()).strip()
                if HEADER_RE.match(merged_text):
                    # expand header bbox
                    x0,y0,x1,y1 = xyxy(b["bbox"])
                    nx0,ny0,nx1,ny1 = xyxy(nxt["bbox"])
                    hx0,hy0,hx1,hy1 = (min(x0,nx0), min(y0,ny0), max(x1,nx1), max(y1,ny1))
                    header_block = {"text": merged_text, "bbox": [{"x":hx0,"y":hy0},{"x":hx1,"y":hy0},{"x":hx1,"y":hy1},{"x":hx0,"y":hy1}], "type": b.get("type")}
                    i += 1  # consume next as part of header
            pb = {"header": header_block, "body": [], "choices": [], "figures": []}
            body_bbox = xyxy(header_block["bbox"])  # start with header box
            i += 1
            # Accumulate until next header
            # Scan ahead to collect blocks until we find E) or we hit next header/solution
            seen_labels = set()
            scan_idx = i
            end_idx = i
            while scan_idx < len(col_blocks):
                cur = col_blocks[scan_idx]
                tcur = (cur.get("text") or "").strip()
                # Constrain to this column by center-x
                cx = (xyxy(cur["bbox"])[0] + xyxy(cur["bbox"])[2]) / 2.0
                if cx < x0c or cx > x1c:
                    scan_idx += 1
                    continue
                if HEADER_RE.match(tcur):
                    break
                if SOLUTION_RE.search(tcur):
                    break
                # Capture choices if present
                if CHOICE_RE.match(tcur):
                    lbl = tcur[:1]
                    seen_labels.add(lbl)
                    pb["choices"].append(cur)
                # Always consider it part of the body region (even if it's a line), to compute the envelope
                pb["body"].append(cur)
                # Expand bbox envelope
                x0,y0,x1,y1 = body_bbox
                cx0,cy0,cx1,cy1 = xyxy(cur["bbox"]) 
                body_bbox = (min(x0,cx0), min(y0,cy0), max(x1,cx1), max(y1,cy1))
                end_idx = scan_idx
                # Stop only when we've seen both A) and E) in this column (reduces bias from stray C))
                if 'A' in seen_labels and 'E' in seen_labels:
                    scan_idx += 1
                    break
                scan_idx += 1
            # Advance i to end of the scanned region
            i = max(i, end_idx + 1)
            # Within collected blocks, detect choices and figures
            for blk in list(pb["body"]):
                t = (blk.get("text") or "").strip()
                if CHOICE_RE.match(t):
                    pb["choices"].append(blk)
            # Ignore figures per new requirement; do not attach figures
            pb["figures"] = []
            # Needs review if <4 choices or header missing
            # Require A–E presence explicitly como recomendado
            labels = { (ch.get("text") or "").strip()[:1] for ch in pb["choices"] }
            if not {'A','B','C','D','E'}.issubset(labels):
                # Attempt to pull choices that might be just below the body (first few following blocks)
                lookahead = 5
                k = i
                while k < len(col_blocks) and lookahead > 0 and not (HEADER_RE.match((col_blocks[k].get("text") or ""))):
                    t = (col_blocks[k].get("text") or "").strip()
                    if CHOICE_RE.match(t):
                        pb["choices"].append(col_blocks[k])
                    lookahead -= 1
                    k += 1
                labels = { (ch.get("text") or "").strip()[:1] for ch in pb["choices"] }
                pb["needs_review"] = not {'A','B','C','D','E'}.issubset(labels)
            else:
                pb["needs_review"] = False
            # Tighten bottom to last choice if present to avoid including solution text below
            if pb["choices"]:
                bottoms = [xyxy(ch["bbox"])[3] for ch in pb["choices"]]
                x0,y0,x1,y1 = body_bbox
                y1 = max(bottoms)
                body_bbox = (x0,y0,x1,y1)
            pb["bbox"] = body_bbox
            problems.append(pb)
        # Post-pass: clusters of choices without headers -> create needs_review problems
        covered = set()
        for pb in problems:
            for blk in ([pb["header"]] if pb.get("header") else []) + pb.get("body", []) + pb.get("choices", []) + pb.get("figures", []):
                covered.add(id(blk))
        # Collect choice blocks not covered
        remain_choices = [blk for blk in col_blocks if id(blk) not in covered and CHOICE_RE.match((blk.get("text") or "").strip())]
        # Sort by top y
        remain_choices.sort(key=lambda b: xyxy(b["bbox"])[1])
        # Cluster by small vertical gaps
        clusters = []
        cur = []
        last_y1 = None
        for blk in remain_choices:
            y0 = xyxy(blk["bbox"])[1]
            if last_y1 is None or y0 - last_y1 < 0.08:
                cur.append(blk)
            else:
                if cur:
                    clusters.append(cur)
                cur = [blk]
            last_y1 = xyxy(blk["bbox"])[3]
        if cur:
            clusters.append(cur)
        for cluster in clusters:
            if len(cluster) < 4:
                continue
            # Determine vertical span
            xs = []
            ys = []
            for blk in cluster:
                x0,y0,x1,y1 = xyxy(blk["bbox"])
                xs += [x0,x1]
                ys += [y0,y1]
            span = (min(xs), min(ys), max(xs), max(ys))
            pb = {"header": {}, "body": [], "choices": list(cluster), "figures": [], "needs_review": True}
            # Attach body blocks that overlap vertically >= 20%
            for blk in col_blocks:
                if id(blk) in covered or blk in cluster:
                    continue
                if overlap_y(span, xyxy(blk["bbox"])) >= 0.2:
                    pb["body"].append(blk)
            # Figures similarly
            for blk in col_blocks:
                if id(blk) in covered or blk in cluster:
                    continue
                t = (blk.get("text") or "").strip()
                if blk.get("type") in {"figure","table","image"} and overlap_y(span, xyxy(blk["bbox"])) >= 0.2:
                    pb["figures"].append(blk)
            # Compute bbox
            allb = [span] + [xyxy(blk["bbox"]) for blk in pb["body"]] + [xyxy(blk["bbox"]) for blk in pb["figures"]]
            x0 = min(b[0] for b in allb)
            y0 = min(b[1] for b in allb)
            x1 = max(b[2] for b in allb)
            y1 = max(b[3] for b in allb)
            pb["bbox"] = (x0,y0,x1,y1)
            problems.append(pb)
    return problems
