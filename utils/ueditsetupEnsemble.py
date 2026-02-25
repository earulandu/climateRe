#!/usr/bin/env python3
import sys
import os
import re
import subprocess
import shutil
import json

STATE_FILE = '.ensemble_state.json'


def write_sbatch(work_dir, base_name, count):
    """Generate individual #submit.sbatch files for each ensemble member."""
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
        out_path = os.path.join(work_dir, f"{n}submit.sbatch")
        with open(out_path, 'w') as f:
            f.write('\n'.join(individual_lines))
        print(f"Created: {n}submit.sbatch")


def run_cmd(cmd, cwd):
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        print(f"Error: '{' '.join(cmd)}' failed with exit code {result.returncode}")
        sys.exit(result.returncode)
    print(f"  Done: {cmd[0]}")


def save_state(work_dir, base_name, count, base_domname):
    state = {'base_name': base_name, 'count': count, 'base_domname': base_domname}
    with open(os.path.join(work_dir, STATE_FILE), 'w') as f:
        json.dump(state, f)


def load_state(work_dir):
    path = os.path.join(work_dir, STATE_FILE)
    if not os.path.isfile(path):
        print("Error: no paused run found in this directory.")
        print(f"Run 'python3 {os.path.basename(sys.argv[0])} <base_file> <count>' first.")
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def main():
    work_dir = os.getcwd()

    # ── continue mode ─────────────────────────────────────────────────────────
    if len(sys.argv) == 2 and sys.argv[1] == 'continue':
        state = load_state(work_dir)
        base_name    = state['base_name']
        count        = state['count']
        base_domname = state['base_domname']

        m1_in_file   = f"1{base_name}"
        m1_domname   = f"1{base_domname}"
        m1_input_dir = os.path.join(work_dir, "1input")

        print(f"Resuming: running sst and icbc for member 1 ({m1_in_file})...")
        for cmd_name in ["sst", "icbc"]:
            run_cmd([cmd_name, m1_in_file], work_dir)

        if count > 1:
            print(f"\nCopying input files from 1input to members 2-{count}...")
            src_files = os.listdir(m1_input_dir)
            for n in range(2, count + 1):
                m_domname   = f"{n}{base_domname}"
                m_input_dir = os.path.join(work_dir, f"{n}input")
                for fname in src_files:
                    src = os.path.join(m1_input_dir, fname)
                    new_fname = m_domname + fname[len(m1_domname):] if fname.startswith(m1_domname) else fname
                    shutil.copy2(src, os.path.join(m_input_dir, new_fname))
                    print(f"  {n}input/{new_fname}")

        write_sbatch(work_dir, base_name, count)

        os.remove(os.path.join(work_dir, STATE_FILE))
        print(f"\nDone. All {count} ensemble members ready.")

    # ── initial setup mode ────────────────────────────────────────────────────
    elif len(sys.argv) == 3:
        base_file = sys.argv[1]
        count     = int(sys.argv[2])

        if not os.path.isfile(base_file):
            print(f"Error: file not found: {base_file}")
            sys.exit(1)

        base_name = os.path.basename(base_file)

        with open(base_file, 'r') as f:
            content = f.read()

        for n in range(1, count + 1):
            os.makedirs(os.path.join(work_dir, f'{n}input'), exist_ok=True)
            os.makedirs(os.path.join(work_dir, f'{n}output'), exist_ok=True)

            new_content = re.sub(
                r"domname\s*=\s*'([^']*)'",
                lambda m: f"domname = '{n}{m.group(1)}'",
                content
            )
            new_content = re.sub(r"dirter\s*=\s*'[^']*'",  f"dirter = './{n}input'",  new_content)
            new_content = re.sub(r"dirglob\s*=\s*'[^']*'", f"dirglob = './{n}input'", new_content)
            new_content = re.sub(r"dirout\s*=\s*'[^']*'",  f"dirout='./{n}output'",   new_content)

            out_path = os.path.join(work_dir, f'{n}{base_name}')
            with open(out_path, 'w') as f:
                f.write(new_content)

            print(f"Created: {n}{base_name}  {n}input/  {n}output/")

        base_domname = re.search(r"domname\s*=\s*'([^']*)'", content).group(1)
        m1_in_file   = f"1{base_name}"

        print(f"\nRunning terrain for member 1 ({m1_in_file})...")
        run_cmd(["terrain", m1_in_file], work_dir)

        run_cmd(["cp", "/N/u/earuland/Quartz/thindrives/climateRe/utils/editlanduse.py", "."], work_dir)

        save_state(work_dir, base_name, count, base_domname)

        print(f"\nTerrain complete. Edit 1input/ now, then run:")
        print(f"  python3 {os.path.basename(sys.argv[0])} continue")

    # ── bad usage ─────────────────────────────────────────────────────────────
    else:
        print("Usage:")
        print(f"  python3 {os.path.basename(sys.argv[0])} <base_file> <count>   # setup + terrain")
        print(f"  python3 {os.path.basename(sys.argv[0])} continue               # resume after editing")
        sys.exit(1)


if __name__ == '__main__':
    main()
