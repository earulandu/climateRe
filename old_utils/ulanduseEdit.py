import netCDF4 as nc
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.widgets import RectangleSelector, TextBox, Button
import glob
import re
import os
import sys

np.set_printoptions(threshold=500)

# ──────────────────────────────────────────────────────────────────────────────
# CLI argument parsing
# ──────────────────────────────────────────────────────────────────────────────
in_file = None
cli_applies = []

args = sys.argv[1:]
i = 0
while i < len(args):
    if args[i] == '--apply' and i + 1 < len(args):
        cli_applies.append(args[i + 1])
        i += 2
    elif not args[i].startswith('--'):
        in_file = args[i]
        i += 1
    else:
        i += 1

# Find .in file
if in_file:
    if not os.path.exists(in_file):
        raise FileNotFoundError(f"Specified file not found: {in_file}")
else:
    in_files = glob.glob('*.in')
    if not in_files:
        raise FileNotFoundError("No .in file found in the current directory")
    if len(in_files) > 1:
        print("Multiple .in files found. Specify one as an argument:")
        for f in in_files:
            print(f"  python3 ulanduseEdit.py {f}")
        sys.exit(1)
    in_file = in_files[0]

with open(in_file, 'r') as f:
    content = f.read()

in_file_dir = os.path.dirname(os.path.abspath(in_file))


def resolve_path(p, base_dir=None):
    if base_dir is None:
        base_dir = in_file_dir
    if os.path.isabs(p):
        return p
    return os.path.normpath(os.path.join(base_dir, p))


# Parse domname
match = re.search(r"domname\s*=\s*['\"]([^'\"]+)['\"]", content)
if not match:
    raise ValueError(f"Could not find domname in {in_file}")
domname = match.group(1)
print(f"Found domname: {domname}")

# Parse dirter and dirglob
dirter_match = re.search(r"dirter\s*=\s*['\"]([^'\"]+)['\"]", content)
dirter = resolve_path(dirter_match.group(1) if dirter_match else './input')
print(f"Using terrain directory (dirter): {dirter}")

dirglob_match = re.search(r"dirglob\s*=\s*['\"]([^'\"]+)['\"]", content)
dirglob = resolve_path(dirglob_match.group(1) if dirglob_match else dirter)
print(f"Using global directory (dirglob): {dirglob}")

filename = os.path.join(dirter, f'{domname}_DOMAIN000.nc')
print(f"Opening: {filename}")

data = nc.Dataset(filename, 'r+')
landuse = data['landuse']

legend_text = landuse.getncattr('legend')
legend_dict = {}
for line in legend_text.strip().split('\n'):
    line = line.strip()
    if not line:
        continue
    parts = line.split('=>')
    if len(parts) < 2:
        continue
    try:
        legend_dict[int(parts[0].strip())] = parts[1].strip()
    except (ValueError, IndexError):
        continue
if not legend_dict:
    raise ValueError(f"Could not parse any legend entries from {filename}")

landuse_data = landuse[:]

# applied_changes tracks single-file edits (for replay command)
# bulk_applied_changes tracks changes staged via Apply All (for Save All)
applied_changes = []
bulk_applied_changes = []

# ──────────────────────────────────────────────────────────────────────────────
# Ensemble member scanning & validation
# ──────────────────────────────────────────────────────────────────────────────
def scan_ensemble_members():
    """
    Scan cwd for .in files created by setupEnsemble.py (filenames starting
    with a digit).  For each, parse domname/dirter and verify the domain NC
    file exists inside the associated input folder.
    """
    members = []
    for f in sorted(glob.glob(os.path.join(os.getcwd(), '*.in'))):
        fname = os.path.basename(f)
        if not fname[0].isdigit():
            continue
        try:
            with open(f, 'r') as fp:
                c = fp.read()
        except Exception:
            continue

        m = re.search(r"domname\s*=\s*['\"]([^'\"]+)['\"]", c)
        if not m:
            continue
        dom = m.group(1)

        fdir = os.path.dirname(os.path.abspath(f))
        dt_m = re.search(r"dirter\s*=\s*['\"]([^'\"]+)['\"]", c)
        dt = resolve_path(dt_m.group(1) if dt_m else './input', fdir)

        nc_file = os.path.join(dt, f'{dom}_DOMAIN000.nc')
        num_m = re.match(r'^(\d+)', fname)

        members.append({
            'num':       int(num_m.group(1)) if num_m else 0,
            'in_file':   f,
            'in_fname':  fname,
            'domname':   dom,
            'dirter':    dt,
            'nc_file':   nc_file,
            'nc_exists': os.path.isfile(nc_file),
        })

    members.sort(key=lambda x: x['num'])
    return members


