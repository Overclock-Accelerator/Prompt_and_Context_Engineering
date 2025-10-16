"""
Usage:
  python split_10k_html.py path/to/10k.html --parts 5 --prefix out/part_

Fast + tolerant SEC 10-K splitter.
- Detects SEC-style "Item X" headings (Item 1, 1A, 7, 7A, etc.)
- Handles case, nbsp, punctuation, and nested wrappers
- Splits document into roughly balanced HTML parts

Requires: pip install beautifulsoup4 lxml
"""

import argparse, os, math, re
from bs4 import BeautifulSoup, NavigableString, Tag, Comment

CANON_ORDER = [
    "ITEM 1", "ITEM 1A", "ITEM 1B", "ITEM 1C",
    "ITEM 2", "ITEM 3", "ITEM 4",
    "ITEM 5", "ITEM 6",
    "ITEM 7", "ITEM 7A",
    "ITEM 8", "ITEM 9", "ITEM 9A", "ITEM 9B", "ITEM 9C",
    "ITEM 10", "ITEM 11", "ITEM 12", "ITEM 13", "ITEM 14",
    "ITEM 15", "ITEM 16"
]

# --- tolerant Item heading matcher
ITEM_RE = re.compile(
    r"item\s*\d{1,2}[A-Za-z]?\s*[\.\-–:)]?",
    re.IGNORECASE
)
NBSP_RE = re.compile(r"\u00A0+")

