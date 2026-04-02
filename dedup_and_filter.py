import os, glob, re
from collections import defaultdict

PDF_DIR = r'D:\Desktop\DATA-Download_Extraction\outputs\literature\PDF'
DUP_DIR = r'D:\Desktop\DATA-Download_Extraction\outputs\literature\duplicates'
os.makedirs(DUP_DIR, exist_ok=True)

pdf_files = sorted(glob.glob(os.path.join(PDF_DIR, '*.pdf')))
print(f"Total valid PDFs: {len(pdf_files)}")

# Build title-based dedup groups
by_title = defaultdict(list)
for f in pdf_files:
    fname = os.path.basename(f)
    sz = os.path.getsize(f)
    
    # Parse year_source_title
    parts = fname.split('_', 2)
    year_f = parts[0] if len(parts) >= 1 else '?'
    source_f = parts[1] if len(parts) >= 2 else ''
    title_part = parts[2].replace('.pdf', '').strip() if len(parts) >= 3 else fname.replace('.pdf', '')
    
    # Normalize title for dedup
    title_norm = re.sub(r'[^a-z0-9\s]', '', title_part.lower()).strip()
    title_norm = re.sub(r'\s+', ' ', title_norm)
    
    # Use first 60 chars as key
    key = title_norm[:60] if len(title_norm) > 60 else title_norm
    
    by_title[key].append({
        'path': f,
        'fname': fname,
        'size': sz,
        'year': year_f,
        'source': source_f,
        'title_title': title_part[:80]
    })

# Find duplicates
dup_groups = {k: v for k, v in by_title.items() if len(v) > 1}
print(f"\nDuplicate groups: {len(dup_groups)}")
print(f"Total duplicate files: {sum(len(v) for v in dup_groups.values())}")
print(f"Files to remove: {sum(len(v)-1 for v in dup_groups.values())}")

dupes_removed = 0
for key, items in dup_groups.items():
    # Keep largest file
    items.sort(key=lambda x: x['size'], reverse=True)
    print(f"\n  DUP [{len(items)}x]: {key[:70]}...")
    for i, it in enumerate(items):
        marker = "  KEEP" if i == 0 else "  MOVE"
        print(f"    {marker} [{it['size']/1024:.0f}KB] {it['fname'][:80]}")
    
    # Move duplicates to dup dir
    for i in range(1, len(items)):
        try:
            dst = os.path.join(DUP_DIR, items[i]['fname'])
            if not os.path.exists(dst):
                os.rename(items[i]['path'], dst)
                dupes_removed += 1
        except Exception as e:
            print(f"      ERR: {e}")

print(f"\nTotal duplicates removed: {dupes_removed}")
final = len(glob.glob(os.path.join(PDF_DIR, '*.pdf')))
print(f"Final unique PDFs: {final}")

# ============================================================
# Step 3: Relevance check
# ============================================================
print(f"\n{'='*60}")
print("RELEVANCE CHECK")
print(f"{'='*60}")

remaining = sorted(glob.glob(os.path.join(PDF_DIR, '*.pdf')))
relevant_count = 0
edge_count = 0
irrelevant_count = 0

for f in remaining:
    fname = os.path.basename(f).lower()
    
    # Core keywords
    core = ['fluorescent', 'lumin', 'phosphor', 'quantum dot', 'qd', 'ucnp', 
            'aie', 'carbon dot', 'nanoprobe', 'nanosensor', 'fluorophore']
    
    # Irrelevant topics
    irrelevant = ['trichloroethylene', 'fenton', 'humic acid', 
                   'formamide denaturation', 'cytokine regulated glycan',
                   'respiratory', 'pulmonary toxicity', 'nano zinc oxide']
    
    is_core = any(k in fname for k in core)
    is_irrel = any(k in fname for k in irrelevant)
    
    if is_irrel:
        irrelevant_count += 1
        print(f"  [IRRELEVANT] {fname[:90]}")
    elif is_core:
        relevant_count += 1
    else:
        edge_count += 1
        print(f"  [EDGE    ] {fname[:90]}")

print(f"\n  Relevant: {relevant_count}")
print(f"  Edge cases: {edge_count}")
print(f"  Irrelevant: {irrelevant_count}")
