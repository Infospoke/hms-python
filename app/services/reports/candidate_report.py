import io
import json
import os
import math
import datetime
from app.models import ProctoringEventType

import matplotlib

matplotlib.use("Agg")

from reportlab.lib.pagesizes import A4


def safe_float(val, default=0.0):
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except:
        return default


from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

if os.path.exists("static/fonts/Roboto-Regular.ttf"):
    pdfmetrics.registerFont(TTFont("Roboto", "static/fonts/Roboto-Regular.ttf"))
    pdfmetrics.registerFont(TTFont("Roboto-Bold", "static/fonts/Roboto-Bold.ttf"))

from app.core import config as consts

DARK_BLUE = colors.HexColor("#122554")
LIGHT_BLUE_BG = colors.HexColor("#F4F6F9")
BORDER_COLOR = colors.HexColor("#D1D5DB")
TEXT_PRIMARY = colors.HexColor("#1F2937")
TEXT_SECONDARY = colors.HexColor("#6B7280")
GREEN_SUCCESS = colors.HexColor("#16A34A")
GREEN_BG = colors.HexColor("#DCFCE7")
YELLOW_WARN = colors.HexColor("#FBBF24")
RED_DANGER = colors.HexColor("#DC2626")


GREY_BG = colors.HexColor("#F0F0F0")
GREEN = colors.HexColor("#228B22")
BLUE = colors.HexColor("#1E90FF")
ORANGE = colors.HexColor("#FF8C00")
RED = colors.HexColor("#B22222")
YELLOW = colors.HexColor("#FFD700")

try:
    pdfmetrics.registerFont(TTFont("SegoeEmoji", "C:\\Windows\\Fonts\\seguiemj.ttf"))
    emoji_font = "SegoeEmoji"
except Exception:
    emoji_font = "Helvetica"

LOGO_PATH = "./static/icons/home-logo.svg"


def format_date(dt_obj):
    if not dt_obj:
        return "N/A"
    if isinstance(dt_obj, str):
        try:
            dt_obj = datetime.datetime.fromisoformat(dt_obj)
        except:
            return dt_obj
    return dt_obj.strftime("%d %b %Y | %I:%M %p")


def list_to_bullets(items, style):
    if not items:
        return Paragraph("N/A", style)
    bullets = "<br/>".join(
        [f"&bull; {str(i).strip()}" for i in items if str(i).strip()]
    )
    return Paragraph(bullets, style)


def get_severity_color(proc):

    if (
        proc.event_type == ProctoringEventType.visual_violation
        and "Cell Phone Detected" in proc.details
    ):
        return RED_DANGER
    elif proc.event_type != ProctoringEventType.visual_violation:
        return YELLOW_WARN

    return YELLOW_WARN


def safe_int(val, default=0):
    try:
        if val is None:
            return default
        f_val = float(val)
        if math.isnan(f_val) or math.isinf(f_val):
            return default
        return int(f_val)
    except:
        return default