def norm_text(t: str) -> str:
    t = NBSP_RE.sub(" ", t or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t

def load_html(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def ensure_doctype(html_text):
    t = html_text.lstrip()
    if not t.lower().startswith("<!doctype"):
        return "<!DOCTYPE html>\n" + html_text
    return html_text

def clone_head(soup):
    head = soup.head
    if head:
        return BeautifulSoup(str(head), "lxml").head
    return BeautifulSoup("<head><meta charset='utf-8'></head>", "lxml").head

def text_weight(nodes):
    total = 0
    for n in nodes:
        if isinstance(n, NavigableString):
            total += len(n)
        elif isinstance(n, Tag):
            total += len(n.get_text(" ", strip=False)) + len(str(n)) // 20
    return total

# --- Find Items and split DOM properly
def normalize_item_label(text):
    """Normalize an Item label to canonical form."""
    label = norm_text(text).upper().replace("–", "-").replace(":", "")
    # Extract just "ITEM XX" part (number with optional letter)
    match = re.match(r'(ITEM\s+\d{1,2}[A-Z]?)', label)
    if match:
        label = match.group(1)
    # Remove trailing period/punctuation
    label = re.sub(r'[\.\-]+$', '', label).strip()
    return label

def find_all_items(soup):
    """Find all unique Item labels in canonical order, filtering out TOC entries."""
    text = soup.get_text("\n", strip=True)
    found_labels = {}  # Map label -> position of LAST occurrence

    # Find all matches and track last occurrence of each
    for m in ITEM_RE.finditer(text):
        label = normalize_item_label(m.group(0))
        # Extract just the number part to check validity
        num_match = re.search(r'(\d+)', label)
        if num_match:
            num = int(num_match.group(1))
            # Filter spurious matches (valid 10-K Items are 1-16)
            if num > 16 or num < 1:
                continue
        # Keep updating with later positions (real headings come after TOC)
        found_labels[label] = m.start()

    # Return in canonical order
    ordered = [label for label in CANON_ORDER if label in found_labels]
    return ordered if ordered else []

def find_deepest_common_container(soup, item_labels):
    """Find the deepest element that contains all Items."""
    # Start from body and go deeper
    current = soup.body

    while True:
        children_with_items = []
        for child in current.children:
            if not hasattr(child, 'get_text'):
                continue
            text = child.get_text(" ", strip=True).upper()
            # Check if this child contains any Items
            has_item = any(label in text for label in item_labels)
            if has_item:
                children_with_items.append(child)

        # If only one child has all Items, go deeper
        if len(children_with_items) == 1:
            current = children_with_items[0]
        else:
            break

    return current

def split_container_by_items(container, item_labels):
    """Split container's children at Item boundaries."""
    children = list(container.children)
    if not children:
        return [(None, [container])]

    # Find which child each Item LAST appears in (to skip TOC)
    item_positions = {}  # Map label -> last idx where it appears

    for idx, child in enumerate(children):
        if not hasattr(child, 'get_text'):
            continue

        text = child.get_text(" ", strip=True).upper()

        # Check each Item label
        for label in item_labels:
            if label in text:
                # Keep updating to track LAST occurrence
                item_positions[label] = idx

    if not item_positions:
        return [(None, children)]

    # Sort by canonical order, not position
    # Create list in the order items appear in item_labels
    ordered_items = [(label, item_positions[label]) for label in item_labels if label in item_positions]

    sections = []
    for i, (label, start_idx) in enumerate(ordered_items):
        end_idx = ordered_items[i+1][1] if i+1 < len(ordered_items) else len(children)
        section_nodes = children[start_idx:end_idx]
        sections.append((label, section_nodes))

    return sections

def chunk_by_items_fast(soup):
    """Split DOM by Item boundaries, returning actual DOM nodes."""
    item_labels = find_all_items(soup)
    if not item_labels:
        return [(None, [soup.body])], False

    # Find the deepest container that has all Items
    container = find_deepest_common_container(soup, item_labels)
    sections = split_container_by_items(container, item_labels)
    return sections, True

def split_oversized_chunk(label, nodes, target_size, max_parts):
    """Split a large chunk into balanced sub-parts by cumulative size."""
    total_size = sum(len(str(n)) for n in nodes)

    if total_size <= target_size * 2:
        return [(label, nodes)]

    # Calculate how many parts we need for this chunk
    num_subparts = min(max_parts, max(2, int(total_size / target_size)))
    target_per_subpart = total_size / num_subparts

    # Build sub-parts by cumulative size
    subparts = []
    current_batch = []
    current_size = 0

    for node in nodes:
        node_size = len(str(node))
        current_batch.append(node)
        current_size += node_size

        # If we hit target size and haven't maxed out parts yet
        if current_size >= target_per_subpart and len(subparts) < num_subparts - 1:
            subparts.append((label, current_batch))
            current_batch = []
            current_size = 0

    # Add remaining nodes as final subpart
    if current_batch:
        subparts.append((label, current_batch))

    return subparts if subparts else [(label, nodes)]

def pack_into_parts(chunks, k):
    """Pack chunks into k balanced parts, splitting oversized Items."""
    # Calculate weight of each chunk (DOM node sizes)
    weights = []
    for _, nodes in chunks:
        w = sum(len(str(n)) for n in nodes)
        weights.append(w)

    total = sum(weights) or 1
    target = total / k

    # First pass: identify and split oversized chunks
    processed_chunks = []

    for (label, nodes), w in zip(chunks, weights):
        # If this chunk is huge (>2x target), split it into sub-parts
        if w > target * 2:
            # Reserve enough parts for the oversized item
            subparts = split_oversized_chunk(label, nodes, target, k)
            processed_chunks.extend(subparts)
        else:
            processed_chunks.append((label, nodes))

    # Second pass: pack processed chunks into parts
    parts = []
    cur, curw = [], 0

    for label, nodes in processed_chunks:
        w = sum(len(str(n)) for n in nodes)

        # If adding this would exceed target and we haven't reached k parts yet, start new
        if cur and curw + w > target * 1.5 and len(parts) < k - 1:
            parts.append(cur)
            cur, curw = [], 0

        cur.append((label, nodes))
        curw += w

    if cur:
        parts.append(cur)

    return parts

def build_html_doc(head_tpl, lang, chunk_group):
    """Build complete HTML document from chunks of DOM nodes."""
    soup = BeautifulSoup("", "lxml")
    html = soup.new_tag("html")
    if lang:
        html["lang"] = lang
    soup.append(html)
    html.append(BeautifulSoup(str(head_tpl), "lxml").head)
    body = soup.new_tag("body")
    html.append(body)

    for label, nodes in chunk_group:
        # Add Item comment marker
        if label:
            comment = Comment(f" {label} ")
            body.append(NavigableString("\n"))
            body.append(comment)
            body.append(NavigableString("\n"))

        # Append actual DOM nodes (not as strings!)
        for node in nodes:
            # Clone the node by parsing its string representation
            if isinstance(node, NavigableString):
                body.append(type(node)(str(node)))
            elif isinstance(node, Tag):
                # Parse and append the node's HTML
                cloned = BeautifulSoup(str(node), "lxml")
                # Extract the actual content (skip html/body wrappers that lxml adds)
                for child in cloned.body.children if cloned.body else cloned.children:
                    body.append(child)
            else:
                body.append(str(node))

    return ensure_doctype(str(soup))

def main():
    ap = argparse.ArgumentParser(description="Split SEC 10-K HTML into structure-aware parts.")
    ap.add_argument("input", help="Path to 10-K HTML file")
    ap.add_argument("--parts", type=int, default=5)
    ap.add_argument("--prefix", default="part_")
    args = ap.parse_args()

    html_text = load_html(args.input)
    soup = BeautifulSoup(html_text, "lxml")

    if not soup.body:
        raise SystemExit("No <body> found in HTML.")

    chunks, has_items = chunk_by_items_fast(soup)
    if not has_items:
        print("Warning: No standard 'Item X' headings detected. Output will be coarse by top-level blocks.")
    else:
        print(f"Found {len(chunks)} unique Items")

    parts = pack_into_parts(chunks, max(1, args.parts))
    print(f"Packed into {len(parts)} parts (requested {args.parts})")

    head_tpl = clone_head(soup)
    lang = soup.html.get("lang") if soup.html else None

    os.makedirs(os.path.dirname(args.prefix) or ".", exist_ok=True)

    for i, group in enumerate(parts, start=1):
        doc = build_html_doc(head_tpl, lang, group)
        outpath = f"{args.prefix}{i}.html"
        with open(outpath, "w", encoding="utf-8") as f:
            f.write(doc)
        labels = [lbl for lbl, _ in group if lbl]
        size_kb = len(doc) // 1024
        print(f"Wrote {outpath} ({size_kb}KB)  Items: {', '.join(labels) or '—'}")

if __name__ == "__main__":
    main()

