
import argparse, sys
from pathlib import Path
from tqdm import tqdm

from . import pdf_ingest, table_extractor, figure_extractor, spectrum_digitizer, llm_summarizer, merger

# nfp_etl/cli.py (文件最顶部，其他 import 之前)
import warnings
try:
    # 新旧 cryptography 版本都兼容
    from cryptography.utils import CryptographyDeprecationWarning
    warnings.filterwarnings("ignore", category=CryptographyDeprecationWarning)
except Exception:
    pass
# 再保险：按消息关键字屏蔽
warnings.filterwarnings(
    "ignore",
    message="ARC4 has been moved to cryptography.hazmat.decrepit.ciphers.algorithms.ARC4",
)


def run(args):
    pdf_dir = Path(args.pdf_dir)
    out_dir = Path(args.out_dir)
    staging_root = Path("data/staging")
    digitizer = spectrum_digitizer.SpectrumDigitizer()

    try:
        for pdf in tqdm(sorted(pdf_dir.glob("*.pdf"))):
            paper_id = pdf.stem
            staging_dir = staging_root / paper_id
            layout_path = pdf_ingest.run(str(pdf), str(staging_dir))

            tables_meta = []
            if args.enable_table:
                tables_dir = staging_dir / "tables"
                metas = table_extractor.extract_tables(str(pdf), str(tables_dir))
                tables_meta = metas

            figures_meta = []
            if args.enable_figure:
                fig_dir = staging_dir / "figures"
                figs = figure_extractor.extract_figures(str(pdf), layout_path, str(fig_dir))
                figures_meta = figs

            spectrum_meta = []
            if args.enable_spectrum and figures_meta:
                for f in figures_meta:
                    res = digitizer.analyze(f["path"])
                    spectrum_meta.append({"figure": f, "result": res})

            text_json = staging_dir / "text_structured.json"
            # 关键点：如果 LLM 不可用，则 summarize_text_blocks 会抛异常，直接终止整个程序。
            llm_summarizer.summarize_text_blocks(str(layout_path), "configs/schema.yml", "configs/prompts", str(text_json))

            main_csv = out_dir / "nfp_samples.csv"
            merger.merge_records(str(text_json), tables_meta, spectrum_meta, str(main_csv))

        print(f"Done. Output: {out_dir}")
    except Exception as e:
        print(f"[FATAL] LLM-required extraction failed: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf_dir", type=str, required=True)
    parser.add_argument("--out_dir", type=str, required=True)
    parser.add_argument("--enable-table", action="store_true")
    parser.add_argument("--enable-figure", action="store_true")
    parser.add_argument("--enable-spectrum", action="store_true")
    parser.add_argument("--llm-vision", choices=["on","off"], default="on")
    args = parser.parse_args()
    run(args)

if __name__ == "__main__":
    main()
