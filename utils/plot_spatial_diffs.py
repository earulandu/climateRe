"""
plot_spatial_diffs.py
=====================
Spatial difference maps (scenario − base) for RegCM5 Upper Mississippi Basin
output, 2011 (May 2 – July 29).

For each variable and scenario, produces:
  • Time-mean Δ field (scenario − base)
  • Per-gridpoint two-sided t-test stippling for significance (p < 0.05)

Variables:
  huss — near-surface specific humidity  (kg/kg → g/kg)
  hfls — surface upward latent heat flux  (W/m²)
  tas  — near-surface air temperature    (K → °F → ΔF)

Scenarios:
  15% cropland reduction  (full_miss_11_15.nc  vs full_miss_11_base.nc)
  25% cropland reduction  (full_miss_11_25.nc  vs full_miss_11_base.nc)

Output files (saved to the working directory):
  fig4_spatial_dhuss_15.png  /  fig4_spatial_dhuss_25.png
  fig5_spatial_dhfls_15.png  /  fig5_spatial_dhfls_25.png
  fig6_spatial_dtas_15.png   /  fig6_spatial_dtas_25.png
  fig7_spatial_dhi_15.png    /  fig7_spatial_dhi_25.png  (heat index)
"""

import numpy as np
import xarray as xr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from scipy.stats import ttest_ind

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
FILES = {
    "base":  "full_iowa_21_base.nc",
    "15pct": "full_iowa_21_15.nc",
    "25pct": "full_iowa_21_25.nc",
}

SCENARIO_LABELS = {
    "15pct": "15 % cropland reduction",
    "25pct": "25 % cropland reduction",
}

SCENARIO_SHORT = {"15pct": "15", "25pct": "25"}

P_THRESH  = 0.05    # significance level
DPI       = 300
STIPPLE_EVERY = 2   # subsample stipple markers to avoid over-crowding


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_variable(nc_path, varname):
    """Return (time, iy, jx) numpy array; squeezes m2 singleton if present."""
    ds = xr.open_dataset(nc_path)
    da = ds[varname]
    if "m2" in da.dims:
        da = da.isel(m2=0)
    return da.values.astype(np.float32)


def approx_RH(T_K, q_kgkg):
    """
    Approximate RH (%) from temperature (K) and specific humidity (kg/kg).
    Uses August-Roche-Magnus formula; assumes P ≈ 1013.25 hPa.
    """
    T_C = T_K - 273.15
    es  = 6.112 * np.exp(17.67 * T_C / (T_C + 243.5))
    e   = q_kgkg * 1013.25 / (0.622 + 0.378 * q_kgkg)
    return np.clip(100.0 * e / es, 0, 100)


def heat_index_F(T_F, RH):
    """NWS Rothfusz regression heat index (°F)."""
    return (-42.379
            + 2.04901523   * T_F
            + 10.14333127  * RH
            - 0.22475541   * T_F * RH
            - 6.83783e-3   * T_F**2
            - 5.481717e-2  * RH**2
            + 1.22874e-3   * T_F**2 * RH
            + 8.5282e-4    * T_F * RH**2
            - 1.99e-6      * T_F**2 * RH**2)


def ttest_field(arr_base, arr_scen):
    """
    Per-gridpoint independent two-sided t-test.

    Parameters
    ----------
    arr_base, arr_scen : (time, iy, jx)

    Returns
    -------
    p_field : (iy, jx) array of p-values
    """
    nt, ny, nx = arr_base.shape
    p_field = np.full((ny, nx), np.nan)
    for j in range(ny):
        for i in range(nx):
            b = arr_base[:, j, i]
            s = arr_scen[:, j, i]
            if np.any(np.isfinite(b)) and np.any(np.isfinite(s)):
                _, p_field[j, i] = ttest_ind(b, s, equal_var=False,
                                              nan_policy="omit")
    return p_field


def make_diverging_norm(delta, percentile=98):
    """Symmetric diverging normalisation centred on zero."""
    vmax = np.nanpercentile(np.abs(delta), percentile)
    vmax = max(vmax, 1e-6)   # guard against all-zero fields
    return mcolors.TwoSlopeNorm(vmin=-vmax, vcenter=0.0, vmax=vmax)


def add_stippling(ax, p_field, mask, sig=P_THRESH, every=STIPPLE_EVERY):
    """
    Overlay dots where p < sig AND on land (mask == 2).
    Subsamples every *every* gridpoints to avoid visual clutter.
    """
    ny, nx = p_field.shape
    sig_land = (p_field < sig) & (mask == 2)
    jj, ii = np.where(sig_land)
    # subsample
    sel = (jj % every == 0) & (ii % every == 0)
    ax.scatter(ii[sel], jj[sel], s=1.5, c="black",
               marker=".", linewidths=0, zorder=5, alpha=0.5)


