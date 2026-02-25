import os
import shutil

BASE_SRC = "/N/u/earuland/Quartz/thindrives/climateRe/basefiles"
UTILS_SRC = "/N/u/earuland/Quartz/thindrives/climateRe/utils"


def setupdir(dest):
    os.makedirs(dest, exist_ok=True)

    shutil.copy(os.path.join(BASE_SRC, "btown_000.in"), dest)
    shutil.copy(os.path.join(BASE_SRC, "header.sbatch"), dest)

    base_dir = os.path.join(dest, "base")
    edit_dir = os.path.join(dest, "edit")
    os.makedirs(base_dir, exist_ok=True)
    os.makedirs(edit_dir, exist_ok=True)

    shutil.copy(os.path.join(UTILS_SRC, "ubasesetupEnsemble.py"), base_dir)
    shutil.copy(os.path.join(UTILS_SRC, "ueditsetupEnsemble.py"), edit_dir)


if __name__ == '__main__':
    setupdir(os.getcwd())