def generate_comprehensive_report(data: dict) -> io.BytesIO:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=25,
        leftMargin=25,
        topMargin=25,
        bottomMargin=35,
    )

    j_app = data.get("job_application")
    j_details = data.get("job_details")
    j_meta = data.get("job_meta")
    r_anal = data.get("resume_analysis")
    i_sess = data.get("interview_session")
    i_anal = data.get("interview_analysis")
    qna_list = data.get("qna_list", [])
    procs = data.get("proctoring_logs", [])

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "Title",
        parent=styles["Heading1"],
        fontName="Roboto-Bold",
        fontSize=18,
        textColor=DARK_BLUE,
        alignment=TA_RIGHT,
    )
    subtitle_style = ParagraphStyle(
        "Sub",
        parent=styles["Normal"],
        fontName="Roboto",
        fontSize=10,
        textColor=TEXT_SECONDARY,
        alignment=TA_RIGHT,
    )

    banner_style = ParagraphStyle(
        "Banner",
        parent=styles["Normal"],
        fontName="Roboto-Bold",
        fontSize=12,
        textColor=colors.white,
    )
    subbanner_style = ParagraphStyle(
        "SubBanner",
        parent=styles["Normal"],
        fontName="Roboto-Bold",
        fontSize=11,
        textColor=DARK_BLUE,
        keepWithNext=True,
        spaceAfter=4,
    )

    th_style = ParagraphStyle(
        "TH",
        parent=styles["Normal"],
        fontName="Roboto-Bold",
        fontSize=9,
        textColor=DARK_BLUE,
        alignment=TA_CENTER,
    )
    th_left = ParagraphStyle("THL", parent=th_style, alignment=TA_LEFT)
    th_center = ParagraphStyle("THC", parent=th_style, alignment=TA_CENTER)

    td_style = ParagraphStyle(
        "TD",
        parent=styles["Normal"],
        fontName="Roboto",
        fontSize=9,
        textColor=TEXT_PRIMARY,
        leading=12,
    )
    td_bold = ParagraphStyle("TDBold", parent=td_style, fontName="Roboto-Bold")
    td_center = ParagraphStyle("TDCenter", parent=td_style, alignment=TA_CENTER)

    label_style = ParagraphStyle(
        "Lbl",
        parent=styles["Normal"],
        fontName="Roboto-Bold",
        fontSize=9,
        textColor=DARK_BLUE,
    )

    story = []

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
    report_title = Paragraph("CANDIDATE REPORT", title_style)

    header_table = Table(
        [[comp_title, [report_title]]], colWidths=[3.2 * inch, 4.3 * inch]
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
    story.append(Spacer(1, 10))

    story.append(
        Table(
            [[Paragraph("1. Candidate Overview", banner_style)]],
            colWidths=[7.2 * inch],
            style=[
                ("BACKGROUND", (0, 0), (-1, -1), DARK_BLUE),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
            ],
        )
    )

    c_name = "N/A"
    c_email = "N/A"
    c_phone = "N/A"
    c_app_id = f"{(j_app.id if j_app else 0)}"
    c_job = j_meta.job_title if j_meta else "N/A"
    c_req_id = j_meta.job_code if j_meta else "N/A"
    c_dept = "N/A"
    c_loc = j_meta.job_location if j_meta else "N/A"

    if r_anal:
        c_name = r_anal.candidate_name or c_name
        c_email = r_anal.email or c_email
        c_phone = r_anal.contact_number or c_phone
    elif j_app:
        c_name = f"{j_app.first_name} {j_app.last_name or ''}".strip()
        c_email = j_app.email or c_email
        c_phone = j_app.ph_no or c_phone

    c_date = format_date(j_app.created_date if j_app else None)

    c_city_country = "N/A"
    if j_meta:
        loc_parts = []
        if getattr(j_meta, "job_location", None):
            loc_parts.append(j_meta.job_location)
        if getattr(j_meta, "job_country", None):
            loc_parts.append(j_meta.job_country)
        if loc_parts:
            c_city_country = ", ".join(loc_parts)

    def make_icon_block(icon_path, text_html):
        if not os.path.exists(icon_path):
            return Paragraph(text_html, td_style)

        img = Image(icon_path, width=12, height=12)
        t = Table([[img, Paragraph(text_html, td_style)]], colWidths=[18, None])
        t.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (0, 0), 6),
                    (
                        "TOPPADDING",
                        (0, 0),
                        (0, 0),
                        2,
                    ),
                ]
            )
        )
        return t

    col1_items = [
        make_icon_block("static/icons/user.png", c_name),
        Spacer(1, 8),
        make_icon_block("static/icons/email.png", c_email),
        Spacer(1, 3),
        make_icon_block("static/icons/phone.png", c_phone),
        Spacer(1, 3),
        make_icon_block("static/icons/location.png", c_city_country),
        Spacer(1, 12),
        Paragraph(f"<font>Candidate ID: {c_app_id}</font>", td_style),
    ]

    col2_items = [
        make_icon_block(
            "static/icons/calendar.png",
            f"<font color='#122554'><b>Application Date</b></font><br/><font color='#4B5563'>{c_date}</font>",
        ),
        Spacer(1, 10),
        make_icon_block(
            "static/icons/briefcase.png",
            f"<font color='#122554'><b>Applied For</b></font><br/><font color='#4B5563'>{c_job}</font>",
        ),
        Spacer(1, 10),
        make_icon_block(
            "static/icons/tag.png",
            f"<font color='#122554'><b>Job Code</b></font><br/><font color='#4B5563'>{c_req_id}</font>",
        ),
    ]

    col3_items = [
        make_icon_block(
            "static/icons/building.png",
            f"<font color='#122554'><b>Department</b></font><br/><font color='#4B5563'>{c_dept}</font>",
        ),
        Spacer(1, 10),
        make_icon_block(
            "static/icons/location.png",
            f"<font color='#122554'><b>Location</b></font><br/><font color='#4B5563'>{c_loc}</font>",
        ),
        Spacer(1, 10),
        make_icon_block(
            "static/icons/clock.png",
            f"<font color='#122554'><b>Employment Type</b></font><br/><font color='#4B5563'>Full-time</font>",
        ),
    ]

    c_overview_data = [[col1_items, col2_items, col3_items]]

    t_ov = Table(c_overview_data, colWidths=[2.6 * inch, 2.3 * inch, 2.3 * inch])
    t_ov.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1, BORDER_COLOR),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("PADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    story.append(t_ov)
    story.append(Spacer(1, 10))

    story.append(
        Table(
            [[Paragraph("2. Hiring Stages Timeline", banner_style)]],
            colWidths=[7.2 * inch],
            style=[
                ("BACKGROUND", (0, 0), (-1, -1), DARK_BLUE),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
            ],
        )
    )
    not_completed_msg = "<font size=7 color='#9CA3AF'>Pending</font>"

    t1_date = c_date
    t2_date = format_date(r_anal.processed_at) if r_anal else not_completed_msg
    t3_date = format_date(i_sess.created_date) if i_sess else not_completed_msg
    t4_date = not_completed_msg

    if (
        i_anal
        and getattr(i_anal, "status", None)
        and i_anal.status.lower() == "completed"
    ):
        t4_date = format_date(
            getattr(i_anal, "updated_date", None)
            or (getattr(i_sess, "created_date", None) if i_sess else None)
        )

    def get_timeline_icon(path, is_arrow=False):
        if is_arrow:
            return Image(path, width=40, height=12) if os.path.exists(path) else ""
        return Image(path, width=42, height=42) if os.path.exists(path) else ""

    arrow_icon = get_timeline_icon("static/icons/arrow.png", is_arrow=True)

    tl_data = [
        [
            get_timeline_icon("static/icons/t1.png"),
            arrow_icon,
            get_timeline_icon("static/icons/t2.png"),
            arrow_icon,
            get_timeline_icon("static/icons/t3.png"),
            arrow_icon,
            get_timeline_icon("static/icons/t4.png"),
        ],
        [
            Paragraph("<b>Application Submitted</b>", td_center),
            "",
            Paragraph("<b>Resume Screening</b>", td_center),
            "",
            Paragraph("<b>AI Interview</b>", td_center),
            "",
            Paragraph("<b>Completed</b>", td_center),
        ],
        [
            Paragraph(f"<font size=8 color='#6B7280'>{t1_date}</font>", td_center),
            "",
            Paragraph(f"<font size=8 color='#6B7280'>{t2_date}</font>", td_center),
            "",
            Paragraph(f"<font size=8 color='#6B7280'>{t3_date}</font>", td_center),
            "",
            Paragraph(f"<font size=8 color='#6B7280'>{t4_date}</font>", td_center),
        ],
    ]
    tl_table = Table(
        tl_data,
        colWidths=[
            1.4 * inch,
            0.53 * inch,
            1.4 * inch,
            0.53 * inch,
            1.4 * inch,
            0.53 * inch,
            1.4 * inch,
        ],
    )
    tl_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1, BORDER_COLOR),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, 0), 16),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
                ("TOPPADDING", (0, 1), (-1, 1), 6),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 0),
                ("TOPPADDING", (0, 2), (-1, 2), 2),
                ("BOTTOMPADDING", (0, 2), (-1, 2), 16),
            ]
        )
    )
    story.append(tl_table)
    story.append(Spacer(1, 10))

    if r_anal:
        story.append(
            Table(
                [[Paragraph("3. Resume Screening Details", banner_style)]],
                colWidths=[7.2 * inch],
                style=[
                    ("BACKGROUND", (0, 0), (-1, -1), DARK_BLUE),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                ],
            )
        )

    s_date = t2_date
    s_score = (
        f"{r_anal.final_score}%"
        if (r_anal and r_anal.final_score is not None)
        else "N/A"
    )
    q_match = (
        f"{r_anal.education_score}%"
        if (r_anal and r_anal.education_score is not None)
        else "N/A"
    )
    e_match = (
        f"{r_anal.experience_score}%"
        if (r_anal and r_anal.experience_score is not None)
        else "N/A"
    )
    k_match = (
        f"{r_anal.keywords_match}%"
        if (r_anal and r_anal.keywords_match is not None)
        else "N/A"
    )
    outcome = r_anal.recommendation_decision if r_anal else "N/A"
    display_outcome = outcome
    out_color = TEXT_PRIMARY.hexval()
    if outcome and isinstance(outcome, str):
        val = outcome.capitalize().strip()
        if val == "Hire":
            out_color = GREEN_SUCCESS.hexval()
            display_outcome = "Shortlisted for AI Interview"
        elif val == "Consider":
            out_color = YELLOW_WARN.hexval()
            display_outcome = "Shortlisted for AI Interview"
        elif val == "Reject":
            out_color = RED_DANGER.hexval()
            display_outcome = "Not Shortlisted"

    matched_sk = r_anal.tb_matching_skills if r_anal else []
    highlights = r_anal.tb_strengths if r_anal else []
    if not highlights and r_anal and r_anal.tb_education_highlights:
        highlights = r_anal.tb_education_highlights

    left_table_data = [
        [
            Paragraph("<b>Resume Screening Date & Time</b>", label_style),
            Paragraph(s_date, td_style),
        ],
        [
            Paragraph("<b>Screened By</b>", label_style),
            Paragraph("AI Resume Screening Engine", td_style),
        ],
        [
            Paragraph("<b>Overall Match Score</b>", label_style),
            Paragraph(s_score, td_style),
        ],
        [
            Paragraph("<b>Qualification Match</b>", label_style),
            Paragraph(q_match, td_style),
        ],
        [
            Paragraph("<b>Experience Match</b>", label_style),
            Paragraph(e_match, td_style),
        ],
        [
            Paragraph("<b>Key Skills Match</b>", label_style),
            Paragraph(k_match, td_style),
        ],
        [
            Paragraph("<b>Screening Outcome</b>", label_style),
            Paragraph(
                f"<font color='{out_color}'><b>{display_outcome}</b></font>",
                td_style,
            ),
        ],
    ]
    t_left = Table(left_table_data, colWidths=[1.5 * inch, 1.8 * inch])
    t_left.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, -2), 0.5, BORDER_COLOR),
                ("BACKGROUND", (0, 0), (0, -1), LIGHT_BLUE_BG),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("PADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )

    mid_table_data = [
        [Paragraph("<b>Matched Skills</b>", label_style)],
        [list_to_bullets(matched_sk, td_style)],
    ]
    t_mid = Table(mid_table_data, colWidths=[1.8 * inch])
    t_mid.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, BORDER_COLOR),
                ("BACKGROUND", (0, 0), (0, 0), LIGHT_BLUE_BG),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 1), (0, 1), 40),
            ]
        )
    )

    right_table_data = [
        [
            Paragraph(
                "<b>Resume Highlights</b> <font color='#6B7280'>(Extracted by AI)</font>",
                label_style,
            )
        ],
        [list_to_bullets(highlights, td_style)],
    ]
    t_right = Table(right_table_data, colWidths=[2.1 * inch])
    t_right.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, BORDER_COLOR),
                ("BACKGROUND", (0, 0), (0, 0), LIGHT_BLUE_BG),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )

    box3_data = [[t_left, t_mid, t_right]]
    box3 = Table(box3_data, colWidths=[3.3 * inch, 1.8 * inch, 2.1 * inch])
    box3.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1, BORDER_COLOR),
                ("LINEBEFORE", (1, 0), (-1, -1), 0.5, BORDER_COLOR),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    if r_anal:
        story.append(box3)
        story.append(Spacer(1, 10))

    if i_anal:
        story.append(
            Table(
                [[Paragraph("4. AI Interview Details", banner_style)]],
                colWidths=[7.2 * inch],
                style=[
                    ("BACKGROUND", (0, 0), (-1, -1), DARK_BLUE),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                ],
            )
        )

        i_date = t3_date
        raw_exp = (
            r_anal.experience_level
            if r_anal and r_anal.experience_level
            else "Intermediate"
        )
        i_diff = "Medium"
        if raw_exp == "Beginner":
            i_diff = "Easy"
        elif raw_exp == "Experienced":
            i_diff = "Hard"
        i_score = (
            f"{i_anal.total_score}%"
            if (i_anal and i_anal.total_score is not None)
            else "N/A"
        )
        i_model = consts.GEMINI_MODEL_FOR_AI_INTERVIEWER
        i_mode = "Video + Audio"
        i_rec = getattr(i_anal, "recommendation", "N/A") or "N/A"
        if isinstance(i_rec, str):
            i_rec = i_rec.capitalize().strip()
        i_rec_color = TEXT_PRIMARY.hexval()
        if i_rec and isinstance(i_rec, str):
            val = i_rec
            if val in ("Hire", "Strong hire"):
                i_rec_color = GREEN_SUCCESS.hexval()
            elif val == "Consider":
                i_rec_color = YELLOW_WARN.hexval()
            elif val == "Reject":
                i_rec_color = RED_DANGER.hexval()

        i_header_data = [
            [
                Paragraph("<b>AI Interview Date & Time</b>", label_style),
                Paragraph(i_date, td_style),
                Paragraph("<b>AI Interviewer (LLM Model)</b>", label_style),
                Paragraph(i_model, td_style),
            ],
            [
                Paragraph("<b>Interview Difficulty</b>", label_style),
                Paragraph(i_diff, td_style),
                Paragraph("<b>Interview Mode</b>", label_style),
                Paragraph(i_mode, td_style),
            ],
            [
                Paragraph("<b>Overall Performance Score</b>", label_style),
                Paragraph(f"<b>{i_score}</b>", td_style),
                Paragraph("<b>Recommendation</b>", label_style),
                Paragraph(
                    f"<font color='{i_rec_color}'><b>{i_rec}</b></font>", td_style
                ),
            ],
        ]
        t_ih = Table(
            i_header_data, colWidths=[1.8 * inch, 1.8 * inch, 1.8 * inch, 1.8 * inch]
        )
        t_ih.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                    ("BACKGROUND", (0, 0), (0, -1), LIGHT_BLUE_BG),
                    ("BACKGROUND", (2, 0), (2, -1), LIGHT_BLUE_BG),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("PADDING", (0, 0), (-1, -1), 6),
                    ("BOX", (0, 0), (-1, -1), 1, BORDER_COLOR),
                ]
            )
        )
        story.append(t_ih)
        story.append(Spacer(1, 6))

        story.append(
            Paragraph(
                "4.1 Questions Asked by AI, Candidate Replies & AI Evaluation",
                subbanner_style,
            )
        )

        qna_table_data = [
            [
                Paragraph("<b>No.</b>", th_center),
                Paragraph("<b>Question Asked by AI (LLM)</b>", th_center),
                Paragraph("<b>Candidate Reply (Captured)</b>", th_center),
                Paragraph("<b>AI Evaluation</b>", th_center),
            ]
        ]

        qna_count = 1
        for q in qna_list:
            eval_text = "Good"
            score_val = "N/A"
            try:
                if q.ai_analysis:
                    eval_text = q.ai_analysis.get(
                        "explanation", q.ai_analysis.get("feedback", eval_text)
                    )
                    score_val = f"{int(q.ai_analysis.get('overall', 'N/A')//10)}/10"
            except:
                pass

            styled_eval = f"{eval_text}<br/><br/><font color='{GREEN_SUCCESS.hexval()}'><b>Score: {score_val}</b></font>"

            row = [
                Paragraph(str(qna_count), td_center),
                Paragraph(q.question_text, td_style),
                Paragraph(q.answer_text, td_style),
                Paragraph(styled_eval, td_style),
            ]
            qna_table_data.append(row)
            qna_count += 1

        if not qna_list:
            qna_table_data.append(
                [Paragraph("No QnA data available.", td_center), "", "", ""]
            )

        t_qna = Table(
            qna_table_data,
            colWidths=[0.4 * inch, 2.2 * inch, 2.3 * inch, 2.3 * inch],
            repeatRows=1,
        )
        t_qna.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                    ("BACKGROUND", (0, 0), (-1, 0), LIGHT_BLUE_BG),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("PADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        if not qna_list:
            t_qna.setStyle(TableStyle([("SPAN", (0, 1), (3, 1))]))

        story.append(t_qna)
        story.append(Spacer(1, 10))

        story.append(
            Table(
                [
                    [
                        Paragraph(
                            "5. Violations & Concerns Detected During AI Interview",
                            banner_style,
                        )
                    ]
                ],
                colWidths=[7.2 * inch],
                style=[
                    ("BACKGROUND", (0, 0), (-1, -1), DARK_BLUE),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                ],
            )
        )

        v_table_data = [
            [
                Paragraph("<b>No.</b>", th_left),
                Paragraph("<b>Violation Type</b>", th_left),
                Paragraph("<b>Description</b>", th_left),
                Paragraph("<b>Severity</b>", th_center),
                Paragraph("<b>Timestamp</b>", th_center),
            ]
        ]

        def get_sev_weight(p):
            sc = get_severity_color(p)
            if sc == RED_DANGER:
                return 3
            if sc == YELLOW_WARN:
                return 2
            return 1

        sorted_procs = sorted(procs, key=get_sev_weight, reverse=True)[:10]

        v_count = 1
        for p in sorted_procs:
            sev_color = get_severity_color(p or "Low")
            sev_badge = (
                f"<font color='{sev_color.hexval()}'><b>High</b></font>"
                if sev_color == RED_DANGER
                else (
                    f"<font color='{sev_color.hexval()}'><b>Medium</b></font>"
                    if sev_color == YELLOW_WARN
                    else f"<font color='{sev_color.hexval()}'><b>Low</b></font>"
                )
            )
            ts = (
                p.timestamp.strftime("%H:%M:%S")
                if isinstance(p.timestamp, datetime.datetime)
                else "N/A"
            )
            try:
                if isinstance(p.details, list):
                    p_details = ", ".join(p.details)
                elif isinstance(p.details, str) and p.details.startswith("["):
                    parsed = json.loads(p.details)
                    p_details = (
                        ", ".join(parsed) if isinstance(parsed, list) else str(parsed)
                    )
                else:
                    p_details = str(p.details)
            except Exception:
                p_details = str(p.details)

            row = [
                Paragraph(str(v_count), td_style),
                Paragraph(p.event_type, td_style),
                Paragraph(p_details or "Detected event", td_style),
                Paragraph(sev_badge, td_center),
                Paragraph(ts, td_center),
            ]
            v_table_data.append(row)
            v_count += 1

        if not procs:
            v_table_data.append(
                [Paragraph("No violations recorded.", td_center), "", "", "", ""]
            )

        t_v = Table(
            v_table_data,
            colWidths=[0.4 * inch, 1.8 * inch, 3.2 * inch, 0.8 * inch, 1.0 * inch],
            repeatRows=1,
        )
        t_v.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                    ("BACKGROUND", (0, 0), (-1, 0), LIGHT_BLUE_BG),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("PADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        if not procs:
            t_v.setStyle(TableStyle([("SPAN", (0, 1), (4, 1))]))
        story.append(t_v)
        story.append(Spacer(1, 4))

        story.append(
            Paragraph(
                "<b>Note:</b> Violations are detected using AI behavioral analysis and may not be 100% accurate.",
                ParagraphStyle("Note", parent=td_style, fontSize=8),
            )
        )
        story.append(Spacer(1, 20))

    def add_page_number(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(DARK_BLUE)
        canvas.rect(0, 0, A4[0], 25, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Roboto", 9)
        canvas.drawString(
            30,
            10,
            f"This report was automatically generated on {datetime.datetime.now().strftime('%d %b %Y | %I:%M %p')}",
        )
        canvas.drawRightString(A4[0] - 30, 10, f"Page {doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    buffer.seek(0)
    return buffer
