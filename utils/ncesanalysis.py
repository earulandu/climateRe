#!/usr/bin/env python3
import os
import re
import subprocess
import sys


def main():
    parent_dir = os.path.join(os.getcwd(), '..')

    # Detect ensemble count by finding numbered output dirs
    count = 0
    while os.path.isdir(os.path.join(parent_dir, f'{count + 1}output')):
        count += 1

    if count == 0:
        print("Error: no output directories found (expected ../1output/, ../2output/, ...)")
        sys.exit(1)

    # Scan member 1's output to discover base name and dates from SRF files
    m1_output = os.path.join(parent_dir, '1output')
    srf_pattern = re.compile(r'^1(.+)_SRF\.(\d+)\.nc$')

    dates = []
    base_name = None
    for fname in sorted(os.listdir(m1_output)):
        m = srf_pattern.match(fname)
        if m:
            if base_name is None:
                base_name = m.group(1)
            dates.append(m.group(2))

    if not dates:
        print("Error: no SRF files found in ../1output/")
        sys.exit(1)

    print(f"Ensemble members: {count}")
    print(f"Base name: {base_name}")
    print(f"Dates: {', '.join(dates)}\n")

    for date in dates:
        inputs = [
            os.path.join(parent_dir, f'{n}output', f'{n}{base_name}_SRF.{date}.nc')
            for n in range(1, count + 1)
        ]
        output = f'nces_{date}.nc'

        cmd_str = f"module load nco && nces {' '.join(inputs)} {output}"
        print(f"Running: {cmd_str}")
        result = subprocess.run(cmd_str, shell=True, executable='/bin/bash')
        if result.returncode != 0:
            print(f"Error: nces failed for date {date} (exit {result.returncode})")
            sys.exit(result.returncode)
        print(f"Created: {output}\n")

    print(f"Done. {len(dates)} file(s) written to analysis/.")


if __name__ == '__main__':
    main()
