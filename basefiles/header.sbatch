#!/bin/bash
#SBATCH -A r00389
#SBATCH -p general
#SBATCH -N 1
#SBATCH -n 64
#SBATCH -t 240
#SBATCH --mem=128GB

module use /N/slate/obrienta/software/quartz/modulefiles
module load regcm

srun -n 64 regcmMPI