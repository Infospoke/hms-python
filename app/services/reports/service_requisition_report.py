import io
import math
import datetime
import os

from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
    Flowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

NAVY_BLUE = colors.HexColor("#0a2540")
TEXT_MUTED = colors.HexColor("#001858")
BORDER_COLOR = colors.HexColor("#cbd5e1")

if os.path.exists("static/fonts/Roboto-Regular.ttf"):
    pdfmetrics.registerFont(TTFont("Roboto", "static/fonts/Roboto-Regular.ttf"))
    pdfmetrics.registerFont(TTFont("Roboto-Bold", "static/fonts/Roboto-Bold.ttf"))


def format_date(dt_obj):
    if not dt_obj:
        return datetime.datetime.now().strftime("%d %b %Y | %I:%M %p")
    if isinstance(dt_obj, str):
        if dt_obj == "N/A":
            return "-"
        try:
            dt_obj = datetime.datetime.fromisoformat(dt_obj)
        except:
            return dt_obj
    if isinstance(dt_obj, datetime.datetime):
        return dt_obj.strftime("%d %b %Y | %I:%M %p")
    if isinstance(dt_obj, datetime.date):
        return dt_obj.strftime("%d %b %Y")
    return str(dt_obj)


def format_inr(amount):
    if amount == "N/A":
        return amount

    amount = int(amount)
    s = str(amount)

    if len(s) <= 3:
        return s

    last3 = s[-3:]
    rest = s[:-3]

    parts = []
    while len(rest) > 2:
        parts.insert(0, rest[-2:])
        rest = rest[:-2]

    if rest:
        parts.insert(0, rest)

    return "₹ " + ",".join(parts) + "," + last3


class IdAndBadge(Flowable):
    def __init__(self, id_text, badge_text, badge_color):
        Flowable.__init__(self)
        self.id_text = id_text
        self.badge_text = badge_text
        self.badge_color = badge_color
        self.width = 350
        self.height = 22

    def draw(self):
        self.canv.saveState()
        self.canv.setFont("Helvetica-Bold", 14)
        self.canv.setFillColor(colors.HexColor("#0a2540"))
        self.canv.drawString(0, 4, self.id_text)

        id_width = self.canv.stringWidth(self.id_text, "Helvetica-Bold", 14)

        badge_x = id_width + 12
        badge_w = self.canv.stringWidth(self.badge_text, "Helvetica-Bold", 8.5) + 20
        badge_h = 18
        badge_y = 0

        self.canv.setFillColor(colors.HexColor("#eff6ff"))
        self.canv.setStrokeColor(colors.HexColor("#eff6ff"))
        self.canv.roundRect(
            badge_x, badge_y, badge_w, badge_h, badge_h / 2, fill=True, stroke=True
        )

        self.canv.setFillColor(colors.HexColor(self.badge_color))
        self.canv.setFont("Helvetica-Bold", 8.5)
        self.canv.drawCentredString(
            badge_x + badge_w / 2, badge_y + (badge_h - 8.5) / 2 + 1.5, self.badge_text
        )

        self.canv.restoreState()


class RoundedCard(Flowable):
    def __init__(self, table_obj, bg_color, border_color, radius=6):
        Flowable.__init__(self)
        self.table_obj = table_obj
        self.bg_color = bg_color
        self.border_color = border_color
        self.radius = radius
        self.width, self.height = table_obj.wrap(0, 0)

    def draw(self):
        self.canv.saveState()
        self.canv.setFillColor(self.bg_color)
        self.canv.setStrokeColor(self.border_color)
        self.canv.setLineWidth(1)
        self.canv.roundRect(
            0, 0, self.width, self.height, self.radius, fill=True, stroke=True
        )
        self.table_obj.drawOn(self.canv, 0, 0)
        self.canv.restoreState()


