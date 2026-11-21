"""A small .xlsx writer (standard library only) with formulas, styles and cached values.

Formulas are written with their computed value cached, so the file shows numbers in any
viewer, and the workbook asks Excel / LibreOffice / Google Sheets to recalculate on open,
so editing a blue input cell flows through the model.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any
from xml.sax.saxutils import escape

# Style ids (see STYLES below)
TEXT, BOLD, HEADER, NUM, PCT, MULT, INT, IN_NUM, IN_PCT, TOTAL, TITLE, DEC, IN_TEXT, TOTAL_PCT, NOTE, IN_MULT, PRICE = (
    range(17)
)

FMT_STYLE = {"money": NUM, "pct": PCT, "x": MULT, "int": INT, "year": INT, "num": DEC, "text": TEXT, "price": PRICE}
INPUT_STYLE = {
    "money": IN_NUM,
    "pct": IN_PCT,
    "x": IN_MULT,
    "int": IN_NUM,
    "num": IN_NUM,
    "text": IN_TEXT,
    "price": IN_NUM,
}


def col_letter(col: int) -> str:
    """1 -> A, 27 -> AA."""
    out = ""
    while col:
        col, rem = divmod(col - 1, 26)
        out = chr(65 + rem) + out
    return out


def ref(row: int, col: int, absolute: bool = False) -> str:
    d = "$" if absolute else ""
    return f"{d}{col_letter(col)}{d}{row}"


@dataclass
class Sheet:
    name: str
    cells: dict[tuple[int, int], tuple[Any, int, Any]] = field(default_factory=dict)
    widths: dict[int, float] = field(default_factory=dict)
    freeze: tuple[int, int] | None = None  # (rows, cols) frozen

    def set(self, row: int, col: int, value: Any, style: int = TEXT) -> None:
        self.cells[(row, col)] = (value, style, None)

    def formula(self, row: int, col: int, expr: str, cached: Any = None, style: int = NUM) -> None:
        self.cells[(row, col)] = (expr.lstrip("="), style, ("f", cached))

    def addr(self, row: int, col: int, absolute: bool = True) -> str:
        return f"'{self.name}'!{ref(row, col, absolute)}"


class Workbook:
    def __init__(self) -> None:
        self.sheets: list[Sheet] = []

    def add(self, name: str) -> Sheet:
        clean = re.sub(r"[\[\]:*?/\\]", "", name)[:31] or "Sheet"
        base, n = clean, 2
        while any(s.name == clean for s in self.sheets):
            suffix = f" ({n})"
            clean = base[: 31 - len(suffix)] + suffix
            n += 1
        sheet = Sheet(clean)
        self.sheets.append(sheet)
        return sheet

    def to_bytes(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", _content_types(len(self.sheets)))
            z.writestr("_rels/.rels", _ROOT_RELS)
            z.writestr("xl/workbook.xml", _workbook(self.sheets))
            z.writestr("xl/_rels/workbook.xml.rels", _workbook_rels(len(self.sheets)))
            z.writestr("xl/styles.xml", STYLES)
            for i, sheet in enumerate(self.sheets, 1):
                z.writestr(f"xl/worksheets/sheet{i}.xml", _sheet_xml(sheet))
        return buf.getvalue()


def _num(v: float) -> str:
    return repr(float(v)) if v == v and v not in (float("inf"), float("-inf")) else ""


def _cell(row: int, col: int, value: Any, style: int, extra: Any) -> str:
    r = ref(row, col)
    if extra and extra[0] == "f":
        cached = extra[1]
        f = f"<f>{escape(value)}</f>"
        if isinstance(cached, str):
            return f'<c r="{r}" s="{style}" t="str">{f}<v>{escape(cached)}</v></c>'
        if isinstance(cached, (int, float)) and not isinstance(cached, bool) and _num(cached):
            return f'<c r="{r}" s="{style}">{f}<v>{_num(cached)}</v></c>'
        return f'<c r="{r}" s="{style}">{f}</c>'
    if value is None:
        return f'<c r="{r}" s="{style}"/>' if style else ""
    if isinstance(value, bool):
        value = "Yes" if value else "No"
    if isinstance(value, (int, float)):
        s = _num(value)
        return f'<c r="{r}" s="{style}"><v>{s}</v></c>' if s else f'<c r="{r}" s="{style}"/>'
    return f'<c r="{r}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{escape(str(value))}</t></is></c>'


def _sheet_xml(sheet: Sheet) -> str:
    rows: dict[int, list[str]] = {}
    for (r, c), (v, s, extra) in sorted(sheet.cells.items()):
        xml = _cell(r, c, v, s, extra)
        if xml:
            rows.setdefault(r, []).append(xml)
    body = "".join(f'<row r="{r}">{"".join(cells)}</row>' for r, cells in sorted(rows.items()))
    cols = "".join(f'<col min="{c}" max="{c}" width="{w}" customWidth="1"/>' for c, w in sorted(sheet.widths.items()))
    views = '<sheetViews><sheetView workbookViewId="0" showGridLines="0">'
    if sheet.freeze:
        fr, fc = sheet.freeze
        top = ref(fr + 1, fc + 1)
        attrs = (f' xSplit="{fc}"' if fc else "") + (f' ySplit="{fr}"' if fr else "")
        views += f'<pane{attrs} topLeftCell="{top}" activePane="bottomRight" state="frozen"/>'
    views += "</sheetView></sheetViews>"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'{views}<sheetFormatPr defaultRowHeight="15"/>'
        f"{'<cols>' + cols + '</cols>' if cols else ''}<sheetData>{body}</sheetData></worksheet>"
    )


def _content_types(n: int) -> str:
    sheets = "".join(
        f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for i in range(1, n + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        f"{sheets}</Types>"
    )


_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
    'relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'
)


def _workbook(sheets: list[Sheet]) -> str:
    items = "".join(f'<sheet name="{escape(s.name)}" sheetId="{i}" r:id="rId{i}"/>' for i, s in enumerate(sheets, 1))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets>{items}</sheets><calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>'
    )


def _workbook_rels(n: int) -> str:
    rels = "".join(
        f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        f'relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
        for i in range(1, n + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'{rels}<Relationship Id="rId{n + 1}" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'
    )


# fonts: 0 normal, 1 bold, 2 blue (inputs), 3 bold white, 4 title, 5 grey italic
# fills: 0 none, 1 gray125 (required), 2 orange header, 3 light input
# numFmts: 164 #,##0.0  165 0.0%  166 0.00"x"  167 #,##0  168 0.000  169 #,##0.00##
STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<numFmts count="6"><numFmt numFmtId="164" formatCode="#,##0.0;[Red]-#,##0.0"/>'
    '<numFmt numFmtId="165" formatCode="0.0%"/><numFmt numFmtId="166" formatCode="0.00&quot;x&quot;"/>'
    '<numFmt numFmtId="167" formatCode="#,##0"/><numFmt numFmtId="168" formatCode="0.000"/>'
    '<numFmt numFmtId="169" formatCode="#,##0.00##"/></numFmts>'
    '<fonts count="6">'
    '<font><sz val="11"/><name val="Calibri"/></font>'
    '<font><b/><sz val="11"/><name val="Calibri"/></font>'
    '<font><sz val="11"/><color rgb="FF0000FF"/><name val="Calibri"/></font>'
    '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>'
    '<font><b/><sz val="15"/><color rgb="FFE8501A"/><name val="Calibri"/></font>'
    '<font><i/><sz val="10"/><color rgb="FF777777"/><name val="Calibri"/></font>'
    "</fonts>"
    '<fills count="4"><fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFE8501A"/><bgColor indexed="64"/></patternFill></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFFFF4E5"/><bgColor indexed="64"/></patternFill></fill>'
    "</fills>"
    '<borders count="2"><border/><border><top style="thin"><color rgb="FF999999"/></top></border></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="17">'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>'  # 0 TEXT
    '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" applyFont="1"/>'  # 1 BOLD
    '<xf numFmtId="0" fontId="3" fillId="2" borderId="0" applyFont="1" applyFill="1"/>'  # 2 HEADER
    '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" applyNumberFormat="1"/>'  # 3 NUM
    '<xf numFmtId="165" fontId="0" fillId="0" borderId="0" applyNumberFormat="1"/>'  # 4 PCT
    '<xf numFmtId="166" fontId="0" fillId="0" borderId="0" applyNumberFormat="1"/>'  # 5 MULT
    '<xf numFmtId="167" fontId="0" fillId="0" borderId="0" applyNumberFormat="1"/>'  # 6 INT
    '<xf numFmtId="4" fontId="2" fillId="3" borderId="0" applyNumberFormat="1" applyFont="1" applyFill="1"/>'  # 7
    '<xf numFmtId="165" fontId="2" fillId="3" borderId="0" applyNumberFormat="1" applyFont="1" applyFill="1"/>'  # 8
    '<xf numFmtId="164" fontId="1" fillId="0" borderId="1" applyNumberFormat="1" applyFont="1" applyBorder="1"/>'  # 9
    '<xf numFmtId="0" fontId="4" fillId="0" borderId="0" applyFont="1"/>'  # 10 TITLE
    '<xf numFmtId="168" fontId="0" fillId="0" borderId="0" applyNumberFormat="1"/>'  # 11 DEC
    '<xf numFmtId="0" fontId="2" fillId="3" borderId="0" applyFont="1" applyFill="1"/>'  # 12 IN_TEXT
    '<xf numFmtId="165" fontId="1" fillId="0" borderId="1" applyNumberFormat="1" applyFont="1" applyBorder="1"/>'  # 13
    '<xf numFmtId="0" fontId="5" fillId="0" borderId="0" applyFont="1"/>'  # 14 NOTE
    '<xf numFmtId="166" fontId="2" fillId="3" borderId="0" applyNumberFormat="1" applyFont="1" applyFill="1"/>'  # 15
    '<xf numFmtId="169" fontId="0" fillId="0" borderId="0" applyNumberFormat="1"/>'  # 16 PRICE
    "</cellXfs>"
    '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
    "</styleSheet>"
)
