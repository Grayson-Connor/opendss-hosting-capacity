from pathlib import Path

import opendssdirect as dss
import pandas as pd

from baseline import load_feeder

PROJECT_DIR = Path(__file__).resolve().parent
RESULTS_DIR = PROJECT_DIR / "results"

# 3 phase buses where we try adding solar
TEST_BUSES = ["632", "633", "634", "670", "671", "675", "680", "692"]

# Substation and regulator nodes are not customers, so we skip them in the voltage check
SKIP_PREFIXES = ("sourcebus", "650", "rg60")

V_MAX = 1.05
V_MIN = 0.95
STEP_KW = 100
MAX_KW = 10000
LIGHT_LOAD = 0.3  # light load = 30% of normal, a common stand in for a mild sunny midday


def setup(load_mult):
    """Load the feeder, set the load level, then lock the regulator taps."""
    load_feeder()
    dss.Text.Command(f"set loadmult={load_mult}")
    dss.Solution.Solve()  # regulators adjust to this load level
    # Lock taps: regulators are slow and solar output can jump fast,
    # so we assume they don't get a chance to react. This is the usual worst case.
    dss.Text.Command("set controlmode=off")
    dss.Solution.Solve()
    return get_loadings()  # loading before any solar, used as the starting point


def check_voltages():
    """Return (worst high, worst low) per unit voltage across customer nodes."""
    names = dss.Circuit.AllNodeNames()
    vals = dss.Circuit.AllBusMagPu()
    keep = [v for n, v in zip(names, vals) if not n.startswith(SKIP_PREFIXES)]
    return max(keep), min(keep)


def get_loadings():
    """Return {element name: percent of its rating} for lines and transformers."""
    loadings = {}
    flag = dss.PDElements.First()
    while flag:
        name = dss.CktElement.Name()
        norm = dss.CktElement.NormalAmps()
        if norm > 0 and not name.lower().startswith("capacitor"):
            n_cond = dss.CktElement.NumConductors()
            mags = dss.CktElement.CurrentsMagAng()[0::2]  # every other value is a magnitude
            amps = max(mags[:n_cond])  # currents at terminal 1
            loadings[name] = amps / norm * 100
        flag = dss.PDElements.Next()
    return loadings


def check_overload(base_loadings):
    """Find elements solar pushed over 100%, or made worse if they started over 100%.

    Returns (element name, percent) for the worst one, or (None, 0) if all fine.
    """
    worst_name = None
    worst_pct = 0.0
    for name, pct in get_loadings().items():
        limit = max(100.0, base_loadings[name])
        if pct > limit and pct > worst_pct:
            worst_name = name
            worst_pct = pct
    return worst_name, worst_pct


def hosting_capacity_at_bus(bus, load_mult):
    """Add solar at one bus in steps until a limit breaks. Return the max size that passed."""
    base_loadings = setup(load_mult)

    # Solar has to match the bus voltage. kVBase is phase to neutral, PV wants phase to phase.
    dss.Circuit.SetActiveBus(bus)
    kv_ll = dss.Bus.kVBase() * 3 ** 0.5

    dss.Text.Command(
        f"new PVSystem.pv phases=3 bus1={bus} kV={kv_ll:.4f} "
        f"kVA=1 Pmpp=1 irradiance=1 pf=1"
    )

    last_ok = 0
    reason = f"none up to {MAX_KW} kW"
    for kw in range(STEP_KW, MAX_KW + STEP_KW, STEP_KW):
        dss.Text.Command(f"PVSystem.pv.kVA={kw}")
        dss.Text.Command(f"PVSystem.pv.Pmpp={kw}")
        dss.Solution.Solve()

        if not dss.Solution.Converged():
            reason = "did not converge"
            break

        v_high, v_low = check_voltages()
        over_name, over_pct = check_overload(base_loadings)

        if v_high > V_MAX:
            reason = f"overvoltage ({v_high:.4f} pu)"
            break
        if v_low < V_MIN:
            reason = f"undervoltage ({v_low:.4f} pu)"
            break
        if over_name:
            reason = f"overload ({over_name} at {over_pct:.0f}%)"
            break

        last_ok = kw

    return last_ok, reason


def run(load_mult, label):
    rows = []
    for bus in TEST_BUSES:
        kw, reason = hosting_capacity_at_bus(bus, load_mult)
        print(f"  bus {bus}: {kw:>6,} kW   limit hit: {reason}")
        rows.append({"bus": bus, "load_case": label, "hosting_kw": kw, "limit": reason})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    RESULTS_DIR.mkdir(exist_ok=True)

    # Quick sanity check before adding any solar
    base = setup(1.0)
    v_high, v_low = check_voltages()
    print(f"Before solar: customer voltages {v_low:.4f} to {v_high:.4f} pu")
    print("Already over 100% before solar:")
    for name, pct in base.items():
        if pct > 100:
            print(f"  {name} at {pct:.0f}%")
    print()

    print("Normal load:")
    normal = run(1.0, "normal")
    print()

    print(f"Light load ({LIGHT_LOAD:.0%} of normal):")
    light = run(LIGHT_LOAD, "light")
    print()

    # Put both cases side by side
    df = pd.concat([normal, light])
    df.to_csv(RESULTS_DIR / "hosting_capacity.csv", index=False)

    compare = df.pivot(index="bus", columns="load_case", values="hosting_kw")
    compare["drop_kw"] = compare["normal"] - compare["light"]
    print("Hosting capacity (kW), normal vs light load:")
    print(compare[["normal", "light", "drop_kw"]].to_string())
    print()
    print(f"Feeder minimum: {compare['normal'].min():,} kW normal, "
          f"{compare['light'].min():,} kW light")
    print("Saved results/hosting_capacity.csv")