class ColoredDot(Flowable):
    def __init__(self, color_hex, size=6):
        Flowable.__init__(self)
        self.color_hex = color_hex
        self.size = size
        self.width = size + 4
        self.height = size

    def draw(self):
        self.canv.saveState()
        self.canv.setFillColor(colors.HexColor(self.color_hex))
        self.canv.circle(
            self.width / 2, self.height / 2, self.size / 2, fill=True, stroke=False
        )
        self.canv.restoreState()


class ApprovalPipelineFlowable(Flowable):
    def __init__(self, width=517):
        Flowable.__init__(self)
        self.width = width
        self.height = 115
        self.radius = 4

    def draw(self):
        canv = self.canv
        canv.saveState()

        canv.setFillColor(colors.white)
        canv.setStrokeColor(colors.HexColor("#cbd5e1"))
        canv.setLineWidth(1)
        canv.roundRect(
            0, 0, self.width, self.height, self.radius, fill=True, stroke=True
        )

        header_height = 20
        header_y = self.height - header_height
        canv.setFillColor(colors.HexColor("#0a2540"))
        canv.roundRect(
            0, header_y, self.width, header_height, self.radius, fill=True, stroke=False
        )
        canv.rect(0, header_y, self.width, self.radius, fill=True, stroke=False)

        canv.setFillColor(colors.white)
        canv.setFont("Helvetica-Bold", 8)
        canv.drawString(14, header_y + 6, "1. APPROVAL PIPELINE")

        left_width = 410
        nodes = [
            {
                "num": "1",
                "role": "Hiring Manager",
                "name": "Alex Kumar",
                "status": "Created",
                "status_color": "#10b981",
                "bg": "#1d4ed8",
            },
            {
                "num": "2",
                "role": "Department Head",
                "name": "Rohit Sharma",
                "status": "Upcoming",
                "status_color": "#475569",
                "bg": "#64748b",
            },
            {
                "num": "3",
                "role": "HRBP",
                "name": "Priya Mehta",
                "status": "Upcoming",
                "status_color": "#475569",
                "bg": "#64748b",
            },
            {
                "num": "4",
                "role": "Finance",
                "name": "Neha Verma",
                "status": "Upcoming",
                "status_color": "#475569",
                "bg": "#64748b",
            },
        ]

        cy = header_y - 25
        node_radius = 12
        spacing = left_width / len(nodes)
        node_xs = [spacing / 2 + i * spacing for i in range(len(nodes))]

        canv.setStrokeColor(colors.HexColor("#94a3b8"))
        canv.setLineWidth(1)
        for i in range(len(nodes) - 1):
            x1 = node_xs[i] + node_radius
            x2 = node_xs[i + 1] - node_radius
            canv.line(x1, cy, x2, cy)
            mid_x = (x1 + x2) / 2
            canv.line(mid_x - 3, cy - 3, mid_x + 3, cy)
            canv.line(mid_x - 3, cy + 3, mid_x + 3, cy)

        for i, node in enumerate(nodes):
            cx = node_xs[i]

            canv.setFillColor(colors.HexColor(node["bg"]))
            canv.setStrokeColor(colors.HexColor(node["bg"]))
            canv.circle(cx, cy, node_radius, fill=True, stroke=True)

            canv.setFillColor(colors.white)
            canv.setFont("Helvetica-Bold", 10)
            canv.drawCentredString(cx, cy - 3.5, node["num"])

            ty = cy - 23
            canv.setFillColor(colors.HexColor("#0f172a"))
            canv.setFont("Helvetica-Bold", 8)
            canv.drawCentredString(cx, ty, node["role"])

            ty -= 13
            canv.setFillColor(colors.HexColor("#0f172a"))
            canv.setFont("Helvetica-Bold", 7.5)
            canv.drawCentredString(cx, ty, node["name"])

            ty -= 13
            canv.setFillColor(colors.HexColor(node["status_color"]))
            canv.setFont("Helvetica", 8)
            canv.drawCentredString(cx, ty, node["status"])

        vx = left_width
        canv.setStrokeColor(colors.HexColor("#cbd5e1"))
        canv.line(vx, 10, vx, header_y - 10)

        legend_x = vx + 25
        legend_y = header_y - 20
        legends = [
            {"label": "Pending", "color": "#1d4ed8", "has_icon": False},
            {"label": "Upcoming", "color": "#64748b", "has_icon": False},
            {
                "label": "Approved",
                "color": "#10b981",
                "has_icon": True,
                "icon": "check",
            },
            {
                "label": "Rejected",
                "color": "#ef4444",
                "has_icon": True,
                "icon": "cross",
            },
        ]

        for leg in legends:
            canv.setFillColor(colors.HexColor(leg["color"]))
            canv.setStrokeColor(colors.HexColor(leg["color"]))
            canv.circle(legend_x, legend_y, 4, fill=True, stroke=True)

            if leg["has_icon"]:
                canv.setStrokeColor(colors.white)
                canv.setLineWidth(0.8)
                if leg["icon"] == "check":
                    canv.line(legend_x - 1.5, legend_y, legend_x - 0.5, legend_y - 1.5)
                    canv.line(
                        legend_x - 0.5, legend_y - 1.5, legend_x + 1.5, legend_y + 1.5
                    )
                elif leg["icon"] == "cross":
                    canv.line(
                        legend_x - 1.5, legend_y - 1.5, legend_x + 1.5, legend_y + 1.5
                    )
                    canv.line(
                        legend_x - 1.5, legend_y + 1.5, legend_x + 1.5, legend_y - 1.5
                    )

            canv.setFillColor(colors.HexColor("#0f172a"))
            canv.setFont("Helvetica", 8)
            canv.drawString(legend_x + 15, legend_y - 2.5, leg["label"])

            legend_y -= 16

        canv.restoreState()


