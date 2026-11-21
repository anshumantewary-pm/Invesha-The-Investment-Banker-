"""Command line: ``invesha company|project|startup --file inputs.json [--xlsx out.xlsx] [--json]``.

``invesha example company > company.json`` prints a ready-made input file to start from.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from invesha import __version__, corporate, excel, project, startup
from invesha.core import InputError, Report, fmt_value
from invesha.examples import EXAMPLES
from invesha.sectors import SECTORS

MODELS = {"company": corporate.analyse_inputs, "project": project.analyse_inputs, "startup": startup.analyse_inputs}


def run(kind: str, data: dict[str, Any]) -> Report:
    return MODELS[kind](data)


def render(report: Report) -> str:
    cur, unit = report.currency, report.unit
    out = [f"{report.title}", report.subtitle, "", f"VERDICT: {report.verdict}", report.verdict_note, ""]
    for t in report.tiles:
        out.append(f"  {t.label:<28} {fmt_value(t.value, t.fmt, cur, unit):>20}  {t.note}")
    for table in report.tables:
        out += ["", f"== {table.title}"]
        out.append("  ".join(f"{c:>14}" if i else f"{c:<30}" for i, c in enumerate(table.columns)))
        for r, row in enumerate(table.rows):
            cells = []
            for c, v in enumerate(row):
                if c == 0:
                    cells.append(f"{str(v):<30}")
                    continue
                fmt = table.fmts[c] if table.by_column else table.fmts[r]
                cells.append(f"{fmt_value(v, fmt, '', ''):>14}")
            out.append("  ".join(cells))
    out += ["", "== Suggestions"]
    for s in report.suggestions:
        out.append(f"[{s.priority.upper()}] {s.area}: {s.title}")
        out.append(f"    {s.detail}")
        out += [f"    - {a}" for a in s.actions]
    return "\n".join(out)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="invesha", description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    for kind in MODELS:
        p = sub.add_parser(kind, help=f"run the {kind} model")
        p.add_argument("--file", required=True, help="JSON inputs (see 'invesha example')")
        p.add_argument("--xlsx", help="also write the Excel workbook here")
        p.add_argument("--json", action="store_true", help="print the full report as JSON")
    ex = sub.add_parser("example", help="print example inputs")
    ex.add_argument("kind", choices=list(MODELS))
    sub.add_parser("sectors", help="list sectors")
    args = parser.parse_args(argv)

    if args.command == "example":
        print(json.dumps(EXAMPLES[args.kind], indent=2, ensure_ascii=False))
        return 0
    if args.command == "sectors":
        for s in SECTORS.values():
            print(f"{s.key:<15} {s.name:<34} EV/EBITDA {s.ev_ebitda[0]:.0f}-{s.ev_ebitda[2]:.0f}x")
        return 0
    try:
        with open(args.file, encoding="utf-8") as handle:
            data = json.load(handle)
        report = run(args.command, data)
        if args.xlsx:
            with open(args.xlsx, "wb") as handle:
                handle.write(excel.build(args.command, data))
    except (OSError, json.JSONDecodeError) as error:
        print(f"error: cannot read {args.file}: {error}", file=sys.stderr)
        return 2
    except InputError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False) if args.json else render(report))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
