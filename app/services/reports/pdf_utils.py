from xml.sax.saxutils import escape

from reportlab.platypus import Table


def safe_text(value):
    # Paragraph text is parsed as markup, so a bare "&" in data was mangled
    # ("R&D" printed as "R&D;") and a "<" could fail the whole report.
    if value is None:
        return ""
    return escape(value if isinstance(value, str) else str(value))


def allow_oversized_rows(table, doc):
    # ReportLab keeps table rows whole, so a row taller than a page raised
    # LayoutError and failed the whole report. Only a table that has such a row
    # is allowed to continue a row onto the next page; tables whose rows fit
    # keep their usual layout.
    frame_height = doc.height - 12  # the page frame pads 6pt top and bottom
    table.wrap(doc.width - 12, frame_height)
    repeat = table.repeatRows or 0
    header_height = sum(table._rowHeights[:repeat])
    if max(table._rowHeights[repeat:], default=0) > frame_height - header_height:
        _enable_split_in_row(table)


def _enable_split_in_row(table):
    # Nested tables need the setting too: with it on the outer table alone,
    # ReportLab loops forever trying to split the row.
    table.splitInRow = 1
    for row in table._cellvalues:
        for cell in row:
            for flowable in cell if isinstance(cell, (list, tuple)) else [cell]:
                if isinstance(flowable, Table):
                    _enable_split_in_row(flowable)
