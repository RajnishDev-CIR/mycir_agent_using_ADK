import pandas as pd
from pathlib import Path

EXCEL_PATH = Path("250630_Database of Indicative System Prices_V2_SS_GB.xlsx")
OUTPUT_PATH = Path("capex_agent/data/system_price.csv")

def export():
    if not EXCEL_PATH.exists():
        print(f"ERROR: Excel file not found at {EXCEL_PATH}")
        print("Place the Excel file in the project root folder.")
        return

    xl = pd.ExcelFile(EXCEL_PATH)
    df = pd.read_excel(xl, sheet_name="System Price ", header=1)

    df = df.iloc[:, 1:20]
    df.columns = [
        "contingency_pct", "margin_pct", "type", "size_mwp",
        "module_rate", "inverter_rate", "racking_rate", "bos_rate",
        "mechanical_rate", "electrical_rate", "civil_rate",
        "engineering_rate", "permitting_rate", "overhead_rate",
        "margin_rate", "sales_tax_rate", "contingency_amount",
        "bonding_rate", "total_rate"
    ]

    df["type"] = df["type"].astype(str).str.strip()
    df = df.dropna(subset=["type", "size_mwp"])
    df = df[df["type"].isin(["GM", "RT", "CP"])]
    df = df.reset_index(drop=True)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)
    print(f"Exported {len(df)} rows to {OUTPUT_PATH}")
    print(df.groupby("type")["size_mwp"].count().to_string())

if __name__ == "__main__":
    export()