ensemble_members = scan_ensemble_members()
all_valid = bool(ensemble_members) and all(m['nc_exists'] for m in ensemble_members)

if ensemble_members:
    print(f"\nDetected {len(ensemble_members)} ensemble member(s):")
    for m in ensemble_members:
        tag = "OK     " if m['nc_exists'] else "MISSING"
        print(f"  [{tag}] {m['in_fname']}  ->  {m['nc_file']}")
    if not all_valid:
        missing = [m for m in ensemble_members if not m['nc_exists']]
        print(f"\n*** WARNING: {len(missing)} domain file(s) missing — "
              f"Apply All / Save All will be disabled ***")
        for m in missing:
            print(f"  Missing: {m['nc_file']}")
else:
    print("\nNo ensemble members detected. Bulk editing disabled.")

# ──────────────────────────────────────────────────────────────────────────────
# Shared helper  (defined before CLI block so both modes can use it)
# ──────────────────────────────────────────────────────────────────────────────
def _apply_region_to_array(lu_arr, x_min, y_min, x_max, y_max, new_val, percent):
    """
    Randomly change `percent`% of the pixels in the rectangle
    (x_min,y_min)-(x_max,y_max) of lu_arr to new_val.
    Randomisation is independent per call — each ensemble member gets its
    own unique set of perturbed pixels.
    Returns the number of pixels changed.
    Uses numpy flat indexing — no Python pixel loops.
    """
    r0 = max(y_min, 0);  r1 = min(y_max, lu_arr.shape[0] - 1)
    c0 = max(x_min, 0);  c1 = min(x_max, lu_arr.shape[1] - 1)
    if r0 > r1 or c0 > c1:
        return 0
    n_rows = r1 - r0 + 1
    n_cols = c1 - c0 + 1
    n_pts  = n_rows * n_cols
    n = int(n_pts * percent / 100)
    if n == 0:
        return 0
    flat_idx = np.random.choice(n_pts, n, replace=False)
    lu_arr[r0 + flat_idx // n_cols, c0 + flat_idx % n_cols] = new_val
    return n


# ──────────────────────────────────────────────────────────────────────────────
# CLI / batch mode
# ──────────────────────────────────────────────────────────────────────────────
if cli_applies:
    for spec in cli_applies:
        parts = spec.split(',')
        if len(parts) != 6:
            print(f"Invalid --apply spec (expected x_min,y_min,x_max,y_max,new_val,percent): {spec}")
            sys.exit(1)
        try:
            x_min, y_min, x_max, y_max = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
            new_val = int(parts[4])
            percent = float(parts[5])
        except ValueError:
            print(f"Invalid --apply values (all fields must be numeric): {spec}")
            sys.exit(1)
        if not 0 <= percent <= 100:
            print(f"Invalid percent {percent} — must be between 0 and 100.")
            sys.exit(1)
        if new_val not in legend_dict:
            print(f"Invalid landuse value {new_val}. Valid: {sorted(legend_dict.keys())}")
            sys.exit(1)

        num_to_change = _apply_region_to_array(
            landuse_data, x_min, y_min, x_max, y_max, new_val, percent
        )

        applied_changes.append((x_min, y_min, x_max, y_max, new_val, percent))
        print(f"Applied: region ({x_min},{y_min})-({x_max},{y_max}), "
              f"landuse={new_val} ({legend_dict.get(new_val, '?')}), "
              f"{percent}% -> {num_to_change} points")

    landuse[:] = landuse_data
    data.sync()
    print(f"\nSaved changes to {filename}")
    sys.exit(0)


def _validate_inputs():
    """Parse and validate textbox inputs. Returns (new_val, percent)."""
    try:
        new_val = int(textbox_landuse.text)
        percent = float(textbox_percent.text)
    except ValueError:
        raise ValueError("Invalid input: enter an integer for landuse and a number for percent.")
    if new_val not in legend_dict:
        raise ValueError(f"Invalid landuse value {new_val}. Valid: {sorted(legend_dict.keys())}")
    if not 0 <= percent <= 100:
        raise ValueError("Percent must be between 0 and 100.")
    return new_val, percent


# ──────────────────────────────────────────────────────────────────────────────
# Figure & layout  (3 columns: file panel | main plot | landuse legend)
# ──────────────────────────────────────────────────────────────────────────────
fig = plt.figure(figsize=(19, 9))
gs = gridspec.GridSpec(
    1, 3, figure=fig,
    width_ratios=[1.3, 3.5, 1.0],
    left=0.02, right=0.98,
    bottom=0.22, top=0.93,
    wspace=0.28,
)
ax_files        = fig.add_subplot(gs[0])   # File legend panel (LEFT)
ax              = fig.add_subplot(gs[1])   # Main landuse plot (CENTRE)
ax_legend_panel = fig.add_subplot(gs[2])   # Landuse legend    (RIGHT)

# ── File legend panel ─────────────────────────────────────────────────────────
ax_files.set_facecolor('#f0f4f8')
ax_files.set_xticks([])
ax_files.set_yticks([])
for spine in ax_files.spines.values():
    spine.set_edgecolor('#b0bec8')
    spine.set_linewidth(0.9)
ax_files.set_title('Ensemble Files', fontsize=10, fontweight='bold',
                   color='#2c3e50', pad=6)

if not ensemble_members:
    ax_files.text(
        0.5, 0.55,
        "No ensemble members\ndetected.\n\nRun setupEnsemble.py\nfirst to create\nensemble members.",
        transform=ax_files.transAxes,
        fontsize=9, ha='center', va='center',
        fontfamily='monospace', color='#888888', style='italic',
    )
else:
    # Dynamic line height based on member count
    lines_per_member = 4   # in_file line + dirter line + nc_file line + gap
    line_h = min(0.038, 0.90 / (len(ensemble_members) * lines_per_member + 1))
    y = 0.96

    for member in ensemble_members:
        is_current = os.path.abspath(member['in_file']) == os.path.abspath(in_file)
        prefix = '►' if is_current else ' '
        weight = 'bold' if is_current else 'normal'
        name_color = '#1a3a6e' if is_current else '#2c3e50'

        # .in filename
        ax_files.text(
            0.03, y, f"{prefix} {member['in_fname']}",
            transform=ax_files.transAxes,
            fontsize=7.5, va='top', fontfamily='monospace',
            fontweight=weight, color=name_color,
        )
        y -= line_h

        # dirter folder
        dname = os.path.basename(member['dirter'].rstrip(os.sep))
        ax_files.text(
            0.03, y, f"   └─ {dname}/",
            transform=ax_files.transAxes,
            fontsize=7, va='top', fontfamily='monospace', color='#606060',
        )
        y -= line_h

        # NC domain file (green = present, red = missing)
        nc_fname  = os.path.basename(member['nc_file'])
        nc_color  = '#1a7a1a' if member['nc_exists'] else '#cc2200'
        nc_mark   = '✓' if member['nc_exists'] else '✗'
        ax_files.text(
            0.03, y, f"      └─ {nc_fname} {nc_mark}",
            transform=ax_files.transAxes,
            fontsize=7, va='top', fontfamily='monospace', color=nc_color,
        )
        y -= line_h * 1.5   # extra gap between members

    # Warning banner when any domain file is missing
    if not all_valid:
        missing_count = sum(1 for m in ensemble_members if not m['nc_exists'])
        ax_files.text(
            0.03, max(y - 0.01, 0.02),
            f"⚠  {missing_count} domain file(s) missing\n"
            f"   Apply All / Save All\n   are disabled.",
            transform=ax_files.transAxes,
            fontsize=7.5, va='top', fontfamily='monospace',
            color='#cc2200', fontweight='bold',
        )

# ── Main landuse plot ─────────────────────────────────────────────────────────
im = ax.imshow(landuse_data, cmap='gray', origin='lower')
plt.colorbar(im, ax=ax)
ax.set_title(
    f'Landuse Data  ·  {os.path.basename(in_file)}',
    fontsize=12, fontweight='bold', color='#2c3e50', pad=8,
)


def format_coord(x, y):
    col, row = int(round(x)), int(round(y))
    if 0 <= row < landuse_data.shape[0] and 0 <= col < landuse_data.shape[1]:
        val = int(landuse_data[row, col])
        name = legend_dict.get(val, 'Unknown')
        return f'x={x:.0f}, y={y:.0f},  {name} ({val})'
    return f'x={x:.0f}, y={y:.0f}'


ax.format_coord = format_coord

# ── Landuse legend panel ──────────────────────────────────────────────────────
ax_legend_panel.axis('off')
ax_legend_panel.set_title('Landuse Legend', fontsize=10, fontweight='bold', pad=6)
legend_lines = [f"{k:3d} → {legend_dict[k]}" for k in sorted(legend_dict.keys())]
ax_legend_panel.text(
    0.05, 0.97, '\n'.join(legend_lines),
    transform=ax_legend_panel.transAxes,
    fontsize=8, verticalalignment='top', fontfamily='monospace',
    bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5),
)

