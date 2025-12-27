import os
from nfp_etl import cli

if __name__ == "__main__":
    # ==== 可根据需要修改路径 ====
    pdf_dir = "data/pdfs"
    out_dir = "data/outputs"

    # ==== 命令行参数等价项 ====
    args = [
        "--pdf_dir", pdf_dir,
        "--out_dir", out_dir,
        "--enable-table",
        "--enable-figure",
        "--enable-spectrum",
        "--llm-vision", "on"
    ]

    print(f"Running NFP pipeline with args: {args}")
    cli.main(args)
