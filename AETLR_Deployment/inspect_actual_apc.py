import json
from pathlib import Path
import pandas as pd

p = Path('c:/Users/nevesj/OneDrive - Hiscox/Documents/Alteryx ETL Replacements ADO/AETLR_Deployment/validation/Actual Result/UNP_00047_APC.xlsx')
if not p.exists():
    raise FileNotFoundError(p)

x = pd.ExcelFile(p)
out = {"path": str(p), "sheets": x.sheet_names}
for s in x.sheet_names:
    df = pd.read_excel(x, sheet_name=s, dtype=object)
    out[s] = {
        "row_count": len(df),
        "columns": list(df.columns),
        "head": df.head(5).fillna("").astype(str).to_dict(orient="records"),
    }
print(json.dumps(out, indent=2, ensure_ascii=False))
