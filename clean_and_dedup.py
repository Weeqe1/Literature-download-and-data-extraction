"""Clean invalid PDFs, deduplicate remaining, and prepare for extraction."""
import glob
import os
import shutil

PDF_DIR = r'D:\Desktop\DATA-Download_Extraction\outputs\literature\PDF'
BACKUP_DIR = r'D:\Desktop\DATA-Download_Extraction\outputs\literature\invalid_backup'
os.makedirs(BACKUP_DIR, exist_ok=True)

# ============================================================
# Step 1: Classify and move invalid files
# ============================================================
pdf_files = glob.glob(os.path.join(PDF_DIR, '*.pdf'))
print(f"Total files to classify: {len(pdf_files)}")

valid_count = 0
empty_count = 0
bad_header = 0
truncated = 0
invalid_moved = 0

for f in pdf_files:
    fname = os.path.basename(f)
    sz = os.path.getsize(f)
    
    if sz < 100:
        shutil.move(f, os.path.join(BACKUP_DIR, fname))
        empty_count += 1
        invalid_moved += 1
    else:
        try:
            with open(f, 'rb') as fh:
                header = fh.read(5)
                if header == b'%PDF-':
                    content = fh.read()
                    if b'/Pages' in content or b'/Root' in content:
                        valid_count += 1  # Keep in place
                    else:
                        shutil.move(f, os.path.join(BACKUP_DIR, fname))
                        truncated += 1
                        invalid_moved += 1
                else:
                    shutil.move(f, os.path.join(BACKUP_DIR, fname))
                    bad_header += 1
                    invalid_moved += 1
        except Exception as e:
            print(f"  Error reading {fname}: {e}")
            shutil.move(f, os.path.join(BACKUP_DIR, fname))
            invalid_moved += 1

print(f"\nStep 1 Results:")
print(f"  Valid PDFs (kept): {valid_count}")
print(f"  Empty (<100B): {empty_count}")
print(f"  Bad header: {bad_header}")
print(f"  Truncated: {truncated}")
print(f"  Total moved to backup: {invalid_moved}")
print(f"  Files remaining in PDF dir: {len(glob.glob(os.path.join(PDF_DIR, '*.pdf')))}")

# ============================================================
# Step 2: Deduplicate valid PDFs by title
# ============================================================
remaining = sorted(glob.glob(os.path.join(PDF_DIR, '*.pdf')))
print(f"\nStep 2: Deduplicating {len(remaining)} valid PDFs...")

by_title = {}
duplicates_removed = 0
duplicates_dir = os.path.join(PDF_DIR, '..', 'dedup_backup')
os.makedirs(duplicates_dir, exist_ok=True)

for f in remaining:
    fname = os.path.basename(f)
    # Parse: year_source_title.pdf
    parts = fname.split('_', 1)
    if len(parts) < 2:
        title_short = fname.lower()
    else:
        rest = parts[1]
        parts2 = rest.split('_', 1)
        if len(parts2) < 2:
            source = rest
            title_part = ""
        else:
            source = parts2[0]
            title_part = parts2[1]
        
        # Normalize title
        title_norm = title_part.replace('.pdf', '').strip().lower()
        # Remove trailing underscores
        title_norm = title_norm.rstrip('_').strip()
        # Take first 80 chars as matching key
        title_short = title_norm[:80] if len(title_norm) > 80 else title_norm
    
    sz = os.path.getsize(f)
    
    if title_short in by_title:
        # Decide which to keep: larger file
        prev_sz, prev_path = by_title[title_short]
        if sz > prev_sz:
            # Replace
            old = os.path.basename(prev_path)
            shutil.move(prev_path, os.path.join(duplicates_dir, old))
            by_title[title_short] = (sz, f)
        else:
            # Keep existing, move this one
            shutil.move(f, os.path.join(duplicates_dir, fname))
        duplicates_removed += 1
    else:
        by_title[title_short] = (sz, f)

print(f"  Duplicates removed: {duplicates_removed}")
print(f"  Unique PDFs: {len(by_title)}")

# ============================================================
# Step 3: Generate final report CSV
# ============================================================
final = sorted(glob.glob(os.path.join(PDF_DIR, '*.pdf')))
print(f"\nStep 3: Final {len(final)} unique valid PDFs ready for extraction")

# Read checkpoint metadata for DOI mapping
try:
    import pandas as pd
    checkpoint = pd.read_excel(r'D:\Desktop\DATA-Download_Extraction\outputs\literature\_checkpoint.xlsx')
    
    # Build a report
    report_rows = []
    for f in final:
        fname = os.path.basename(f)
        sz = os.path.getsize(f)
        
        # Try to match with checkpoint
        match = checkpoint[checkpoint['pdf_path'].str.contains(fname, na=False)]
        doi = ''
        title = ''
        year = ''
        journal = ''
        
        if len(match) > 0:
            row = match.iloc[0]
            doi = str(row.get('doi', ''))
            title = str(row.get('title', ''))
            year = str(row.get('year', ''))
            journal = str(row.get('journal', ''))
        
        report_rows.append({
            'file': fname[:100],
            'size_kb': round(sz / 1024, 1),
            'year': year,
            'doi': doi[:50] if doi else '',
            'title': str(title)[:80],
            'journal': str(journal)[:50]
        })
    
    report_df = pd.DataFrame(report_rows)
    report_path = r'D:\Desktop\DATA-Download_Extraction\outputs\literature\pdf_inventory.csv'
    report_df.to_csv(report_path, index=False, encoding='utf-8-sig')
    print(f"\nInventory CSV: {report_path} ({len(report_df)} rows)")
    print(f"\nYear distribution of final PDFs:")
    year_dist = report_df[report_df['year'] != '']['year'].value_counts()
    for y in sorted(year_dist.index, key=lambda x: int(x) if x.isdigit() else 0):
        bar = '#' * (year_dist[y] // 2)
        print(f"  {y}: {year_dist[y]:3d} {bar}")
    
    # Top journals
    print(f"\nTop journals:")
    journal_dist = report_df[report_df['journal'] != '']['journal'].value_counts()
    for j, c in journal_dist.head(10).items():
        print(f"  {j}: {c}")
        
except Exception as e:
    print(f"Warning: could not generate CSV report: {e}")
    for f in final:
        fname = os.path.basename(f)
        sz = os.path.getsize(f)
        print(f"  {sz/1024:.0f}KB | {fname[:80]}")
