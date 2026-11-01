"""``python -m bodyscout learn --robot path.py:Class --budget N``."""
import os
import sys

for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_var, "1")

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
