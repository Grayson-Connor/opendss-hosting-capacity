import matplotlib
matplotlib.use("Agg")  # just save the images, don't open windows
import matplotlib.pyplot as plt
import opendssdirect as dss
import pandas as pd

from hosting_capacity import RESULTS_DIR, V_MAX, V_MIN, LIGHT_LOAD, setup

df = pd.read_csv(RESULTS_DIR / "hosting_capacity.csv")
df["bus"] = df["bus"].astype(str)

# Chart 1: hosting capacity by bus, normal vs light load
compare = df.pivot(index="bus", columns="load_case", values="hosting_kw")[["normal", "light"]]
ax = compare.plot(kind="bar", figsize=(9, 5), color=["#4C72B0", "#DD8452"], width=0.75)
for container in ax.containers:
    ax.bar_label(container, fmt="{:,.0f}", fontsize=8, padding=2)
ax.set_title("Solar hosting capacity by bus, IEEE 13 bus feeder")
ax.set_xlabel("Bus")
ax.set_ylabel("Max solar before a limit is hit (kW)")
ax.legend(["Normal load", f"Light load ({LIGHT_LOAD:.0%})"])
plt.xticks(rotation=0)
plt.tight_layout()
plt.savefig(RESULTS_DIR / "hosting_capacity_by_bus.png", dpi=150)
plt.close()
print("Saved results/hosting_capacity_by_bus.png")

# Chart 2: voltage profile for the worst voltage case
# Pick the voltage limited case with the lowest hosting capacity, straight from the results
volt = df[df["limit"].str.startswith("overvoltage")]
worst = volt.loc[volt["hosting_kw"].idxmin()]
bus = worst["bus"]
kw = int(worst["hosting_kw"])
load_mult = 1.0 if worst["load_case"] == "normal" else LIGHT_LOAD
print(f"Worst voltage case: bus {bus}, {kw:,} kW, {worst['load_case']} load")


def profile(add_solar):
    """Return {phase: (distances, voltages)} from the substation outward."""
    setup(load_mult)
    # An energy meter at the start of the feeder lets OpenDSS measure distance from it
    dss.Text.Command("new energymeter.m1 element=Line.650632 terminal=1")
    if add_solar:
        dss.Circuit.SetActiveBus(bus)
        kv_ll = dss.Bus.kVBase() * 3 ** 0.5
        dss.Text.Command(
            f"new PVSystem.pv phases=3 bus1={bus} kV={kv_ll:.4f} "
            f"kVA={kw} Pmpp={kw} irradiance=1 pf=1"
        )
    dss.Solution.Solve()
    out = {}
    for ph in (1, 2, 3):
        dists = dss.Circuit.AllNodeDistancesByPhase(ph)  # in km
        volts = dss.Circuit.AllNodeVmagPUByPhase(ph)
        # Skip distance 0, that's the regulator, which we also skip in the limit check
        pairs = [(d, v) for d, v in zip(dists, volts) if d > 0]
        out[ph] = ([d for d, v in pairs], [v for d, v in pairs])
    return out


before = profile(add_solar=False)
after = profile(add_solar=True)

colors = {1: "#4C72B0", 2: "#DD8452", 3: "#55A868"}
fig, ax = plt.subplots(figsize=(9, 5))
for ph in (1, 2, 3):
    ax.scatter(*before[ph], color=colors[ph], marker="o", facecolors="none", s=40)
    ax.scatter(*after[ph], color=colors[ph], marker="o", s=40, label=f"Phase {ph}")
ax.axhline(V_MAX, color="red", linestyle="--", linewidth=1, label="Limits (0.95 and 1.05)")
ax.axhline(V_MIN, color="red", linestyle="--", linewidth=1)
ax.set_title(f"Voltage profile: {kw:,} kW of solar at bus {bus} ({worst['load_case']} load)\n"
             "hollow = no solar, filled = with solar")
ax.set_xlabel("Distance from substation (km)")
ax.set_ylabel("Voltage (per unit)")
ax.legend(loc="upper center")
plt.tight_layout()
plt.savefig(RESULTS_DIR / "voltage_profile_worst_case.png", dpi=150)
plt.close()
print("Saved results/voltage_profile_worst_case.png")