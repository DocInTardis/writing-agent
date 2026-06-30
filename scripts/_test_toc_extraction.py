import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.fetch_academic_papers import download_arxiv_source, extract_toc_from_latex

aid = '2201.00978v1'
print(f"Downloading source for {aid}...")
src = download_arxiv_source(aid, timeout=30)
if src:
    print(f"Downloaded {len(src)} bytes")
    toc = extract_toc_from_latex(src)
    print(f"Found {len(toc)} sections:")
    for s in toc:
        indent = "  " * (s["level"] - 1)
        print(f"{indent}- {s['title']}")
else:
    print("Failed to download source")