# ──────────────────────────────────────────────────────────────────────────────
# Rectangle selection
# ──────────────────────────────────────────────────────────────────────────────
current_region = [None]   # holds (x_min, y_min, x_max, y_max)


def on_select(eclick, erelease):
    # xdata/ydata are None when the click lands outside the axes
    if None in (eclick.xdata, eclick.ydata, erelease.xdata, erelease.ydata):
        return
    x1, y1 = int(round(eclick.xdata)),   int(round(eclick.ydata))
    x2, y2 = int(round(erelease.xdata)), int(round(erelease.ydata))

    x_min, x_max = min(x1, x2), max(x1, x2)
    y_min, y_max = min(y1, y2), max(y1, y2)

    current_region[0] = (x_min, y_min, x_max, y_max)
    print(f"\nSelected region: ({x_min}, {y_min}) to ({x_max}, {y_max})")

    # Clamp to data bounds and slice — no Python pixel loops
    r0 = max(y_min, 0);  r1 = min(y_max, landuse_data.shape[0] - 1)
    c0 = max(x_min, 0);  c1 = min(x_max, landuse_data.shape[1] - 1)
    if r0 > r1 or c0 > c1:
        print("Selection outside data bounds.")
        return

    sub = landuse_data[r0:r1 + 1, c0:c1 + 1]
    print(f"Total points: {sub.size}")
    print("Landuse types in selection:")
    vals, counts = np.unique(sub, return_counts=True)
    for v, cnt in zip(vals, counts):
        print(f"  {int(v)} - {legend_dict.get(int(v), 'Unknown')}: {cnt} points")


