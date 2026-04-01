"""
plot_ribbon_timeseries.py
=========================
Generate three ribbon time series plots from RegCM5 climate model output
for the Upper Mississippi Basin, 2011 (May 2 – July 29).

Variables:
  1. huss — near-surface specific humidity  (kg/kg → g/kg)
  2. hfls — surface upward latent heat flux  (W/m²)
  3. tas  — near-surface air temperature    (K → °F)

Three cropland scenarios:
  - Base (control)          : full_miss_11_base.nc
  - 15% cropland reduction  : full_miss_11_15.nc
  - 25% cropland reduction  : full_miss_11_25.nc
"""

import numpy as np
import xarray as xr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from scipy.stats import pearsonr

# ---------------------------------------------------------------------------
# Paths – adjust if files live elsewhere
# ---------------------------------------------------------------------------
FILES = {
    "base": "full_iowa_21_base.nc",
    "15pct": "full_iowa_21_15.nc",
    "25pct": "full_iowa_21_25.nc",
}

SCENARIO_LABELS = {
    "base":  "Base (control)",
    "15pct": "15% cropland reduction",
    "25pct": "25% cropland reduction",
}

COLORS = {
    "base":  "#2166AC",   # blue
    "15pct": "#B2182B",   # red
    "25pct": "#1B7837",   # green
}

PLOT_ORDER = ["25pct", "15pct", "base"]   # back → front

N_STEPS   = 704          # 3-hourly timesteps
STEPS_PER_DAY = 8
SMOOTH_WINDOW = 16       # 16 steps = 2 days
DPI = 300


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def smooth(arr, window=SMOOTH_WINDOW):
    """Running mean with edge fill to avoid boundary artefacts."""
    kernel = np.ones(window) / window
    s = np.convolve(arr, kernel, mode="same")
    s[:window]  = arr[:window].mean()
    s[-window:] = arr[-window:].mean()
    return s


def spatial_stats(data3d, mask):
    """
    Compute per-timestep spatial mean and std over land points.

    Parameters
    ----------
    data3d : ndarray, shape (time, iy, jx)
    mask   : ndarray, shape (iy, jx), 1 = land

    Returns
    -------
    mean, std : ndarrays of length time
    """
    nt = data3d.shape[0]
    mean = np.empty(nt)
    std  = np.empty(nt)
    for t in range(nt):
        slab = np.where(mask == 2, data3d[t], np.nan)
        mean[t] = np.nanmean(slab)
        std[t]  = np.nanstd(slab)
    return mean, std


def load_variable(nc_path, varname):
    """
    Load *varname* from *nc_path*, squeeze the m2 singleton if present,
    and return a (time, iy, jx) numpy array.
    """
    ds = xr.open_dataset(nc_path)
    da = ds[varname]

    if "m2" in da.dims:
        da = da.isel(m2=0)

    return da.values   # shape (time, iy, jx)


def heat_index_F(T_F, RH):
    """
    NWS Rothfusz regression heat index (°F).

    Parameters
    ----------
    T_F : temperature in °F
    RH  : relative humidity in percent (0–100)

    Returns
    -------
    HI : heat index in °F
    """
    HI = (-42.379
          + 2.04901523   * T_F
          + 10.14333127  * RH
          - 0.22475541   * T_F * RH
          - 6.83783e-3   * T_F**2
          - 5.481717e-2  * RH**2
          + 1.22874e-3   * T_F**2 * RH
          + 8.5282e-4    * T_F * RH**2
          - 1.99e-6      * T_F**2 * RH**2)
    return HI


def approx_RH(T_K, q_kgkg):
    """
    Approximate relative humidity from temperature (K) and specific
    humidity (kg/kg) using the August-Roche-Magnus formula.

    Returns RH in percent.
    """
    T_C = T_K - 273.15
    # Saturation vapour pressure (hPa)
    es = 6.112 * np.exp(17.67 * T_C / (T_C + 243.5))
    # Actual vapour pressure (hPa) — assuming P ≈ 1013.25 hPa
    e  = q_kgkg * 1013.25 / (0.622 + 0.378 * q_kgkg)
    RH = 100.0 * e / es
    return np.clip(RH, 0, 100)


