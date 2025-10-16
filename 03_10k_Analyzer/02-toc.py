from bs4 import BeautifulSoup, Comment
import re, json, os, argparse

# Canonical Item order
CANON_ORDER = [
    "ITEM 1", "ITEM 1A", "ITEM 1B", "ITEM 1C",
    "ITEM 2", "ITEM 3", "ITEM 4",
    "ITEM 5", "ITEM 6",
    "ITEM 7", "ITEM 7A",
    "ITEM 8", "ITEM 9", "ITEM 9A", "ITEM 9B", "ITEM 9C",
    "ITEM 10", "ITEM 11", "ITEM 12", "ITEM 13", "ITEM 14",
    "ITEM 15", "ITEM 16"
]

def extract_title_from_text(text):
    """Extract title portion after 'ITEM X.' or 'I TEM X\t' (handles split text)"""
    # Match "ITEM 1A." or "I TEM 1A\t" followed by the title
    match = re.match(r'I\s*TEM\s+\d{1,2}[A-Za-z]?[\.\t\s]+(.+)', text, re.I)
    if match:
        title = match.group(1).strip()
        # Clean up: remove excessive whitespace, truncate if too long
        title = re.sub(r'\s+', ' ', title)
        if len(title) > 100:
            title = title[:97] + "..."
        return title if title else None
    return None

def extract_items_from_file(path):
    """Extract Items by finding <!-- ITEM X --> comment markers."""
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        soup = BeautifulSoup(f, "lxml")

    found = {}  # Map label -> (title, snippet) (using dict to dedupe)

    # Find all comment nodes that match <!-- ITEM X -->
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment_text = comment.strip()

        # Check if this is an Item comment marker
        match = re.match(r'ITEM\s+(\d{1,2}[A-Za-z]?)', comment_text, re.I)
        if not match:
            continue

        label = f"ITEM {match.group(1).upper()}"

        # Skip if already found in this file
        if label in found:
            continue

        # Look for the title in the next few sibling elements
        title = None
        snippet = None
        current = comment.next_sibling
        attempts = 0

        # Create a regex to match the exact Item label (not substrings like "ITEM 1" matching "ITEM 1A")
        exact_label_re = re.compile(r'\b' + re.escape(label) + r'\b', re.I)

        while current and attempts < 10:
            if hasattr(current, 'get_text'):
                text = current.get_text(" ", strip=True)
                if text and exact_label_re.search(text):
                    # Found the heading that contains the exact Item label
                    title = extract_title_from_text(text)
                    # Keep the raw HTML as snippet
                    snippet = str(current)
                    break
            current = current.next_sibling
            attempts += 1

        found[label] = (title, snippet)

    return found

def extract_items_from_original(html_path, parts_folder):
    """Extract Items from original HTML, map to which part file they appear in."""
    with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
        soup = BeautifulSoup(f, "lxml")

    item_info = {}  # Map label -> (title, snippet)

    # Find all <p> tags that might contain Item headings
    for p_tag in soup.find_all('p'):
        # Get the combined text of the <p> tag
        p_text = p_tag.get_text(" ", strip=True)

        # Check if this looks like an Item heading (handles split text like "I TEM 10")
        match = re.match(r'I\s*TEM\s+(\d{1,2}[A-Za-z]?)', p_text, re.I)
        if not match:
            continue

        label = f"ITEM {match.group(1).upper()}"

        # Skip if already found
        if label in item_info:
            continue

        # Check if this is a real heading (has bold spans) vs TOC (normal weight)
        # Look for at least one bold span
        bold_spans = p_tag.find_all('span', style=re.compile(r'font-weight:bold'))
        if not bold_spans:
            continue  # Skip TOC entries

        # Extract title and snippet
        title = extract_title_from_text(p_text)
        snippet = str(p_tag)

        item_info[label] = (title, snippet)

    # Now determine which part file each Item appears in
    item_to_file = {}  # Map label -> (file, title, snippet)

    for fn in sorted(os.listdir(parts_folder)):
        if not fn.endswith(".html"):
            continue

        filepath = os.path.join(parts_folder, fn)
        # Just look for comment markers to determine which file has which Item
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        for label in CANON_ORDER:
            if label in item_to_file:
                continue
            # Check if this part has the Item marker
            if f"<!-- {label} -->" in content:
                title, snippet = item_info.get(label, (None, None))
                item_to_file[label] = (fn, title, snippet)

    return item_to_file

def main():
    ap = argparse.ArgumentParser(description="Generate TOC from original 10-K HTML and split files.")
    ap.add_argument("source_html", help="Original 10-K HTML file")
    ap.add_argument("parts_folder", help="Folder containing split HTML files")
    ap.add_argument("--output", default="toc.json", help="Output JSON file (default: toc.json)")
    args = ap.parse_args()

    # Extract Items from original HTML and map to part files
    item_to_file = extract_items_from_original(args.source_html, args.parts_folder)

    # Build TOC in canonical order
    toc = []
    for label in CANON_ORDER:
        if label in item_to_file:
            fn, title, snippet = item_to_file[label]
            entry = {
                "label": label,
                "title": title,
                "snippet": snippet,
                "file": fn
            }
            toc.append(entry)

    # Write output
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(toc, f, indent=2, ensure_ascii=False)

    print(f"Wrote {args.output} with {len(toc)} entries")

if __name__ == "__main__":
    main()
