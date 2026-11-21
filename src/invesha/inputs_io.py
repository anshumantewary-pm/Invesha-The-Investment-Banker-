"""Read model inputs from an uploaded file (Excel, CSV or JSON) and make blank templates.

Files are read as rows of cells. The first cell names the field (its key, its form label,
or an alias such as the label on the downloadable workbook's Inputs sheet). The value is
taken from the column headed "Value" when there is one, otherwise from the second column.
So all of these work:

* the template downloaded from the platform (Key | Field | Value | Help)
* the Excel model downloaded from the platform (its Inputs sheet), edited and re-uploaded
* any simple two-column sheet or CSV: ``revenue, 1200``
* a JSON object of inputs, or a JSON file saved from the platform
"""

from __future__ import annotations

import csv
import io
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from typing import Any

from invesha.core import InputError
from invesha.examples import EXAMPLES
from invesha.fields import ALIASES, FORMS, fields
from invesha.sectors import SECTORS
from invesha.xlsx import BOLD, HEADER, IN_NUM, IN_PCT, IN_TEXT, NOTE, TITLE, Workbook

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9%]+", " ", str(text).lower()).strip()


def _lookup(kind: str) -> dict[str, list[str]]:
    """normalised name -> field spec, for keys, labels and aliases."""
    table: dict[str, list[str]] = {}
    for spec in fields(kind):
        key, label = spec[0], spec[1]
        for name in (key, key.replace("_", " "), label, label + " (%)", *ALIASES.get(key, [])):
            table.setdefault(_norm(name), spec)
    return table


# ---------------------------------------------------------------- reading files


def _xlsx_rows(data: bytes) -> list[list[Any]]:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise InputError("this does not look like an Excel .xlsx file") from None
    shared: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root.findall("m:si", NS):
            shared.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    targets = {r.get("Id"): r.get("Target") for r in rels}
    node = wb.find("m:sheets", NS)
    sheets = [(s.get("name") or "", targets.get(s.get(REL_NS))) for s in (node if node is not None else [])]
    if not sheets:
        raise InputError("the workbook has no sheets")
    # Prefer a sheet called Inputs (the platform's own workbook), else the first sheet.
    name, target = next((s for s in sheets if s[0].strip().lower() == "inputs"), sheets[0])
    path = target.lstrip("/") if target and target.startswith("/") else f"xl/{target}"
    root = ET.fromstring(z.read(path))
    rows: list[list[Any]] = []
    for row in root.iter(f"{{{NS['m']}}}row"):
        cells: dict[int, Any] = {}
        for c in row.findall("m:c", NS):
            ref = c.get("r", "")
            col = 0
            for ch in re.match(r"[A-Z]+", ref).group(0) if re.match(r"[A-Z]+", ref) else "":
                col = col * 26 + ord(ch) - 64
            t, v = c.get("t"), c.find("m:v", NS)
            if t == "s" and v is not None:
                value: Any = shared[int(v.text or 0)]
            elif t == "inlineStr":
                value = "".join(x.text or "" for x in c.iter(f"{{{NS['m']}}}t"))
            elif t in ("str", "e"):
                value = v.text if v is not None else None
            elif t == "b":
                value = v is not None and v.text == "1"
            elif v is not None and v.text is not None:
                value = float(v.text)
            else:
                value = None
            cells[col] = value
        if cells:
            width = max(cells)
            rows.append([cells.get(i) for i in range(1, width + 1)])
    return rows


def _csv_rows(text: str) -> list[list[Any]]:
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [row for row in csv.reader(io.StringIO(text), dialect) if any(c.strip() for c in row)]


def _number(raw: Any, field_type: str) -> float:
    if isinstance(raw, bool):
        raise ValueError("not a number")
    if isinstance(raw, (int, float)):
        x = float(raw)
        percent_sign = False
    else:
        text = re.sub(r"[\s,₹$€£]", "", str(raw))
        percent_sign = text.endswith("%")
        text = text.rstrip("%").replace("x", "") if field_type == "x" else text.rstrip("%")
        if text.startswith("(") and text.endswith(")"):
            text = "-" + text[1:-1]
        x = float(text)
    # "18%", 18 and 0.18 all mean 18%: values above 1.5 are read as percentages.
    if field_type == "pct" and (percent_sign or abs(x) > 1.5):
        x /= 100
    return x


def _convert(spec: list[str], raw: Any) -> Any:
    label, ftype = spec[1], spec[2]
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    try:
        if ftype in ("text",) or ftype.startswith("select:"):
            return str(raw).strip()
        if ftype == "currency":
            text = str(raw).strip()
            return {"inr": "₹", "rs": "₹", "usd": "$", "eur": "€", "gbp": "£"}.get(text.lower(), text[:1] or "")
        if ftype == "sector":
            text = _norm(raw)
            for k, s in SECTORS.items():
                if text in (k, _norm(s.name)) or text and text in _norm(s.name):
                    return k
            raise ValueError(f"unknown sector {raw!r}")
        if ftype == "list":
            parts = [p for p in re.split(r"[;,\s]+", str(raw)) if p]
            return [_number(p, "pct") for p in parts]
        if ftype == "rounds":
            rounds = []
            for part in re.split(r"[;\n|]+", str(raw)):
                if part.strip():
                    month, amount = re.split(r"\s*[=:]\s*|\s+", part.strip(), maxsplit=1)
                    rounds.append({"month": int(float(month)), "amount": _number(amount, "num")})
            return rounds
        x = _number(raw, ftype)
        return int(round(x)) if ftype == "int" else x
    except (ValueError, TypeError) as error:
        raise InputError(f"{label}: could not read {raw!r} ({error})") from None