class SectionHeaderFlowable(Flowable):
    def __init__(self, text, width=517, height=22, radius=4):
        Flowable.__init__(self)
        self.text = text
        self.width = width
        self.height = height
        self.radius = radius

    def draw(self):
        canv = self.canv
        canv.saveState()
        canv.setFillColor(colors.HexColor("#0a2540"))
        canv.roundRect(
            0, 0, self.width, self.height, self.radius, fill=True, stroke=False
        )
        canv.rect(0, 0, self.width, self.radius, fill=True, stroke=False)

        canv.setFillColor(colors.white)
        canv.setFont("Helvetica-Bold", 8.5)
        canv.drawString(14, self.height / 2 - 3, self.text)
        canv.restoreState()


def generate_service_requisition_report(data: dict) -> io.BytesIO:
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=25,
        leftMargin=25,
        topMargin=25,
        bottomMargin=35,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "Title",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        textColor=NAVY_BLUE,
        alignment=TA_RIGHT,
    )

    subtitle_style = ParagraphStyle(
        "Sub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        textColor=TEXT_MUTED,
        alignment=TA_RIGHT,
    )

    logo_style = ParagraphStyle(
        "LogoText",
        parent=styles["Normal"],
        fontName="Helvetica",
        leading=22,
    )

    subtext_style = ParagraphStyle(
        "SubText",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        textColor=colors.HexColor("#001C48"),
        leading=13,
    )

    story = []

    # 1. Left column: Logo + NEXUS HMS text
    try:
        from svglib.svglib import svg2rlg

        logo_drawing = svg2rlg("static/icons/home-logo.svg")
        if logo_drawing:
            logo_drawing.width = 40
            logo_drawing.height = 36
            logo_drawing.scale(0.1, 0.1)
    except Exception:
        logo_drawing = None

    logo_text = [
        Paragraph(
            "<font size=21 color='#0051cf'><b>NEXUS</b></font> <font size=17 color='#6b7280'>HMS</font>",
            logo_style,
        ),
        Spacer(1, 2),
        Paragraph("Smarter Hiring. Better Future.", subtext_style),
    ]

    if logo_drawing:
        logo_table = Table(
            [[logo_drawing, logo_text]], colWidths=[0.55 * inch, 2.3 * inch]
        )
        logo_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        comp_title = logo_table
    else:
        comp_title = logo_text

    # 2. Right column: Report generated date and title
    gen_on = format_date(data.get("generated_on"))
    right_items = [
        Paragraph("SERVICE REQUISITION REPORT", title_style),
        Paragraph(f"Report Generated On: {gen_on}", subtitle_style),
    ]

    header_table = Table(
        [[comp_title, right_items]], colWidths=[3.2 * inch, 4.3 * inch]
    )
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    story.append(header_table)
    story.append(Spacer(1, 12))

    # 3. Next section - Metadata Card

    section_0 = data.get("section_0")
    sr_id_code = section_0.get("sr_id")
    sr_approved = section_0.get("approved")

    status_str = "Pending Approval"
    if sr_approved:
        status_str = "Approved"
        status_color = "#10b981"
    else:
        status_str = "Pending Approval"
        status_color = "#2563eb"

    id_badge_flowable = IdAndBadge(sr_id_code, status_str, status_color)

    lbl_style = ParagraphStyle(
        "MetaLbl",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        textColor=colors.HexColor("#64748b"),
        leading=11,
    )
    val_style = ParagraphStyle(
        "MetaVal",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=colors.HexColor("#0f172a"),
        leading=12,
    )

    def meta_item(icon_name, label, value):
        icon_path = f"static/icons/{icon_name}"
        if not os.path.exists(icon_path):
            icon_path = f"static/icons/user.png"

        img = (
            Image(icon_path, width=12, height=12)
            if os.path.exists(icon_path)
            else Spacer(1, 1)
        )

        if label == "Priority":
            if value == "Standard":
                color = "#10b981"
            elif value == "High":
                color = "#f59e0b"
            elif value == "Critical":
                color = "#ef4444"

            dot_flow = ColoredDot(color, size=6)
            text_para = Paragraph(f"<b>{value}</b>", val_style)
            val_content = Table([[dot_flow, text_para]], colWidths=[12, 1.1 * inch])
            val_content.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ]
                )
            )
        else:
            val_content = Paragraph(f"<b>{value}</b>", val_style)

        content_table = Table(
            [
                [Paragraph(label, lbl_style)],
                [val_content],
            ],
            colWidths=[1.25 * inch],
        )
        content_table.setStyle(
            TableStyle(
                [
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )

        item_table = Table([[img, content_table]], colWidths=[0.23 * inch, 1.2 * inch])
        item_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (0, 0), 2),
                ]
            )
        )
        return item_table

    c_name = section_0.get("creator_name")
    dept = section_0.get("department_name")
    created_on = format_date(section_0.get("created_on"))
    priority = section_0.get("priority")
    target_start = format_date(section_0.get("target_start_date"))

    meta_row = [
        meta_item("user.png", "Created By", c_name),
        meta_item("building.png", "Department", dept),
        meta_item("calendar.png", "Date Created", created_on),
        meta_item("flag1.png", "Priority", priority),
        meta_item("calendar.png", "Target Start Date", target_start),
    ]

    inner_meta_table = Table([meta_row], colWidths=[103.4] * 5)
    inner_meta_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    card_data = [[id_badge_flowable], [Spacer(1, 1)], [inner_meta_table]]

    card_table = Table(card_data, colWidths=[517])
    card_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (0, 0), 14),
            ]
        )
    )

    rounded_card = RoundedCard(
        card_table, colors.white, colors.HexColor("#cbd5e1"), radius=6
    )
    story.append(rounded_card)
    story.append(Spacer(1, 15))

    story.append(ApprovalPipelineFlowable(width=517))
    story.append(Spacer(1, 15))

    # 4. REQUISITION DETAILS Section
    def grid_cell(label, value):
        lbl_style = ParagraphStyle(
            "glbl",
            fontName="Helvetica",
            fontSize=8,
            textColor=colors.HexColor("#475569"),
            leading=10,
        )
        val_style = ParagraphStyle(
            "gval",
            fontName="Roboto-Bold",
            fontSize=8.5,
            textColor=colors.HexColor("#0f172a"),
            leading=10,
        )
        return [
            Paragraph(label, lbl_style),
            Spacer(1, 4),
            Paragraph(value, val_style),
        ]

    section_2 = data.get("section_2")

    grid_data = [
        [
            grid_cell("Job Title", section_2.get("job_title")),
            grid_cell("Business Unit", str(section_2.get("business_unit"))),
            grid_cell("Department", section_2.get("department")),
            grid_cell("Reporting Manager", section_2.get("reporting_manager")),
        ],
        [
            grid_cell("Employment Type", section_2.get("employment_type")),
            grid_cell("Work Mode", section_2.get("work_mode")),
            grid_cell("Location", section_2.get("location")),
            grid_cell(
                "Target Start Date", format_date(section_2.get("target_start_date"))
            ),
        ],
        [
            grid_cell("Number of Openings", str(section_2.get("openings"))),
            grid_cell("Experience", section_2.get("experience")),
            grid_cell("Seniority Level", str(section_2.get("seniority_level"))),
            grid_cell("Priority", section_2.get("priority")),
        ],
    ]

    grid_style = TableStyle(
        [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("INNERGRID", (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e1")),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]
    )

    grid_table = Table(grid_data, colWidths=[517 / 4] * 4, style=grid_style)

    req_card_data = [
        [
            SectionHeaderFlowable(
                "2. REQUISITION DETAILS", width=517, height=22, radius=4
            )
        ],
        [grid_table],
    ]

    req_card_table = Table(req_card_data, colWidths=[517])
    req_card_table.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    rounded_req_card = RoundedCard(
        req_card_table, colors.white, colors.HexColor("#cbd5e1"), radius=4
    )
    story.append(rounded_req_card)
    story.append(Spacer(1, 15))

    section_3 = data.get("section_3")

    # 5. BUSINESS JUSTIFICATION Section
    biz_grid_data = [
        [
            grid_cell("Requisition Type", section_3.get("requisition_type")),
            grid_cell("Replaces Employee", section_3.get("replaces_employee")),
            grid_cell("Impact if Not Filled", section_3.get("impact_if_not_filled")),
        ],
        [grid_cell("Business Case", section_3.get("business_case")), "", "", ""],
    ]

    biz_grid_style = TableStyle(
        [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("INNERGRID", (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e1")),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("SPAN", (0, 1), (2, 1)),
        ]
    )

    biz_grid_table = Table(biz_grid_data, colWidths=[517 / 3] * 3, style=biz_grid_style)

    biz_card_data = [
        [
            SectionHeaderFlowable(
                "3. BUSINESS JUSTIFICATION", width=517, height=22, radius=4
            )
        ],
        [biz_grid_table],
    ]

    biz_card_table = Table(biz_card_data, colWidths=[517])
    biz_card_table.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    rounded_biz_card = RoundedCard(
        biz_card_table, colors.white, colors.HexColor("#cbd5e1"), radius=4
    )
    story.append(rounded_biz_card)
    story.append(Spacer(1, 15))

    # 6. BUDGET & COMPENSATION Section

    section_4 = data.get("section_4")

    comp_grid_data = [
        [
            grid_cell(
                "Salary Band",
                format_inr(section_4.get("minimum_salary"))
                + " - "
                + format_inr(section_4.get("maximum_salary")),
            ),
            grid_cell(
                "Proposed Total Compensation",
                format_inr(section_4.get("proposed_total_compensation")),
            ),
            grid_cell(
                "Annual Hiring Cost", format_inr(section_4.get("annual_hiring_cost"))
            ),
        ],
        [
            grid_cell("Signing Bonus", format_inr(section_4.get("signing_bonus"))),
            grid_cell("Equity / RSU", str(section_4.get("equity"))),
            grid_cell(
                "Relocation Budget", format_inr(section_4.get("relocation_budget"))
            ),
        ],
    ]

    comp_grid_style = TableStyle(
        [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("INNERGRID", (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e1")),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]
    )

    comp_grid_table = Table(
        comp_grid_data, colWidths=[517 / 3] * 3, style=comp_grid_style
    )

    comp_card_data = [
        [
            SectionHeaderFlowable(
                "4. BUDGET & COMPENSATION", width=517, height=22, radius=4
            )
        ],
        [comp_grid_table],
    ]

    comp_card_table = Table(comp_card_data, colWidths=[517])
    comp_card_table.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    rounded_comp_card = RoundedCard(
        comp_card_table, colors.white, colors.HexColor("#cbd5e1"), radius=4
    )
    story.append(rounded_comp_card)
    story.append(Spacer(1, 15))

    # 7. ROLE REQUIREMENTS Section
    section_5 = data.get("section_5")

    role_grid_data = [
        [
            grid_cell("Skills Must Have", section_5.get("skills_must_have")),
            "",
            grid_cell("Nice-to-Have Skills", section_5.get("nice_to_have_skills")),
            "",
        ],
        [
            grid_cell("Education Requirement", section_5.get("education_requirements")),
            "",
            grid_cell("Years of Experience", section_5.get("years_of_experience")),
            grid_cell("Interview Rounds", section_5.get("interview_rounds")),
        ],
        [
            grid_cell(
                "Certifications Required", section_5.get("certifications_required")
            ),
            "",
            grid_cell("Languages", section_5.get("languages")),
            "",
        ],
        [
            grid_cell("Assessment Required", section_5.get("assessment_required")),
            "",
            grid_cell("Travel Requirement", section_5.get("travel_requirements")),
            "",
        ],
    ]

    role_grid_style = TableStyle(
        [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("INNERGRID", (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e1")),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("SPAN", (0, 0), (1, 0)),
            ("SPAN", (2, 0), (3, 0)),
            ("SPAN", (0, 1), (1, 1)),
            ("SPAN", (0, 2), (1, 2)),
            ("SPAN", (2, 2), (3, 2)),
            ("SPAN", (0, 3), (1, 3)),
            ("SPAN", (2, 3), (3, 3)),
        ]
    )

    role_grid_table = Table(
        role_grid_data, colWidths=[517 / 4] * 4, style=role_grid_style
    )

    role_card_data = [
        [SectionHeaderFlowable("5. ROLE REQUIREMENTS", width=517, height=22, radius=4)],
        [role_grid_table],
    ]

    role_card_table = Table(role_card_data, colWidths=[517])
    role_card_table.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    rounded_role_card = RoundedCard(
        role_card_table, colors.white, colors.HexColor("#cbd5e1"), radius=4
    )
    story.append(rounded_role_card)
    story.append(Spacer(1, 15))

    # 8. APPROVAL STAGES SUMMARY Section
    summary_header_style = ParagraphStyle(
        "sum_hdr",
        fontName="Helvetica",
        fontSize=8,
        textColor=colors.HexColor("#64748b"),
        alignment=TA_CENTER,
    )
    summary_cell_bold = ParagraphStyle(
        "sum_bold",
        fontName="Roboto-Bold",
        fontSize=8.5,
        textColor=colors.HexColor("#0f172a"),
        alignment=TA_CENTER,
    )
    summary_cell_normal = ParagraphStyle(
        "sum_norm",
        fontName="Helvetica",
        fontSize=8.5,
        textColor=colors.HexColor("#475569"),
        alignment=TA_CENTER,
    )

    def status_paragraph(text, color_hex):
        return Paragraph(
            f"<b>{text}</b>",
            ParagraphStyle(
                "sum_stat",
                fontName="Roboto-Bold",
                fontSize=8.5,
                textColor=colors.HexColor(color_hex),
                alignment=TA_CENTER,
            ),
        )

    summary_data = [
        [
            Paragraph("Level", summary_header_style),
            Paragraph("Approver", summary_header_style),
            Paragraph("Role", summary_header_style),
            Paragraph("Status", summary_header_style),
            Paragraph("Action On", summary_header_style),
            Paragraph("Comments", summary_header_style),
        ],
        [
            Paragraph("1", summary_cell_bold),
            Paragraph("Alex Kumar", summary_cell_bold),
            Paragraph("Hiring Manager", summary_cell_normal),
            status_paragraph("Created", "#10b981"),
            Paragraph("-", summary_cell_normal),
            Paragraph("-", summary_cell_normal),
        ],
        [
            Paragraph("2", summary_cell_bold),
            Paragraph("Rohit Sharma", summary_cell_bold),
            Paragraph("Department Head", summary_cell_normal),
            status_paragraph("Upcoming", "#475569"),
            Paragraph("-", summary_cell_normal),
            Paragraph("-", summary_cell_normal),
        ],
        [
            Paragraph("3", summary_cell_bold),
            Paragraph("Priya Mehta", summary_cell_bold),
            Paragraph("HRBP", summary_cell_normal),
            status_paragraph("Upcoming", "#475569"),
            Paragraph("-", summary_cell_normal),
            Paragraph("-", summary_cell_normal),
        ],
        [
            Paragraph("4", summary_cell_bold),
            Paragraph("Neha Verma", summary_cell_bold),
            Paragraph("Finance", summary_cell_normal),
            status_paragraph("Upcoming", "#475569"),
            Paragraph("-", summary_cell_normal),
            Paragraph("-", summary_cell_normal),
        ],
    ]

    summary_grid_style = TableStyle(
        [
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("INNERGRID", (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e1")),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]
    )

    summary_table = Table(
        summary_data, colWidths=[40, 110, 110, 80, 87, 90], style=summary_grid_style
    )

    summary_card_data = [
        [
            SectionHeaderFlowable(
                "6. APPROVAL STAGES SUMMARY", width=517, height=22, radius=4
            )
        ],
        [summary_table],
    ]

    summary_card_table = Table(summary_card_data, colWidths=[517])
    summary_card_table.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    rounded_summary_card = RoundedCard(
        summary_card_table, colors.white, colors.HexColor("#cbd5e1"), radius=4
    )
    story.append(rounded_summary_card)
    story.append(Spacer(1, 15))

    # 9. AUDIT INFORMATION Section
    audit_grid_data = [
        [
            grid_cell("Created By", "Alex Kumar"),
            grid_cell("Date Created", "12 May 2025 | 10:15 AM"),
            grid_cell("Last Updated By", "-"),
            grid_cell("Last Updated On", "-"),
        ]
    ]

    audit_grid_style = TableStyle(
        [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("INNERGRID", (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e1")),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]
    )

    audit_grid_table = Table(
        audit_grid_data, colWidths=[517 / 4] * 4, style=audit_grid_style
    )

    audit_card_data = [
        [SectionHeaderFlowable("7. AUDIT INFORMATION", width=517, height=22, radius=4)],
        [audit_grid_table],
    ]

    audit_card_table = Table(audit_card_data, colWidths=[517])
    audit_card_table.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    rounded_audit_card = RoundedCard(
        audit_card_table, colors.white, colors.HexColor("#cbd5e1"), radius=4
    )
    story.append(rounded_audit_card)
    story.append(Spacer(1, 15))

    def add_page_number(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(TEXT_MUTED)
        canvas.drawString(30, 15, "Note: This is a system generated report.")
        canvas.drawRightString(A4[0] - 30, 15, f"Page {doc.page} of 2")
        canvas.restoreState()

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    buffer.seek(0)
    return buffer