def save_map(delta, p_field, mask, title, cbar_label, savename, cmap="RdBu_r"):
    """
    Draw a single spatial difference map with stippling and save it.

    Parameters
    ----------
    delta     : (iy, jx) time-mean difference field
    p_field   : (iy, jx) p-value field (or None to skip stippling)
    mask      : (iy, jx) land mask  (2 = land)
    """
    # Mask ocean
    delta_plot = np.where(mask == 2, delta, np.nan)

    norm = make_diverging_norm(delta_plot)
    fig, ax = plt.subplots(figsize=(9, 6), facecolor="white")
    ax.set_facecolor("#d0d8e4")   # light blue for ocean/outside

    im = ax.imshow(delta_plot, origin="lower", cmap=cmap,
                   norm=norm, aspect="auto", interpolation="nearest")

    if p_field is not None:
        add_stippling(ax, p_field, mask)

    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label(cbar_label, fontsize=10)

    sig_note = f"Stippling: p < {P_THRESH}"
    ax.set_title(f"{title}\n{sig_note}", fontsize=11, fontweight="bold")
    ax.set_xlabel("grid x (jx)", fontsize=9)
    ax.set_ylabel("grid y (iy)", fontsize=9)
    ax.tick_params(labelsize=8)

    fig.tight_layout()
    fig.savefig(savename, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {savename}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Load land mask
    with xr.open_dataset(FILES["base"]) as ds:
        mask = ds["mask"].values   # (iy, jx)

    # -------------------------------------------------------------------
    # Load 3-D arrays once (converted to display units)
    # -------------------------------------------------------------------
    print("Loading data …")
    data = {}
    for key, path in FILES.items():
        huss_raw = load_variable(path, "huss")          # kg/kg
        tas_raw  = load_variable(path, "tas")           # K
        hfls_raw = load_variable(path, "hfls")          # W/m²

        data[key] = {
            "huss": huss_raw * 1000.0,                          # → g/kg
            "hfls": hfls_raw,
            "tas":  (tas_raw - 273.15) * 9.0 / 5.0 + 32.0,              # → °F
            "hi":   heat_index_F(
                        (tas_raw - 273.15) * 9.0 / 5.0 + 32.0,
                        approx_RH(tas_raw, huss_raw)
                    ),                                                    # °F
        }
    print("  done.\n")

    # -------------------------------------------------------------------
    # Variable specs
    # -------------------------------------------------------------------
    var_specs = [
        {
            "key":       "huss",
            "fig_prefix": "fig4_spatial_dhuss",
            "cbar_label": "Δ specific humidity (g/kg)",
            "title_base": "Δ Specific Humidity",
            "cmap":      "BrBG",
        },
        {
            "key":       "hfls",
            "fig_prefix": "fig5_spatial_dhfls",
            "cbar_label": "Δ latent heat flux (W/m²)",
            "title_base": "Δ Latent Heat Flux",
            "cmap":      "PuOr",
        },
        {
            "key":       "tas",
            "fig_prefix": "fig6_spatial_dtas",
            "cbar_label": "Δ temperature (°F)",
            "title_base": "Δ Near-surface Temperature",
            "cmap":      "RdBu_r",
        },
        {
            "key":       "hi",
            "fig_prefix": "fig7_spatial_dhi",
            "cbar_label": "Δ heat index (°F)",
            "title_base": "Δ Heat Index (NWS Rothfusz)",
            "cmap":      "RdBu_r",
        },
    ]

    # -------------------------------------------------------------------
    # Loop: scenarios × variables
    # -------------------------------------------------------------------
    for scen in ["15pct", "25pct"]:
        short = SCENARIO_SHORT[scen]
        label = SCENARIO_LABELS[scen]
        print(f"Computing t-tests and maps for {label} …")

        for spec in var_specs:
            vkey = spec["key"]

            arr_base = data["base"][vkey]    # (time, iy, jx)
            arr_scen = data[scen][vkey]

            # Time-mean difference
            delta = np.nanmean(arr_scen, axis=0) - np.nanmean(arr_base, axis=0)

            # Per-gridpoint t-test
            print(f"    t-test for {vkey} …", end=" ", flush=True)
            p_field = ttest_field(arr_base, arr_scen)
            n_sig = int(np.sum((p_field < P_THRESH) & (mask == 2)))
            n_land = int(np.sum(mask == 2))
            print(f"{n_sig}/{n_land} land pts significant ({100*n_sig/n_land:.1f} %)")

            title = (f"{spec['title_base']} — {label}\n"
                     f"Iowa Region, 2021")
            savename = f"{spec['fig_prefix']}_{short}.png"

            save_map(delta, p_field, mask,
                     title=title,
                     cbar_label=spec["cbar_label"],
                     savename=savename,
                     cmap=spec["cmap"])

        print()

    print("Done.")


if __name__ == "__main__":
    main()