def month_dividers(ax, days_axis):
    """Add vertical dashed lines and month labels at May/June/July."""
    max_day = days_axis[-1]

    # Day 0 = May 2.  June 1 = day 30, July 1 = day 61 (approx).
    dividers = [
        (0,   "May"),
        (30,  "June"),
        (61,  "July"),
    ]

    for i, (day, label) in enumerate(dividers):
        if day > 0:
            ax.axvline(day, color="#aaaaaa", linestyle="--",
                       linewidth=0.8, alpha=0.5, zorder=1)
        # Label: horizontally centred between this divider and the next
        next_day = dividers[i + 1][0] if i + 1 < len(dividers) else max_day
        mid = (day + next_day) / 2.0
        ax.text(mid, -0.07, label,
                ha="center", va="top", fontsize=10, color="#555555",
                transform=ax.get_xaxis_transform())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # ------------------------------------------------------------------
    # 0. Load land mask from the base file (shared across scenarios)
    # ------------------------------------------------------------------
    with xr.open_dataset(FILES["base"]) as ds_base:
        mask = ds_base["mask"].values   # (iy, jx)

    # Days axis
    days = np.arange(N_STEPS) / STEPS_PER_DAY   # 0 … 87.875

    # ------------------------------------------------------------------
    # 1. Collect raw data arrays (converted to display units)
    # ------------------------------------------------------------------
    # We will store: data[varname][scenario] = (time, iy, jx) array
    raw = {}

    print("Loading data …")
    for varname, conv in [("huss", lambda x: x * 1000.0),
                           ("hfls", lambda x: x),
                           ("tas",  lambda x: (x - 273.15) * 9.0 / 5.0 + 32.0)]:
        raw[varname] = {}
        for key, path in FILES.items():
            arr = load_variable(path, varname)
            raw[varname][key] = conv(arr)
        print(f"  {varname} loaded.")

    # ------------------------------------------------------------------
    # 2. Compute per-timestep spatial stats + smooth for each plot
    # ------------------------------------------------------------------
    # stats[varname][scenario] = {"mean": ..., "std": ...}
    stats = {}
    for varname in raw:
        stats[varname] = {}
        for key in FILES:
            mn, sd = spatial_stats(raw[varname][key], mask)
            stats[varname][key] = {
                "mean": smooth(mn),
                "std":  smooth(sd),
            }

    # ------------------------------------------------------------------
    # 3. Draw the three plots
    # ------------------------------------------------------------------
    plot_specs = [
        {
            "varname":   "huss",
            "ylabel":    "Specific humidity (g/kg)",
            "title":     "Near-surface specific humidity — Iowa Region, 2021",
            "savename":  "fig1_huss_ribbon.png",
        },
        {
            "varname":   "hfls",
            "ylabel":    "Latent heat flux (W/m²)",
            "title":     "Surface latent heat flux — Iowa Region, 2021",
            "savename":  "fig2_hfls_ribbon.png",
        },
        {
            "varname":   "tas",
            "ylabel":    "Temperature (°F)",
            "title":     "Near-surface temperature — Iowa Region, 2021",
            "savename":  "fig3_tas_ribbon_F.png",
        },
    ]

    for spec in plot_specs:
        vname = spec["varname"]
        fig, ax = plt.subplots(figsize=(11, 5), facecolor="white")
        ax.set_facecolor("white")

        for key in PLOT_ORDER:
            mn  = stats[vname][key]["mean"]
            sd  = stats[vname][key]["std"]
            col = COLORS[key]

            ax.fill_between(days, mn - sd, mn + sd,
                            color=col, alpha=0.15, linewidth=0)
            ax.plot(days, mn,
                    color=col, linewidth=2, label=SCENARIO_LABELS[key])

        ax.set_xlim(0, days[-1])
        ax.set_xlabel("Days since May 2, 2021", fontsize=12)
        ax.set_ylabel(spec["ylabel"], fontsize=12)
        ax.set_title(spec["title"], fontsize=13, fontweight="bold")
        ax.grid(alpha=0.2)

        # Force a draw so get_ylim() is populated before adding labels
        fig.canvas.draw()
        month_dividers(ax, days)

        legend_handles = [
            mpatches.Patch(color=COLORS[k], label=SCENARIO_LABELS[k])
            for k in ["base", "15pct", "25pct"]
        ]
        ax.legend(handles=legend_handles,
                  loc="best", framealpha=0.9, fontsize=10)

        fig.tight_layout()
        fig.savefig(spec["savename"], dpi=DPI, bbox_inches="tight")
        plt.close(fig)
        print(f"Saved {spec['savename']}")

    # ------------------------------------------------------------------
    # 4. Summary statistics
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("SUMMARY STATISTICS")
    print("=" * 70)

    for varname, unit in [("huss", "g/kg"), ("hfls", "W/m²"), ("tas", "°F")]:
        print(f"\n--- {varname.upper()} ({unit}) ---")

        # Full-period domain-averaged mean: average the smoothed time series
        base_ts = stats[varname]["base"]["mean"]
        base_mean = base_ts.mean()
        base_temporal_std = base_ts.std()

        for key in ["base", "15pct", "25pct"]:
            scen_mean = stats[varname][key]["mean"].mean()
            diff      = scen_mean - base_mean
            snr       = abs(diff) / base_temporal_std if base_temporal_std > 0 else np.nan
            tag       = f"  ({diff:+.4f}, SNR={snr:.2f})" if key != "base" else ""
            print(f"  {SCENARIO_LABELS[key]:<30s}: {scen_mean:.4f} {unit}{tag}")

    # ------------------------------------------------------------------
    # 5. Heat index in °F
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("HEAT INDEX ANALYSIS (NWS Rothfusz regression)")
    print("=" * 70)

    hi_results = {}
    for key in FILES:
        T_K_3d = load_variable(FILES[key], "tas")    # (time, iy, jx)  K
        q_3d   = load_variable(FILES[key], "huss")   # (time, iy, jx)  kg/kg

        # Compute HI at every timestep, then average — required because the
        # Rothfusz regression is nonlinear: mean(HI(T,RH)) ≠ HI(mean(T),mean(RH))
        T_F_3d = (T_K_3d - 273.15) * 9.0 / 5.0 + 32.0
        RH_3d  = approx_RH(T_K_3d, q_3d)            # (time, iy, jx)
        HI_3d  = heat_index_F(T_F_3d, RH_3d)        # (time, iy, jx)

        HI_field_F = np.nanmean(HI_3d, axis=0)   # °F, (iy, jx)

        # Domain average over land
        land_HI  = np.where(mask == 2, HI_field_F, np.nan)
        hi_results[key] = {
            "domain_mean": float(np.nanmean(land_HI)),
            "field":       HI_field_F,
        }

    base_HI = hi_results["base"]["domain_mean"]
    print(f"  {'Scenario':<30s}  {'Domain-avg HI (°F)':>20s}  {'Δ vs base':>12s}")
    print("  " + "-" * 66)
    for key in ["base", "15pct", "25pct"]:
        mean_HI = hi_results[key]["domain_mean"]
        delta   = mean_HI - base_HI
        tag     = f"{delta:+.3f}" if key != "base" else "—"
        print(f"  {SCENARIO_LABELS[key]:<30s}  {mean_HI:>20.3f}  {tag:>12s}")

    # ------------------------------------------------------------------
    # 6. Spatial Pearson correlation: time-mean Δhuss vs. time-mean Δhfls
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("SPATIAL CORRELATION: Δhuss vs. Δhfls (time-mean, land points)")
    print("=" * 70)

    def time_mean_land(varname, key, conv):
        arr = load_variable(FILES[key], varname)
        arr = conv(arr)
        return np.nanmean(arr, axis=0)   # (iy, jx)

    for scen in ["15pct", "25pct"]:
        huss_base  = time_mean_land("huss", "base",  lambda x: x * 1000.0)
        huss_scen  = time_mean_land("huss", scen,    lambda x: x * 1000.0)
        hfls_base  = time_mean_land("hfls", "base",  lambda x: x)
        hfls_scen  = time_mean_land("hfls", scen,    lambda x: x)

        delta_huss = (huss_scen - huss_base)[mask == 2].ravel()
        delta_hfls = (hfls_scen - hfls_base)[mask == 2].ravel()

        # Remove any NaN pairs
        valid = np.isfinite(delta_huss) & np.isfinite(delta_hfls)
        r, p  = pearsonr(delta_huss[valid], delta_hfls[valid])

        interp = "STRONG" if abs(r) > 0.7 else ("MODERATE" if abs(r) > 0.4 else "WEAK")
        print(f"  {SCENARIO_LABELS[scen]} vs. Base:")
        print(f"    r = {r:.4f}  (p = {p:.2e})  → {interp} spatial coupling")
        print(f"    {'✓ Latent heat flux driving humidity changes' if abs(r) > 0.7 else '⚠ Coupling weaker than expected'}")

    print("\nDone.\n")


if __name__ == "__main__":
    main()
