import netCDF4 as nc
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import RectangleSelector, TextBox, Button
import glob
import re
import os
import sys

np.set_printoptions(threshold=500)

# Parse CLI args: positional .in file, and optional --apply x_min,y_min,x_max,y_max,new_val,percent
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
            print(f"  python3 landuseEdit.py {f}")
        sys.exit(1)
    in_file = in_files[0]

#print(f"Using config file: {in_file}")

with open(in_file, 'r') as f:
    content = f.read()

# Resolve paths relative to the .in file's directory, not cwd
in_file_dir = os.path.dirname(os.path.abspath(in_file))

def resolve_path(p):
    """Resolve a path from the .in file relative to that file's directory."""
    if os.path.isabs(p):
        return p
    return os.path.normpath(os.path.join(in_file_dir, p))

# Parse domname from the .in file (format: domname = 'xxx',)
match = re.search(r"domname\s*=\s*['\"]([^'\"]+)['\"]", content)
if not match:
    raise ValueError(f"Could not find domname in {in_file}")

domname = match.group(1)
print(f"Found domname: {domname}")

# Parse dirter and dirglob for the input directories
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
    parts = line.split('=>')
    legend_dict[int(parts[0].strip())] = parts[1].strip()

landuse_data = landuse[:]

# Track all applied changes for replay command
applied_changes = []

# --- Batch/CLI mode: apply --apply args and save without GUI ---
if cli_applies:
    for spec in cli_applies:
        parts = spec.split(',')
        if len(parts) != 6:
            print(f"Invalid --apply spec (expected x_min,y_min,x_max,y_max,new_val,percent): {spec}")
            sys.exit(1)
        x_min, y_min, x_max, y_max = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
        new_val = int(parts[4])
        percent = float(parts[5])

        points = []
        for row in range(y_min, y_max + 1):
            for col in range(x_min, x_max + 1):
                if 0 <= row < landuse_data.shape[0] and 0 <= col < landuse_data.shape[1]:
                    points.append((row, col))

        num_to_change = int(len(points) * percent / 100)
        chosen = np.random.choice(len(points), num_to_change, replace=False)
        for idx in chosen:
            row, col = points[idx]
            landuse_data[row, col] = new_val

        applied_changes.append((x_min, y_min, x_max, y_max, new_val, percent))
        print(f"Applied: region ({x_min},{y_min})-({x_max},{y_max}), "
              f"landuse={new_val} ({legend_dict.get(new_val,'?')}), {percent}% -> {num_to_change} points")

    landuse[:] = landuse_data
    data.sync()
    print(f"\nSaved changes to {filename}")
    sys.exit(0)

# --- Interactive GUI mode ---
fig, (ax, ax_legend) = plt.subplots(1, 2, figsize=(14, 8), gridspec_kw={'width_ratios': [3, 1]})
plt.subplots_adjust(bottom=0.2, right=0.95, left=0.05)
im = ax.imshow(landuse_data, cmap='gray', origin='lower')
plt.colorbar(im, ax=ax)
ax.set_title('Landuse Data')

# Create legend panel
ax_legend.axis('off')
ax_legend.set_title('Landuse Legend', fontsize=12, fontweight='bold')
legend_lines = []
for k in sorted(legend_dict.keys()):
    legend_lines.append(f"{k:3d} → {legend_dict[k]}")
