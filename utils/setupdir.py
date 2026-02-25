import os
import shutil
import subprocess

BASE_SRC = "/N/u/earuland/Quartz/thindrives/climateRe/basefiles"
UTILS_SRC = "/N/u/earuland/Quartz/thindrives/climateRe/utils"


def setupdir(dest):
    os.makedirs(dest, exist_ok=True)

    shutil.copy(os.path.join(BASE_SRC, "btown_000.in"), dest)
    shutil.copy(os.path.join(BASE_SRC, "header.sbatch"), dest)

    base_dir = os.path.join(dest, "base")
    edit_dir = os.path.join(dest, "edit")
    os.makedirs(os.path.join(base_dir, "analysis"), exist_ok=True)
    os.makedirs(os.path.join(edit_dir, "analysis"), exist_ok=True)

    shutil.copy(os.path.join(UTILS_SRC, "ubasesetupEnsemble.py"), base_dir)
    shutil.copy(os.path.join(UTILS_SRC, "ueditsetupEnsemble.py"), edit_dir)
    shutil.copy(os.path.join(UTILS_SRC, "ncesanalysis.py"), os.path.join(base_dir, "analysis"))
    shutil.copy(os.path.join(UTILS_SRC, "ncesanalysis.py"), os.path.join(edit_dir, "analysis"))


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
    setupdir(os.getcwd())