selector = RectangleSelector(ax, on_select, useblit=True, button=[1], interactive=True)

# ──────────────────────────────────────────────────────────────────────────────
# Bottom controls
#
#  Row 1 (y≈0.13):  [New Landuse: ______]  [Percent: ______]
#  Row 2 (y≈0.05):  [Apply]  [Save]          [Apply All]  [Save All]
#
# Apply All / Save All are blue/green when enabled, grey when disabled.
# ──────────────────────────────────────────────────────────────────────────────
ax_landuse_tb    = fig.add_axes([0.32, 0.13, 0.10, 0.05])
ax_percent_tb    = fig.add_axes([0.55, 0.13, 0.08, 0.05])

ax_apply_btn     = fig.add_axes([0.28, 0.05, 0.09, 0.05])
ax_save_btn      = fig.add_axes([0.39, 0.05, 0.09, 0.05])
ax_apply_all_btn = fig.add_axes([0.53, 0.05, 0.12, 0.05])
ax_save_all_btn  = fig.add_axes([0.67, 0.05, 0.12, 0.05])

textbox_landuse = TextBox(ax_landuse_tb, 'New Landuse: ', initial='')
textbox_percent = TextBox(ax_percent_tb, 'Percent: ',     initial='100')

btn_apply = Button(ax_apply_btn, 'Apply')
btn_save  = Button(ax_save_btn,  'Save')

