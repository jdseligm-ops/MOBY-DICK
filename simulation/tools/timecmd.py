#!/usr/bin/env python3
"""Run a command and report wall/user/sys time and peak RSS of its process tree's largest child
(GNU time is not installed on Koa compute nodes). Report goes to stderr; exit code is passed through."""
import resource
import subprocess
import sys
import time

t0 = time.time()
rc = subprocess.call(sys.argv[1:])
wall = time.time() - t0
ru = resource.getrusage(resource.RUSAGE_CHILDREN)
print(f"Elapsed (wall clock) time (s): {wall:.1f}\nUser time (seconds): {ru.ru_utime:.1f}\n"
      f"System time (seconds): {ru.ru_stime:.1f}\nMaximum resident set size (kbytes): {ru.ru_maxrss}\n"
      f"Exit status: {rc}", file=sys.stderr)
sys.exit(rc)
