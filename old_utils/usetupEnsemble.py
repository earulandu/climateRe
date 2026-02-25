#!/usr/bin/env python3
import sys
import os
import re


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 setupensemble.py <base_file> <count>")
        sys.exit(1)

    base_file = sys.argv[1]
    count = int(sys.argv[2])

    if not os.path.isfile(base_file):
        print(f"Error: file not found: {base_file}")
        sys.exit(1)

    base_name = os.path.basename(base_file)
    work_dir = os.getcwd()

    with open(base_file, 'r') as f:
        content = f.read()

    for n in range(1, count + 1):
        # Create numbered input and output directories
        os.makedirs(os.path.join(work_dir, f'{n}input'), exist_ok=True)
        os.makedirs(os.path.join(work_dir, f'{n}output'), exist_ok=True)

        # Replace domname, dirter, dirglob, dirout to numbered variants
        new_content = re.sub(
            r"domname\s*=\s*'([^']*)'",
            lambda m: f"domname = '{n}{m.group(1)}'",
            content
        )
        new_content = re.sub(
            r"dirter\s*=\s*'[^']*'",
            f"dirter = './{n}input'",
            new_content
        )
        new_content = re.sub(
            r"dirglob\s*=\s*'[^']*'",
            f"dirglob = './{n}input'",
            new_content
        )
        new_content = re.sub(
            r"dirout\s*=\s*'[^']*'",
            f"dirout='./{n}output'",
            new_content
        )

        out_path = os.path.join(work_dir, f'{n}{base_name}')
        with open(out_path, 'w') as f:
            f.write(new_content)

        print(f"Created: {n}{base_name}  {n}input/  {n}output/")


if __name__ == '__main__':
    main()