_bulk_color_on  = '#cce5ff'
_bulk_hover_on  = '#99caff'
_bulk_color_off = '0.82'

btn_apply_all = Button(
    ax_apply_all_btn, 'Apply All',
    color      = _bulk_color_on  if all_valid else _bulk_color_off,
    hovercolor = _bulk_hover_on  if all_valid else _bulk_color_off,
)
btn_save_all = Button(
    ax_save_all_btn, 'Save All',
    color      = '#ccf5cc'       if all_valid else _bulk_color_off,
    hovercolor = '#99ea99'       if all_valid else _bulk_color_off,
)

# ──────────────────────────────────────────────────────────────────────────────
# Button callbacks
# ──────────────────────────────────────────────────────────────────────────────

def apply_changes(event):
    """Apply change to the currently displayed file (in memory, not yet saved)."""
    global landuse_data
    if current_region[0] is None:
        print("[Apply] No region selected.")
        return
    try:
        new_val, percent = _validate_inputs()
    except ValueError as e:
        print(f"[Apply] {e}")
        return

    x_min, y_min, x_max, y_max = current_region[0]
    n = _apply_region_to_array(landuse_data, x_min, y_min, x_max, y_max, new_val, percent)
    im.set_data(landuse_data)
    fig.canvas.draw_idle()

    applied_changes.append((x_min, y_min, x_max, y_max, new_val, percent))
    print(f"\n[Apply] Changed {n} pixel(s) to {new_val} ({legend_dict[new_val]}), "
          f"region ({x_min},{y_min})-({x_max},{y_max}), {percent}%")


btn_apply.on_clicked(apply_changes)


def save_changes(event):
    """Save in-memory edits of the current file to disk."""
    try:
        landuse[:] = landuse_data
        data.sync()
    except Exception as e:
        print(f"\n[Save] ERROR — could not write to {filename}: {e}")
        return
    print(f"\n[Save] Saved to {filename}")

    if applied_changes:
        args_str = ' '.join(
            f'--apply {x},{y},{x2},{y2},{v},{p:g}'
            for x, y, x2, y2, v, p in applied_changes
        )
        script = os.path.basename(sys.argv[0])
        print(f"\n--- Replay command ---")
        print(f"python3 {script} <other_file.in> {args_str}")
        print(f"----------------------")


btn_save.on_clicked(save_changes)


