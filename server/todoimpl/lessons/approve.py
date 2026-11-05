"""Write an approved lesson into its skill through skill_lesson.py."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from todoimpl.lessons.store import LOCK, Lesson, LessonError, load_lessons, save_lessons

TIMEOUT_S = 30.0
OK_CODES = (0, 2)  # 2 = recorded, but consolidation into SKILL.md is now due (needs stdout)


def approve(run_dir: Path, lesson_id: str) -> Lesson:
    """Run `skill_lesson.py add` once for a drafted lesson and mark it approved.

    Idempotent: an already approved lesson returns without running anything. On
    failure the lesson stays drafted so the click can be retried.
    """
    with LOCK:
        lessons = load_lessons(run_dir)
        index = next((i for i, x in enumerate(lessons) if x.id == lesson_id), None)
        if index is None:
            msg = f"unknown lesson {lesson_id!r}"
            raise LessonError(msg)
        lesson = lessons[index]
        if lesson.state == "approved":
            return lesson
        script = Path.home() / ".claude/scripts/skill_lesson.py"
        if not script.is_file():  # python would exit 2 on a missing file: indistinguishable from "recorded"
            msg = f"cannot run skill_lesson.py: {script} does not exist"
            raise LessonError(msg)
        argv = [
            sys.executable,
            str(script),
            "add",
            lesson.skill,
            "--mistake",
            lesson.mistake,
            "--rule",
            lesson.rule,
            "--evidence",
            lesson.evidence,
        ]
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=TIMEOUT_S, check=False)  # noqa: S603
        except (OSError, subprocess.TimeoutExpired) as exc:
            msg = f"cannot run skill_lesson.py: {exc}"
            raise LessonError(msg) from exc
        # argparse usage errors also exit 2, but print nothing on stdout; a real "recorded" does.
        if proc.returncode not in OK_CODES or (proc.returncode == 2 and not proc.stdout.strip()):  # noqa: PLR2004
            msg = f"skill_lesson.py exit {proc.returncode}: {(proc.stdout + proc.stderr).strip()[-300:]}"
            raise LessonError(msg)
        lessons[index] = replace(lesson, state="approved")
        save_lessons(run_dir, lessons)
        return lessons[index]
