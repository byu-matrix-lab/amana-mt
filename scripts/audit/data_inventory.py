"""Inventory: every human-labelled MT slice available vs what AmanaMT used."""
import sys
import tarfile
from pathlib import Path

import pandas as pd
from datasets import load_dataset

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from mqmbench.data.utils import lang_from_pair  # noqa: E402

USED_DA = {"cs", "tr", "uk", "ha", "km", "ps", "fr", "pl", "fi", "et", "is", "lt", "lv",
           "bn", "hi", "gu", "ta", "ja", "kk", "xh", "zu"}
USED_MQM = {"en-de", "zh-en", "en-ru", "he-en", "en-es"}

hf = load_dataset("RicardoRei/wmt-da-human-evaluation", split="train").to_pandas()
inv = hf.groupby(["lp", "year"]).size().unstack(fill_value=0)
inv["total"] = inv.sum(axis=1)
inv["lang"] = [lang_from_pair(lp) for lp in inv.index]
inv["direction"] = ["x_to_en" if lp.endswith("-en") else "en_to_x" if lp.startswith("en-") else "x_to_y"
                    for lp in inv.index]
inv["used_in_amanamt"] = [l in USED_DA and d != "x_to_y" for l, d in zip(inv.lang, inv.direction)]
pd.set_option("display.width", 250, "display.max_rows", 200)
print("=== HF WMT DA: segments per lp x year (used = included in AmanaMT DA tier)")
print(inv.sort_values(["used_in_amanamt", "direction", "lp"]).to_string())
inv.to_csv(ROOT / "results" / "audit_data_inventory_da.csv")

print("\n=== mt-metrics-eval expert/other labels by edition (seg-level files)")
M = Path(sys.argv[1])
for ed in sorted(p.name for p in M.iterdir() if p.is_dir()):
    hs = M / ed / "human-scores"
    if not hs.exists():
        continue
    files = sorted(f.name for f in hs.glob("*.seg.score"))
    keep = [f for f in files if any(k in f for k in (".mqm.", ".esa.", ".da-sqm.", "appraise"))
            and "rater" not in f and "col" not in f]
    print(ed, ":", " ".join(keep))

print("\n=== editions in the tarball (incl. not yet extracted)")
with tarfile.open(M.parent / "mt-metrics-eval-v2.tgz") as t:
    eds = sorted({m.name.split("/")[1] for m in t.getmembers() if m.name.count("/") >= 1 and m.isdir()})
print(eds)
