import glob, os

pdf_files = glob.glob('outputs/literature/PDF/*.pdf')
valid = 0
invalid = 0
invalid_list = []
empty_list = []

for f in pdf_files:
    sz = os.path.getsize(f)
    if sz < 100:
        empty_list.append((sz, f))
        invalid += 1
        continue
    try:
        with open(f, 'rb') as fh:
            header = fh.read(5)
            if header == b'%PDF-':
                # Check it has actual content
                content = fh.read()
                if b'/Pages' in content or b'/Root' in content:
                    valid += 1
                else:
                    invalid += 1
                    invalid_list.append((sz, f))
            else:
                invalid += 1
                invalid_list.append((sz, f))
    except Exception as e:
        invalid += 1
        invalid_list.append((sz, f))

print(f"Valid PDFs: {valid}")
print(f"Invalid PDFs: {invalid}")
print(f"  Empty/truncated (<100B): {len(empty_list)}")
print(f"  Invalid headers/content: {len(invalid_list)}")

if empty_list:
    print(f"\n--- Empty/truncated files ({len(empty_list)}): ---")
    for sz, f in sorted(empty_list, key=lambda x: x[0]):
        print(f"  {sz}B | {os.path.basename(f)[:85]}")

if invalid_list:
    print(f"\n--- Invalid content ({len(invalid_list)}): ---")
    for sz, f in sorted(invalid_list, key=lambda x: x[0]):
        sz_str = f"{sz/1024:.1f}KB" if sz >= 1024 else f"{sz}B"
        print(f"  {sz_str} | {os.path.basename(f)[:85]}")

# Now check valid PDFs for content quality
print(f"\n=== Content quality check (valid PDFs, sampling 20) ===")
import pdfplumber
import sys

valid_files = [f for f in pdf_files if f not in [x[1] for x in empty_list] and f not in [x[1] for x in invalid_list]]

# Sort by size to get diverse samples
valid_files_with_size = [(os.path.getsize(f), f) for f in valid_files]
valid_files_with_size.sort(key=lambda x: x[0])

# Sample: small, medium, large
sample_indices = [0, 5, 10, 20, 40, 60, 80, 100, 120, 150, 170, 180, 185, 188, 190, 192]
sample_indices = [min(i, len(valid_files_with_size)-1) for i in sample_indices]

for rank, idx in enumerate(sample_indices):
    sz, fpath = valid_files_with_size[idx]
    fname = os.path.basename(fpath)
    sz_str = f"{sz/1024:.0f}KB" if sz >= 1024 else f"{sz}B"
    try:
        doc = pdfplumber.open(fpath)
        pages = len(doc.pages)
        text = doc.pages[0].extract_text() or ""
        doc.close()
        
        # Quality indicators
        word_count = len(text.split()) if text.strip() else 0
        has_abstract = "abstract" in text.lower() or "ABSTRACT" in text
        has_keywords = "keyword" in text.lower() or "荧光" in text or "fluorescent" in text.lower()
        has_methods = "method" in text.lower() or "experimental" in text.lower() or "experiment" in text.lower()
        
        preview = " ".join(text.split())[:200] if text.strip() else "(empty)"
        
        status = "GOOD" if word_count > 50 else "WARN"
        if word_count < 20:
            status = "POOR"
        
        print(f"\n[{rank+1}] ({status}) {sz_str} | {pages}pg | {fname[:75]}")
        print(f"    Words: {word_count} | Abstract: {has_abstract} | Fluorescence refs: {has_keywords}")
        print(f"    Preview: {preview}")
    except UnicodeEncodeError:
        print(f"\n[{rank+1}] (ENCODE_ERR) {sz_str} | {fname[:75]}")
    except Exception as e:
        print(f"\n[{rank+1}] (ERROR) {sz_str} | {fname[:75]} | {e}")
