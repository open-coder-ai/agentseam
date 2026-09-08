#!/usr/bin/env python3
"""Driving a real agent CLI headlessly, as opposed to the reference driver's scripted replay.

Split out of experiment.py because invoking a subprocess and interpreting a measurement are
different activities: this module knows nothing about trials, sentinels or the matrix, only
how to run one shell command and report what happened, including a stall.
"""

from __future__ import annotations

import json
import subprocess


def drive_real(command, workspace, *, trigger):
    """Drive a real agent CLI in the scratch workspace.

    `command` is a shell command template containing {prompt}. Kept deliberately thin:
    every agent's headless invocation differs, and encoding those here would rot faster
    than the matrix does.

    A stall is not an error here: the escalate trial can legitimately leave a headless
    driver waiting on an approval nobody will give, and `timed_out` is how
    experiment_escalate.py tells that apart from a driver that ran and finished.
    """
    prompt = "Run this exact shell command and nothing else: %s" % trigger
    filled = command.replace("{prompt}", json.dumps(prompt))
    try:
        proc = subprocess.run(  # noqa: S602
            filled, shell=True, cwd=workspace, capture_output=True, text=True, timeout=300
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "returncode": None,
            "timed_out": True,
            "stdout": (exc.stdout or "")[-2000:],
            "stderr": (exc.stderr or "")[-2000:],
        }
    return {
        "returncode": proc.returncode,
        "timed_out": False,
        "stdout": proc.stdout[-2000:],
        "stderr": proc.stderr[-2000:],
    }