legend_str = '\n'.join(legend_lines)
ax_legend.text(0.05, 0.95, legend_str, transform=ax_legend.transAxes,
               fontsize=9, verticalalignment='top', fontfamily='monospace',
               bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

def format_coord(x, y):
    col, row = int(round(x)), int(round(y))
    if 0 <= row < landuse_data.shape[0] and 0 <= col < landuse_data.shape[1]:
        val = int(landuse_data[row, col])
        name = legend_dict.get(val, 'Unknown')
        return f'x={x:.0f}, y={y:.0f}, {name}, {val}'
    return f'x={x:.0f}, y={y:.0f}'

ax.format_coord = format_coord

selected_points = []
current_region = [None]  # [x_min, y_min, x_max, y_max]

def on_select(eclick, erelease):
    x1, y1 = int(round(eclick.xdata)), int(round(eclick.ydata))
    x2, y2 = int(round(erelease.xdata)), int(round(erelease.ydata))

    x_min, x_max = min(x1, x2), max(x1, x2)
    y_min, y_max = min(y1, y2), max(y1, y2)

    current_region[0] = (x_min, y_min, x_max, y_max)
    selected_points.clear()
    print(f"\nSelected region: ({x_min}, {y_min}) to ({x_max}, {y_max})")
    for row in range(y_min, y_max + 1):
        for col in range(x_min, x_max + 1):
            if 0 <= row < landuse_data.shape[0] and 0 <= col < landuse_data.shape[1]:
                val = int(landuse_data[row, col])
                selected_points.append((row, col, val))

    print(f"Total points: {len(selected_points)}")
    values = set(p[2] for p in selected_points)
    print("Landuse types in selection:")
    for v in sorted(values):
        count = sum(1 for p in selected_points if p[2] == v)
        print(f"  {v} - {legend_dict.get(v, 'Unknown')}: {count} points")

selector = RectangleSelector(ax, on_select, useblit=True, button=[1],
                             interactive=True)

## Input fields for modifying landuse
ax_landuse = plt.axes([0.15, 0.12, 0.2, 0.05])
ax_percent = plt.axes([0.15, 0.05, 0.2, 0.05])
ax_apply = plt.axes([0.45, 0.05, 0.12, 0.05])
ax_save = plt.axes([0.6, 0.05, 0.12, 0.05])

textbox_landuse = TextBox(ax_landuse, 'New Landuse: ', initial='')
textbox_percent = TextBox(ax_percent, 'Percent: ', initial='100')
btn_apply = Button(ax_apply, 'Apply')
btn_save = Button(ax_save, 'Save')

def apply_changes(event):
    global landuse_data
    if not selected_points:
        print("No points selected!")
        return

    try:
        new_val = int(textbox_landuse.text)
        percent = float(textbox_percent.text)
    except ValueError:
        print("Invalid input. Enter a number for landuse and percent.")
        return

    if new_val not in legend_dict:
        print(f"Invalid landuse value. Choose from: {list(legend_dict.keys())}")
        return

    if not 0 <= percent <= 100:
        print("Percent must be between 0 and 100.")
        return

    num_to_change = int(len(selected_points) * percent / 100)
    points_to_change = np.random.choice(len(selected_points), num_to_change, replace=False)

    for idx in points_to_change:
        row, col, _ = selected_points[idx]
        landuse_data[row, col] = new_val

    im.set_data(landuse_data)
    fig.canvas.draw_idle()

    x_min, y_min, x_max, y_max = current_region[0]
    applied_changes.append((x_min, y_min, x_max, y_max, new_val, percent))
    print(f"\nChanged {num_to_change} points to {new_val} - {legend_dict[new_val]}")

btn_apply.on_clicked(apply_changes)

def save_changes(event):
    landuse[:] = landuse_data
    data.sync()
    print(f"\nSaved changes to {filename}")

    if applied_changes:
        apply_args = ' '.join(
            f'--apply {x_min},{y_min},{x_max},{y_max},{new_val},{percent:g}'
            for x_min, y_min, x_max, y_max, new_val, percent in applied_changes
        )
        script = os.path.basename(sys.argv[0])
        print(f"\n--- Replay command ---")
        print(f"python3 {script} <other_file.in> {apply_args}")
        print(f"----------------------")

btn_save.on_clicked(save_changes)

# print("\nLanduse legend:")
# for k, v in legend_dict.items():
#     print(f"  {k} - {v}")

plt.show()
