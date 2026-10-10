"""Daily unattended sync through the Windows Task Scheduler.

ponytail: Windows only; a crontab line would cover Linux when someone needs it.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

from .errors import AlquimistaError

_TASK_PREFIX = "ALQuimista Studio - "
# Values reach PowerShell through environment variables, so paths with spaces,
# quotes or accents never need escaping inside the script.
_REGISTER = (
    "$ErrorActionPreference='Stop';"
    "$a=New-ScheduledTaskAction -Execute $env:ALQ_EXE -Argument $env:ALQ_ARGS -WorkingDirectory $env:ALQ_DIR;"
    "$t=New-ScheduledTaskTrigger -Daily -At $env:ALQ_TIME;"
    "$s=New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 12);"
    "Register-ScheduledTask -TaskName $env:ALQ_NAME -Action $a -Trigger $t -Settings $s -Force | Out-Null"
)
_REMOVE = (
    "$ErrorActionPreference='Stop';"
    "Unregister-ScheduledTask -TaskName $env:ALQ_NAME -Confirm:$false"
)
_QUERY = (
    "$task=Get-ScheduledTask -TaskName $env:ALQ_NAME -ErrorAction SilentlyContinue;"
    "if ($task) { ([datetime]$task.Triggers[0].StartBoundary).ToString('HH:mm') };"
    # A missing task leaves $? false even with SilentlyContinue; that is not an error here.
    "exit 0"
)


def task_name(project_path: Path) -> str:
    resolved = str(project_path.resolve()).casefold()
    digest = hashlib.sha1(resolved.encode("utf-8")).hexdigest()[:8]
    stem = re.sub(r"[^\w .-]", "_", project_path.stem)[:40]
    return f"{_TASK_PREFIX}{stem} ({digest})"


def sync_command(project_path: Path) -> tuple[str, list[str], Path]:
    """Executable, arguments and working directory for ``--sync``."""
    project = str(project_path.resolve())
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable)
        return str(executable), ["--sync", project], executable.parent
    windowless = Path(sys.executable).with_name("pythonw.exe")
    interpreter = windowless if windowless.exists() else Path(sys.executable)
    package_root = Path(__file__).resolve().parent.parent
    return str(interpreter), ["-m", "alquimista", "--sync", project], package_root


def _powershell(script: str, env: dict[str, str]) -> str:
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )
    if completed.returncode != 0:
        raise AlquimistaError(completed.stderr.strip() or "O Agendador de Tarefas recusou a operação.")
    return completed.stdout.strip()


def schedule_daily(project_path: Path, at: str) -> None:
    """Create or replace the daily task; ``at`` is ``HH:MM``."""
    executable, arguments, workdir = sync_command(project_path)
    _powershell(
        _REGISTER,
        {
            "ALQ_NAME": task_name(project_path),
            "ALQ_EXE": executable,
            "ALQ_ARGS": subprocess.list2cmdline(arguments),
            "ALQ_DIR": str(workdir),
            "ALQ_TIME": at,
        },
    )


def remove_schedule(project_path: Path) -> None:
    _powershell(_REMOVE, {"ALQ_NAME": task_name(project_path)})


def scheduled_time(project_path: Path) -> str | None:
    """``HH:MM`` of the existing daily task, or None."""
    return _powershell(_QUERY, {"ALQ_NAME": task_name(project_path)}) or None