def apply_all_changes(event):
    """
    Stage a bulk change for all ensemble members:
      - Applies (independently randomised) change to the current display.
      - Records the parameters in bulk_applied_changes.
      - The actual write to other members happens on Save All.
    """
    global landuse_data

    if not all_valid:
        if not ensemble_members:
            print("[Apply All] Disabled — no ensemble members detected.")
        else:
            missing = [m for m in ensemble_members if not m['nc_exists']]
            print("[Apply All] Disabled — missing domain file(s):")
            for m in missing:
                print(f"  {m['nc_file']}")
        return

    if current_region[0] is None:
        print("[Apply All] No region selected.")
        return

    try:
        new_val, percent = _validate_inputs()
    except ValueError as e:
        print(f"[Apply All] {e}")
        return

    x_min, y_min, x_max, y_max = current_region[0]

    # Apply to current file display (independent randomisation)
    n = _apply_region_to_array(landuse_data, x_min, y_min, x_max, y_max, new_val, percent)
    im.set_data(landuse_data)
    fig.canvas.draw_idle()

    applied_changes.append((x_min, y_min, x_max, y_max, new_val, percent))
    bulk_applied_changes.append((x_min, y_min, x_max, y_max, new_val, percent))

    print(f"\n[Apply All] Staged change for all {len(ensemble_members)} ensemble member(s):")
    print(f"  Region:        ({x_min},{y_min}) -> ({x_max},{y_max})")
    print(f"  Landuse:       {new_val} ({legend_dict[new_val]}),  {percent}%")
    print(f"  Current file:  {n} pixel(s) changed (independently randomised)")
    print(f"  Other members: {len(ensemble_members) - 1} member(s) staged — "
          f"click 'Save All' to commit with independent randomisation.")


btn_apply_all.on_clicked(apply_all_changes)


def save_all_changes(event):
    """
    Commit all bulk-staged changes to every ensemble member:
      - Saves the current file to disk.
      - For every other ensemble member: opens its domain NC, applies each
        staged change with *independently* randomised pixel selection, then
        saves and closes the file.
    Each member therefore receives the same region / percentage / landuse class
    but a unique random perturbation pattern.
    """
    if not all_valid:
        if not ensemble_members:
            print("[Save All] Disabled — no ensemble members detected.")
        else:
            missing = [m for m in ensemble_members if not m['nc_exists']]
            print("[Save All] Disabled — missing domain file(s):")
            for m in missing:
                print(f"  {m['nc_file']}")
        return

    if not bulk_applied_changes:
        print("[Save All] No bulk changes staged. Use 'Apply All' first.")
        return

    # Save the currently displayed file
    try:
        landuse[:] = landuse_data
        data.sync()
    except Exception as e:
        print(f"\n[Save All] ERROR — could not write current file {os.path.basename(filename)}: {e}")
        return
    print(f"\n[Save All] Saved current file: {os.path.basename(filename)}")

    current_abs = os.path.abspath(filename)
    errors = 0

    for member in ensemble_members:
        member_nc_abs = os.path.abspath(member['nc_file'])

        if member_nc_abs == current_abs:
            # Already saved above
            print(f"[Save All] {member['in_fname']}: ✓ (current file, already saved)")
            continue

        m_data = None
        try:
            m_data = nc.Dataset(member['nc_file'], 'r+')
            m_lu        = m_data['landuse']
            m_lu_data   = m_lu[:]

            for (x_min, y_min, x_max, y_max, new_val, percent) in bulk_applied_changes:
                n = _apply_region_to_array(
                    m_lu_data, x_min, y_min, x_max, y_max, new_val, percent
                )
                print(f"[Save All] {member['in_fname']}: "
                      f"{n} pixel(s) -> landuse={new_val} ({legend_dict.get(new_val, '?')}), "
                      f"region ({x_min},{y_min})-({x_max},{y_max}), {percent}%")

            m_lu[:] = m_lu_data
            m_data.sync()
            m_data.close()
            print(f"[Save All] {member['in_fname']}: ✓ saved successfully  "
                  f"({member['nc_file']})")

        except Exception as e:
            print(f"[Save All] {member['in_fname']}: ✗ ERROR — {e}")
            errors += 1
            if m_data is not None:
                try:
                    m_data.close()
                except Exception:
                    pass

    if errors == 0:
        print(f"\n[Save All] Complete — all {len(ensemble_members)} member(s) "
              f"saved successfully.")
    else:
        print(f"\n[Save All] Complete with {errors} error(s).")


btn_save_all.on_clicked(save_all_changes)

plt.show()
data.close()  # release the NC file handle when the window is closed
