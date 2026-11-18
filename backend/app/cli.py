"""Operational CLI: migrations and the program data review workflow.

  python -m app.cli migrate
  python -m app.cli import-programs FILE.json     # validates ALL records first; imports none if any fail
  python -m app.cli list-drafts
  python -m app.cli publish-program PROGRAM_ID --reviewer "Name"
"""
from __future__ import annotations

import argparse
import json
import sys

from pydantic import ValidationError

from .config import Config
from .db import connect, migrate
from .programs import repository
from .programs.schemas import ProgramImport


def _cmd_migrate(args, conn) -> int:
    applied = migrate(conn)
    print("Applied: " + ", ".join(applied) if applied else "Database is up to date.")
    return 0


def _cmd_import(args, conn) -> int:
    with open(args.file, encoding="utf-8") as fh:
        raw = json.load(fh)
    records = raw if isinstance(raw, list) else [raw]
    parsed, failed = [], 0
    for i, rec in enumerate(records):
        try:
            parsed.append(ProgramImport.model_validate(rec))
        except ValidationError as exc:
            failed += 1
            print(f"Record {i}: INVALID", file=sys.stderr)
            for e in exc.errors():
                print(f"  - {'.'.join(str(p) for p in e['loc']) or '(record)'}: {e['msg']}", file=sys.stderr)
    if failed:
        print(f"Nothing imported: {failed} of {len(records)} records failed validation.", file=sys.stderr)
        return 1
    for rec in parsed:
        program_id, outcome = repository.import_program(conn, rec)
        print(f"{outcome:9} {program_id}  {rec.university_name} - {rec.degree_name}")
    print("Imported records are drafts. Review each against its sources, then run publish-program.")
    return 0


def _cmd_list_drafts(args, conn) -> int:
    rows = repository.list_drafts(conn)
    for r in rows:
        print(f"{r['id']}  {r['university_name']} - {r['degree_name']}")
    if not rows:
        print("No drafts awaiting review.")
    return 0


def _cmd_publish(args, conn) -> int:
    try:
        repository.publish_program(conn, args.program_id, args.reviewer)
    except repository.ProgramNotFound:
        print("Program not found.", file=sys.stderr)
        return 1
    except repository.PublishBlocked as exc:
        print(f"Publish blocked: {exc}", file=sys.stderr)
        return 1
    print(f"Published {args.program_id}, reviewed by {args.reviewer}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate").set_defaults(func=_cmd_migrate)
    p_imp = sub.add_parser("import-programs")
    p_imp.add_argument("file")
    p_imp.set_defaults(func=_cmd_import)
    sub.add_parser("list-drafts").set_defaults(func=_cmd_list_drafts)
    p_pub = sub.add_parser("publish-program")
    p_pub.add_argument("program_id")
    p_pub.add_argument("--reviewer", required=True)
    p_pub.set_defaults(func=_cmd_publish)

    args = parser.parse_args(argv)
    conn = connect(Config.from_env().database_path)
    try:
        return args.func(args, conn)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
