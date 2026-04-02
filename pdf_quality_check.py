import glob, os, json
from collections import Counter
import pdfplumber

pdf_dir = "outputs/literature/PDF"
pdf_files = sorted(glob.glob(os.path.join(pdf_dir, "*.pdf")))
print(f"总PDF数: {len(pdf_files)}")

# 1. 年份分布
print("\n=== 年份分布 ===")
year_dist = {}
for f in pdf_files:
    fname = os.path.basename(f)
    yr = fname[:4] if fname[:4].isdigit() else "unknown"
    year_dist[yr] = year_dist.get(yr, 0) + 1
for y in sorted(year_dist.keys()):
    bar = "#" * (year_dist[y] // 2)
    print(f"  {y}: {year_dist[y]:3d} {bar}")

# 2. 期刊分布
print("\n=== 期刊分布 TOP20 ===")
journal_counts = Counter()
for f in pdf_files:
    fname = os.path.basename(f)
    parts = fname.split("_", 1)
    if len(parts) > 1:
        rest = parts[1]
        # journal is between year and last part (the title)
        sub = rest.split("_", 1)
        if len(sub) > 1:
            journal = sub[0]
            journal_counts[journal] += 1
for j, c in journal_counts.most_common(20):
    print(f"  {j}: {c}")

# 3. 文件大小
print("\n=== 文件大小 ===")
sizes = [(os.path.getsize(f)/1024, os.path.basename(f)) for f in pdf_files]
sizes.sort()
print(f"  最小: {sizes[0][0]:.0f}KB | {sizes[0][1][:70]}")
print(f"  中位: {sizes[len(sizes)//2][0]:.0f}KB")
print(f"  最大: {sizes[-1][0]/1024:.1f}MB | {sizes[-1][1][:70]}")
tiny = [(s, n) for s, n in sizes if s < 100]
print(f"  <100KB可疑 ({len(tiny)}): ")
for s, n in tiny[:5]:
    print(f"    {s:.0f}KB | {n[:70]}")

# 4. 抽样读内容
print("\n=== 抽样内容检查 (15篇) ===")
# 选不同位置的
indices = [0, 5, 10, 20, 30, 40, 60, 80, 100, 120, 150, 180, 200, 220, 240]
indices = [min(i, len(sizes)-1) for i in indices]

for rank, idx in enumerate(indices):
    sz, fname = sizes[idx]
    fp = os.path.join(pdf_dir, fname)
    print(f"\n--- [{rank+1}] sz={sz:.0f}KB ---")
    print(f"  {fname[:90]}")
    try:
        doc = pdfplumber.open(fp)
        pcount = len(doc.pages)
        print(f"  页数: {pcount}")
        text = doc.pages[0].extract_text() or ""
        if text.strip():
            clean = " ".join(text.split())[:300]
            print(f"  首屏: {clean}...")
        else:
            print(f"  [!] 首屏无文本(扫描件?)")
        doc.close()
    except Exception as e:
        print(f"  [X] {e}")
