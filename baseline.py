from pathlib import Path
import urllib.request

import opendssdirect as dss
import pandas as pd

# Absolute paths, because OpenDSS changes the working folder when it loads a circuit
PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data" / "IEEETestCases"
FEEDER_FILE = DATA_DIR / "13Bus" / "IEEE13Nodeckt.dss"

BASE_URL = "https://raw.githubusercontent.com/dss-extensions/electricdss-tst/master/Version8/Distrib/IEEETestCases/"
FILES = [
    "13Bus/IEEE13Nodeckt.dss",
    "13Bus/IEEELineCodes.DSS",
    "13Bus/IEEE13Node_BusXY.csv",
    "IEEELineCodes.DSS",
]


def download_feeder():
    """Download the IEEE 13 bus files the first time, then reuse the local copy."""
    for name in FILES:
        local = DATA_DIR / name
        if not local.exists():
            local.parent.mkdir(parents=True, exist_ok=True)
            print("Downloading", name)
            urllib.request.urlretrieve(BASE_URL + name, local)


def load_feeder():
    """Load the IEEE 13 bus feeder fresh and solve it."""
    download_feeder()
    dss.Text.Command("clear")
    dss.Text.Command(f'compile "{FEEDER_FILE}"')
    dss.Solution.Solve()


def get_voltages():
    """Return a table of per unit voltage at every node."""
    df = pd.DataFrame({
        "node": dss.Circuit.AllNodeNames(),
        "v_pu": dss.Circuit.AllBusMagPu(),
    })

    def label(v):
        if v > 1.05:
            return "HIGH"
        if v < 0.95:
            return "LOW"
        return "ok"

    df["status"] = df["v_pu"].apply(label)
    return df


if __name__ == "__main__":
    load_feeder()

    print("Solved and converged:", dss.Solution.Converged())
    kw, kvar = dss.Circuit.TotalPower()
    # OpenDSS reports power leaving the substation as negative, so flip the sign
    print(f"Power from substation: {-kw:,.0f} kW, {-kvar:,.0f} kvar")
    print()

    df = get_voltages()
    print(df.to_string(index=False))
    print()
    print(f"Lowest:  {df['v_pu'].min():.4f} pu at {df.loc[df['v_pu'].idxmin(), 'node']}")
    print(f"Highest: {df['v_pu'].max():.4f} pu at {df.loc[df['v_pu'].idxmax(), 'node']}")