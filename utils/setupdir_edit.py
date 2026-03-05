import os
import shutil
import subprocess
import sys

UTILS_SRC = "/N/u/earuland/Quartz/thindrives/climateRe/utils"


def setup_edit_dir(dest, name):
    edit_dir = os.path.join(dest, name)
    os.makedirs(os.path.join(edit_dir, "analysis"), exist_ok=True)
    shutil.copy(os.path.join(UTILS_SRC, "ueditsetupEnsemble.py"), edit_dir)
    shutil.copy(os.path.join(UTILS_SRC, "ncesanalysis.py"), os.path.join(edit_dir, "analysis"))
    print(f"  + {name}/")


def setupdir_edit(dest, num_edits=1):
    os.makedirs(dest, exist_ok=True)
    print(f"setup  {num_edits} edit dir{'s' if num_edits > 1 else ''}")

    if num_edits == 1:
        plain_edit = os.path.join(dest, "edit")
        if os.path.exists(plain_edit):
            print(f"  skip  edit/  (already exists)")
        else:
            setup_edit_dir(dest, "edit")
        edit_labels = ["edit"]
    else:
        for i in range(1, num_edits + 1):
            setup_edit_dir(dest, f"{i}edit")
        edit_labels = [f"{i}edit" for i in range(1, num_edits + 1)]

    changes_path = os.path.join(dest, "edit_doc.txt")
    with open(changes_path, "w") as f:
        for label in edit_labels:
            f.write(f"{label}:\n")
    print(f"  + edit_doc.txt")
    print(f"\ndone")


if __name__ == '__main__':
    subprocess.run(
        'module use /N/slate/obrienta/software/quartz/modulefiles && module load regcm',
        shell=True,
        executable='/bin/bash'
    )
    subprocess.run(
        'module load conda && conda activate /N/slate/$USER/conda_envs/easg690',
        shell=True,
        executable='/bin/bash'
    )

    num_edits = 1
    if len(sys.argv) > 1:
        num_edits = int(sys.argv[1])

    setupdir_edit(os.getcwd(), num_edits)