def parse_rows(kind: str, rows: list[list[Any]]) -> dict[str, Any]:
    lookup = _lookup(kind)
    value_col = 1
    found: dict[str, Any] = {}
    unknown: list[str] = []
    for row in rows:
        if not row or row[0] is None:
            continue
        first = _norm(row[0])
        lowered = [_norm(c) if c is not None else "" for c in row]
        if "value" in lowered and first in ("key", "field", "input", "name", "item"):
            value_col = lowered.index("value")
            continue
        spec = lookup.get(first)
        if spec is None and len(row) > 1 and row[1] is not None:
            spec = lookup.get(_norm(row[1]))  # template rows also carry the label in column B
        if spec is None:
            if len(row) > value_col and row[value_col] not in (None, ""):
                unknown.append(str(row[0]))
            continue
        raw = row[value_col] if len(row) > value_col else None
        value = _convert(spec, raw)
        if value is not None:
            found[spec[0]] = value
    return {"inputs": found, "matched": len(found), "ignored": unknown[:20]}


def parse_file(kind: str, filename: str, data: bytes) -> dict[str, Any]:
    if kind not in FORMS:
        raise InputError(f"unknown model {kind!r}")
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm")):
        result = parse_rows(kind, _xlsx_rows(data))
    elif name.endswith(".json"):
        try:
            obj = json.loads(data.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise InputError(f"not a valid JSON file: {error}") from None
        obj = obj.get("inputs", obj) if isinstance(obj, dict) else obj
        if not isinstance(obj, dict):
            raise InputError("the JSON file must contain an object of inputs")
        result = parse_rows(kind, [[k, v] for k, v in obj.items()])
    elif name.endswith((".csv", ".txt", ".tsv")):
        result = parse_rows(kind, _csv_rows(data.decode("utf-8-sig", errors="replace")))
    elif name.endswith(".xls"):
        raise InputError("old .xls files are not supported: save as .xlsx or CSV and upload again")
    else:
        raise InputError("upload an Excel (.xlsx), CSV or JSON file")
    if not result["matched"]:
        raise InputError("no recognised inputs in this file: download the template to see the expected layout")
    return result


# ---------------------------------------------------------------- templates


def _display(spec: list[str], value: Any) -> Any:
    ftype = spec[2]
    if value is None:
        return None
    if ftype == "list":
        return ", ".join(f"{v * 100:g}%" for v in value)
    if ftype == "rounds":
        return "; ".join(f"{r['month']:g}={r['amount']:g}" for r in value)
    return value


def template_xlsx(kind: str, with_example: bool = True) -> bytes:
    if kind not in FORMS:
        raise InputError(f"unknown model {kind!r}")
    form = FORMS[kind]
    example = EXAMPLES[kind] if with_example else {}
    wb = Workbook()
    s = wb.add("Inputs")
    s.widths = {1: 24, 2: 40, 3: 22, 4: 60}
    s.set(1, 1, f"Invesha: {form['title']} inputs", TITLE)
    s.set(
        2,
        1,
        "Fill the Value column (blue), then upload this file on the platform. "
        "Percentages can be typed as 18% or 18. Leave a value blank to use the default.",
        NOTE,
    )
    for c, h in enumerate(("Key", "Field", "Value", "Help"), 1):
        s.set(4, c, h, HEADER)
    row = 4
    for title, group in form["groups"]:
        row += 2
        s.set(row, 1, title, BOLD)
        for spec in group:
            key, label, ftype = spec[0], spec[1], spec[2]
            hint = spec[3] if len(spec) > 3 else ""
            if ftype == "sector":
                hint = (hint + " " if hint else "") + "one of: " + ", ".join(SECTORS)
            elif ftype.startswith("select:"):
                hint = "one of: " + ftype[7:].replace(",", ", ")
            elif ftype == "rounds":
                hint = "month=amount; month=amount"
            row += 1
            s.set(row, 1, key, NOTE)
            s.set(row, 2, label + (" (%)" if ftype == "pct" else ""))
            value = _display(spec, example.get(key))
            style = IN_PCT if ftype == "pct" else IN_NUM if isinstance(value, (int, float)) else IN_TEXT
            s.set(row, 3, value, style)
            if hint:
                s.set(row, 4, hint, NOTE)
    s.freeze = (4, 0)
    return wb.to_bytes()


def template_csv(kind: str, with_example: bool = True) -> str:
    if kind not in FORMS:
        raise InputError(f"unknown model {kind!r}")
    example = EXAMPLES[kind] if with_example else {}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Key", "Field", "Value"])
    for spec in fields(kind):
        value = _display(spec, example.get(spec[0]))
        if spec[2] == "pct" and isinstance(value, (int, float)):
            value = f"{value * 100:g}%"
        w.writerow([spec[0], spec[1], "" if value is None else value])
    return buf.getvalue()
