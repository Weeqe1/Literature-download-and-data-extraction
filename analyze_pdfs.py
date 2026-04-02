import pandas as pd
import os
from collections import Counter

df = pd.read_excel('outputs/literature/_checkpoint.xlsx')
pdf_df = df[df['pdf_path'].notna()].copy()
print(f'PDFs with file path: {len(pdf_df)}')

# Year distribution
if 'year' in pdf_df.columns:
    valid_years = []
    for y in pdf_df['year'].dropna():
        try:
            valid_years.append(int(y))
        except:
            pass
    year_counts = Counter(valid_years)
    print(f'\nYear distribution (PDFs):')
    for y in sorted(year_counts.keys()):
        print(f'  {y}: {year_counts[y]}')

# Journal distribution
if 'journal' in pdf_df.columns:
    journal_counts = Counter([str(j)[:60] for j in pdf_df['journal'].dropna()])
    print(f'\nTop journals (PDFs):')
    for j, c in journal_counts.most_common(20):
        print(f'  {j}: {c}')

# OA status
if 'is_oa' in pdf_df.columns:
    print(f'\nOA status: {pdf_df["is_oa"].value_counts().to_dict()}')

# Download source
if 'download_source' in pdf_df.columns:
    print(f'\nDownload sources: {pdf_df["download_source"].value_counts().head(10).to_dict()}')

# Actual PDF files
pdf_dir = 'outputs/literature/PDF'
pdf_files = []
for f in os.listdir(pdf_dir):
    if f.endswith('.pdf'):
        pdf_files.append(f)
print(f'\nActual PDF files in directory: {len(pdf_files)}')

# List all filenames for sampling
print('\n--- ALL PDF filenames ---')
for f in sorted(pdf_files):
    print(f'  {f}')
