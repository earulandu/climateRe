#!/usr/bin/env python3
import sys
import os
import re
import subprocess
import shutil


def write_sbatch(work_dir, base_name, count):
    """Generate individual #batch.sbatch files for each ensemble member."""
    template_path = os.path.join(work_dir, '..', 'header.sbatch')
    srun_prefix = "srun -n 64 regcmMPI"

    if os.path.isfile(template_path):
        header_lines = []
        with open(template_path, 'r') as f:
            for line in f:
                stripped = line.rstrip()
                if re.match(r'\s*srun\b', stripped):
                    srun_prefix = stripped
                    break
                header_lines.append(stripped)
    else:
        header_lines = [
            "#!/bin/bash",
            "#SBATCH -A r00389",
            "#SBATCH -p general",
            "#SBATCH -N 1",
            "#SBATCH -n 64",
            "#SBATCH -t 240",
            "#SBATCH --mem=128GB",
            "",
            "module use /N/slate/obrienta/software/quartz/modulefiles",
            "module load regcm",
        ]

    for n in range(1, count + 1):
        individual_lines = header_lines + ["", f"{srun_prefix} {n}{base_name}", ""]
        out_path = os.path.join(work_dir, f"{n}batch.sbatch")
        with open(out_path, 'w') as f:
            f.write('\n'.join(individual_lines))
        print(f"Created: {n}batch.sbatch")


def submit_sbatch(work_dir):
    """Submit all *batch.sbatch files in numeric order."""
    sbatch_files = sorted(
        [f for f in os.listdir(work_dir) if re.match(r'^\d+batch\.sbatch$', f)],
        key=lambda f: int(re.match(r'^(\d+)', f).group(1))
    )
    if not sbatch_files:
        print("Error: no *batch.sbatch files found in current directory.")
        sys.exit(1)

    print(f"Submitting {len(sbatch_files)} job(s)...")
    for fname in sbatch_files:
        result = subprocess.run(['sbatch', fname], cwd=work_dir, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error submitting {fname}: {result.stderr.strip()}")
            sys.exit(result.returncode)
        print(f"  {fname}: {result.stdout.strip()}")


def run_cmd(cmd, cwd):
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        print(f"Error: '{' '.join(cmd)}' failed with exit code {result.returncode}")
        sys.exit(result.returncode)
    print(f"  Done: {cmd[0]}")


def main():
    work_dir = os.getcwd()

    if len(sys.argv) == 2 and sys.argv[1] == 'sbatch':
        submit_sbatch(work_dir)
        return

    if len(sys.argv) != 3:
        print("Usage:")
        print(f"  python3 {os.path.basename(sys.argv[0])} <base_file> <count>   # setup + run all preprocessing")
        print(f"  python3 {os.path.basename(sys.argv[0])} sbatch                 # submit all batch jobs")
        sys.exit(1)

    base_file = sys.argv[1]
    count = int(sys.argv[2])

    if not os.path.isfile(base_file):
        print(f"Error: file not found: {base_file}")
        sys.exit(1)

    base_name = os.path.basename(base_file)

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

    # Parse the base domname to know what prefix terrain/sst/icbc will use
    base_domname = re.search(r"domname\s*=\s*'([^']*)'", content).group(1)
    m1_in_file = f"1{base_name}"
    m1_domname = f"1{base_domname}"
    m1_input_dir = os.path.join(work_dir, "1input")

    # Run terrain, sst, icbc sequentially for member 1
    print(f"\nRunning preprocessing for member 1 ({m1_in_file})...")
    for cmd_name in ["terrain", "sst", "icbc"]:
        run_cmd([cmd_name, m1_in_file], work_dir)

    # Copy and rename files from 1input to {n}input for members 2..count
    if count > 1:
        print(f"\nCopying input files from 1input to members 2-{count}...")
        src_files = os.listdir(m1_input_dir)
        for n in range(2, count + 1):
            m_domname = f"{n}{base_domname}"
            m_input_dir = os.path.join(work_dir, f"{n}input")
            for fname in src_files:
                src = os.path.join(m1_input_dir, fname)
                new_fname = m_domname + fname[len(m1_domname):] if fname.startswith(m1_domname) else fname
                shutil.copy2(src, os.path.join(m_input_dir, new_fname))
                print(f"  {n}input/{new_fname}")

    # Generate individual batch sbatch files for each ensemble member
    write_sbatch(work_dir, base_name, count)

    print(f"\nDone. All {count} ensemble members ready.")


if __name__ == '__main__':
    main()
