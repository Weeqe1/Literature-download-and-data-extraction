import sys, os
file_path = r"D:\Desktop\DATA-Download_Extraction\run_staged_extraction.py"
with open(file_path, 'r', encoding='utf-8') as f:
    code = f.read()

if "import build_clean_dataset" not in code:
    code = code.replace("import sys", "import sys\nimport build_clean_dataset\nimport os")
    
    find_str = "    print(\"=\"*50)\n\n\nif __name__"
    replace_str = "    print(\"=\"*50)\n    \n    # Post-process dataset\n    out_csv = os.path.join(os.path.dirname(args.out_dir) if args.out_dir.endswith('extraction') else args.out_dir, 'nfp_ml_ready_dataset.csv')\n    try:\n        build_clean_dataset.build_dataset(args.out_dir, out_csv)\n    except Exception as e:\n        print('Failed to build ML dataset:', e)\n\n\nif __name__"
    code = code.replace(find_str, replace_str)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(code)
    print("Code updated.")
else:
    print("Already updated.")