import glob, os, sys

# force utf-8 output
if sys.stdout.encoding and 'utf-8' not in sys.stdout.encoding.lower():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

pdf_files = glob.glob('outputs/literature/PDF/*.pdf')
all_info = []

for f in pdf_files:
    sz = os.path.getsize(f)
    fname = os.path.basename(f)
    info = {"file": fname, "size": sz, "status": "unknown"}
    
    if sz < 100:
        info["status"] = "EMPTY"
    else:
        try:
            with open(f, 'rb') as fh:
                header = fh.read(5)
                if header == b'%PDF-':
                    content = fh.read()
                    if b'/Pages' in content or b'/Root' in content:
                        info["status"] = "VALID_PDF"
                    else:
                        info["status"] = "TRUNCATED"
                else:
                    info["status"] = "BAD_HEADER"
        except Exception as e:
            info["status"] = f"ERROR"

for row in all_info if False else [info for info in [{"file": os.path.basename(f), "size": os.path.getsize(f)} for f in pdf_files]]:
    pass

# Categorize
empty = []
valid = []
truncated = []
bad_header = []

for f in pdf_files:
    sz = os.path.getsize(f)
    fname = os.path.basename(f)
    
    if sz < 100:
        empty.append((sz, fname))
    else:
        try:
            with open(f, 'rb') as fh:
                header = fh.read(5)
                if header == b'%PDF-':
                    content = fh.read()
                    if b'/Pages' in content or b'/Root' in content:
                        valid.append((sz, f, fname))
                    else:
                        truncated.append((sz, fname))
                else:
                    bad_header.append((sz, fname))
        except:
            bad_header.append((sz, fname))

print(f"Total files: {len(pdf_files)}")
print(f"Valid PDFs: {len(valid)}")
print(f"Empty/truncated (<100B): {len(empty)}")
print(f"Truncated (has header but bad content): {len(truncated)}")
print(f"Bad header: {len(bad_header)}")

if empty:
    print(f"\n=== EMPTY files ({len(empty)}) ===")
    for sz, n in sorted(empty):
        print(f"  {n}")

if bad_header:
    print(f"\n=== BAD HEADER files ({len(bad_header)}) ===")
    for sz, n in sorted(bad_header):
        print(f"  {sz/1024:.0f}KB | {n[:80]}")

if truncated:
    print(f"\n=== TRUNCATED files ({len(truncated)}) ===")
    for sz, n in sorted(truncated):
        print(f"  {sz/1024:.0f}KB | {n[:80]}")

# ============================================================
# Content quality check on valid PDFs
# ============================================================
print(f"\n{'='*70}")
print(f"CONTENT QUALITY CHECK (sample 20 from {len(valid)} valid PDFs)")
print(f"{'='*70}")

import pdfplumber

# Sort valid by size
valid.sort(key=lambda x: x[0])

# Sample indices: spread across size range + specific checks
n = len(valid)
sample_idx = list(range(0, n, max(n//18, 1)))[:18]
# Also add smallest and largest
if 0 not in sample_idx: sample_idx.append(0)
if n-1 not in sample_idx: sample_idx.append(n-1)
sample_idx = sorted(set(sample_idx))[:20]

results = []
for rank, idx in enumerate(sample_idx):
    sz, fpath, fname = valid[idx]
    try:
        doc = pdfplumber.open(fpath)
        pages = len(doc.pages)
        text = doc.pages[0].extract_text() or ""
        doc.close()
        
        word_count = len(text.split()) if text.strip() else 0
        has_abstract = bool("abstract" in text.lower() or "ABSTRACT" in text)
        has_keywords = bool("keyword" in text.lower() or "fluorescent" in text.lower() or "nanoprobe" in text.lower() or "nanosensor" in text.lower() or "\u8367\u5149" in text)
        has_methods = bool("method" in text.lower() or "experimental" in text.lower() or "synthesis" in text.lower())
        has_numbers = bool(any("nm" in text.lower() or "excitation" in text.lower() or "emission" in text.lower() or "wavelength" in text.lower() for _ in [1]))
        
        quality = "GOOD"
        if word_count < 20 or not any([has_abstract, has_keywords, has_methods]):
            quality = "POOR"
        elif word_count < 50 or not has_abstract:
            quality = "FAIR"
        
        sz_str = f"{sz/1024:.0f}KB"
        preview = " ".join(text.split())[:180] if text.strip() else "(empty)"
        
        print(f"\n[{rank+1}] [{quality}] {sz_str} | {pages}p | {fname[:70]}")
        print(f"      words={word_count}, abstract={has_abstract}, keywords={has_keywords}, numbers={has_numbers}")
        print(f"      {preview}")
        
        results.append({
            "rank": rank+1,
            "quality": quality,
            "size": sz,
            "pages": pages,
            "words": word_count,
            "file": fname,
            "abstract": has_abstract,
            "keywords": has_keywords,
            "numbers": has_numbers,
            "preview": preview
        })
    except Exception as e:
        sz_str = f"{sz/1024:.0f}KB"
        print(f"\n[{rank+1}] [ERROR] {sz_str} | {fname[:70]} | {e}")
        results.append({"rank": rank+1, "quality": "ERROR", "file": fname, "error": str(e)})

# Summary
print(f"\n{'='*70}")
print(f"SAMPLE QUALITY SUMMARY")
print(f"{'='*70}")
q_counts = {}
for r in results:
    q = r.get("quality", "UNKNOWN")
    q_counts[q] = q_counts.get(q, 0) + 1
for q, c in sorted(q_counts.items()):
    print(f"  {q}: {c}")

# Check for duplicate/very similar content
print(f"\n=== Checking for potential duplicates (same title pattern) ===")
from collections import Counter
title_patterns = Counter()
for sz, fpath, fname in valid:
    # Extract the title part after journal
    parts = fname.split("_", 2)
    if len(parts) >= 3:
        # Normalize the title
        title_part = parts[2].replace(".pdf", "")
        # Truncate to first 60 chars
        title_short = title_part[:60].lower().strip()
        title_patterns[title_short] += 1

dups = {k: v for k, v in title_patterns.items() if v > 1}
if dups:
    print(f"Found {len(dups)} potential duplicate titles:")
    for title, count in sorted(dups.items(), key=lambda x: -x[1]):
        print(f"  [{count}x] {title[:70]}...")
else:
    print("No obvious duplicates found.")
