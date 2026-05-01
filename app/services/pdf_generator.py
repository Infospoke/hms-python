import io
import json
import os
import math
import datetime
from datetime import datetime as dt_now
from collections import Counter
from app.models import ProctoringEventType

import base64
from jinja2 import Environment, FileSystemLoader
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

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
    PageBreak,
    Image,
    Image as RLImage,
    HRFlowable,
    Flowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics import renderPDF
from reportlab.graphics.shapes import Drawing, Rect, String, Circle
from svglib.svglib import svg2rlg

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

# Additional colors used by generate_applicants_pdf
GREY_BG = colors.HexColor("#F0F0F0")
GREEN = colors.HexColor("#228B22")
BLUE = colors.HexColor("#1E90FF")
ORANGE = colors.HexColor("#FF8C00")
RED = colors.HexColor("#B22222")
YELLOW = colors.HexColor("#FFD700")

# Try registering Segoe UI Emoji for icons, fallback to Helvetica
try:
    pdfmetrics.registerFont(TTFont('SegoeEmoji', 'C:\\Windows\\Fonts\\seguiemj.ttf'))
    emoji_font = 'SegoeEmoji'
except Exception:
    emoji_font = 'Helvetica'

# SVG Logo Path
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

    try:
        from svglib.svglib import svg2rlg

        logo_drawing = svg2rlg("static/icons/home-logo.svg")
        comp_title = (
            [
                logo_drawing,
                Spacer(1, 6),
                Paragraph(
                    "<font size=11 color='#6B7280'><b>Integrated Solutions LLP</b></font><br/>",
                    styles["Normal"],
                ),
            ]
            if logo_drawing
            else Paragraph(
                "<font size=11 color='#6B7280'><b>Integrated Solutions LLP</b></font><br/>",
                styles["Normal"],
            )
        )
    except Exception:
        comp_title = Paragraph(
            "<font size=11 color='#6B7280'><b>Integrated Solutions LLP</b></font><br/>",
            styles["Normal"],
        )
    report_title = Paragraph("CANDIDATE REPORT", title_style)

    header_table = Table(
        [[comp_title, [report_title]]], colWidths=[2.5 * inch, 4.5 * inch]
    )
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
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
    # c_job = j_details.job_title if j_details else "N/A"
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

    if i_anal and getattr(i_anal, "status", None) and i_anal.status.lower() == "completed":
        t4_date = format_date(
            getattr(i_anal, "updated_date", None) or (getattr(i_sess, "created_date", None) if i_sess else None)
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
    s_score = f"{r_anal.final_score}%" if (r_anal and r_anal.final_score is not None) else "N/A"
    q_match = f"{r_anal.education_score}%" if (r_anal and r_anal.education_score is not None) else "N/A"
    e_match = f"{r_anal.experience_score}%" if (r_anal and r_anal.experience_score is not None) else "N/A"
    k_match = f"{r_anal.keywords_match}%" if (r_anal and r_anal.keywords_match is not None) else "N/A"
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

    matched_sk = r_anal.matching_skills if r_anal else []
    highlights = r_anal.strengths if r_anal else []
    if not highlights and r_anal and r_anal.education_highlights:
        highlights = r_anal.education_highlights

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
        i_score = f"{i_anal.total_score}%" if (i_anal and i_anal.total_score is not None) else "N/A"
        i_model = consts.GEMINI_MODEL_FOR_AI_INTERVIEWER
        i_mode = "Video + Audio"
        i_rec = getattr(i_anal, "recommendation", "N/A") or "N/A"
        if isinstance(i_rec, str):
            i_rec = i_rec.capitalize().strip()
        i_rec_color = TEXT_PRIMARY.hexval()
        if i_rec and isinstance(i_rec, str):
            val = i_rec
            if val == "Hire":
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


class RoundedBoxFlowable(Flowable):
    def __init__(self, content, width, radius=5, strokeColor=colors.lightgrey, fillColor=None, padding=0):
        Flowable.__init__(self)
        self.content = content
        self.width = width
        self.radius = radius
        self.strokeColor = strokeColor
        self.fillColor = fillColor
        self.padding = padding

    def wrap(self, availWidth, availHeight):
        self.w, self.h = self.content.wrap(self.width - 2*self.padding, availHeight)
        self.w = self.width
        self.h += 2*self.padding
        return self.w, self.h

    def draw(self):
        self.canv.saveState()
        if self.fillColor:
            self.canv.setFillColor(self.fillColor)
        self.canv.setStrokeColor(self.strokeColor)
        self.canv.roundRect(0, 0, self.w, self.h, self.radius, stroke=1, fill=1 if self.fillColor else 0)
        self.content.drawOn(self.canv, self.padding, self.padding)
        self.canv.restoreState()

# --- Matplotlib Chart Generators ---

def _buf_from_fig(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight', dpi=150, transparent=True)
    plt.close(fig)
    buf.seek(0)
    return buf

def generate_bar_chart(x_labels, values, label='No. of Applications', num_ticks=5):
    if not values:
        values = [0]
        x_labels = ["N/A"]
    
    fig, ax = plt.subplots(figsize=(5, 3))
    x_pos = range(len(values))
    
    ax.bar(x_pos, [safe_float(v) for v in values], color='#0A1C40', width=0.6, label=label)
    clean_values = [safe_float(v) for v in values]
    max_val = max(clean_values) if clean_values else 10
    ax.set_ylim(0, max_val + (5 if max_val > 5 else 2))
    ax.set_ylabel(label, fontsize=7)
    
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.tick_params(axis='both', which='major', labelsize=7)
    ax.grid(axis='y', linestyle='-', alpha=0.2)
    
    # Display all labels if there are fewer bars (buckets), otherwise use interval logic
    if len(x_labels) <= 12:
        ax.set_xticks(range(len(x_labels)))
        ax.set_xticklabels(x_labels)
    else:
        tick_indices = list(range(0, len(x_labels), 5))
        if (len(x_labels)-1) not in tick_indices:
            tick_indices.append(len(x_labels)-1)
        ax.set_xticks(tick_indices)
        ax.set_xticklabels([x_labels[i] for i in tick_indices])
    
    # ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.2), frameon=False, fontsize=7, handlelength=1, handleheight=1)
    
    # Ensure Y-axis ticks are integers
    from matplotlib.ticker import MaxNLocator
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    
    return _buf_from_fig(fig)

def generate_pie_with_legend(labels, sizes, colors_list, is_donut=False, explode=None, center_text=None, center_subtext=None):
    fig, ax = plt.subplots(figsize=(5, 3))
    
    sizes = [safe_float(s) for s in sizes]
    
    # Check if empty
    is_empty = sum(sizes) == 0
    if is_empty:
        sizes = [1]
        colors_list = ["#E5E7EB"] # Light grey for empty
        is_donut = True
        center_text = "0"
        center_subtext = "Records"
        
    def pct_filter(pct):
        return ('%1.1f%%' % pct) if pct > 0 else ''

    pie_results = ax.pie(
        sizes, 
        colors=colors_list, 
        autopct=pct_filter if not is_empty else None,
        startangle=140, 
        textprops={'fontsize': 7, 'color': 'white', 'fontweight': 'bold'} if not is_empty else {'fontsize': 7, 'color': 'grey'},
        explode=explode,
        wedgeprops=dict(width=0.4, edgecolor='white', linewidth=1) if is_donut else dict(edgecolor='white', linewidth=1)
    )
    
    if not is_empty:
        wedges, texts, autotexts = pie_results
    else:
        wedges, texts = pie_results
        autotexts = []
    ax.axis('equal')
    
    if is_donut and center_text:
        ax.text(0, 0.1, center_text, ha='center', va='center', fontsize=16, fontweight='bold', color='#374151')
        if center_subtext:
            ax.text(0, -0.2, center_subtext, ha='center', va='center', fontsize=7, color='#6B7280')
    
    if is_empty:
        # Show all labels with (0) in legend
        legend_labels = [f"{l} (0)" for l in labels]
    else:
        legend_labels = [f"{l} ({int(s)})" if isinstance(s, (int, float)) and s == int(s) else l for l, s in zip(labels, sizes)]
        
    ax.legend(wedges if not is_empty else [wedges[0]]*len(labels), legend_labels, title="", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1), frameon=False, fontsize=7)
    
    return _buf_from_fig(fig)

def generate_conversion_donut(offered, remaining):
    fig, ax = plt.subplots(figsize=(5, 3))
    
    total = offered + remaining
    if offered == 0:
        sizes = [1]
        colors_list = ["#1E90FF"] # Blue for empty
        wedge_props = dict(width=0.3, edgecolor="#1E90FF", linewidth=0.5)
    else:
        sizes = [offered, remaining]
        colors_list = ["#228B22", "#1E90FF"] # Green, Blue
        wedge_props = dict(width=0.3)
        
    labels = [f"Offered ({offered})", f"Remaining ({remaining})"]
    wedges, texts = ax.pie(
        sizes, 
        colors=colors_list, 
        startangle=90, 
        wedgeprops=wedge_props
    )
    
    rate = (offered / (offered + remaining)) * 100 if (offered + remaining) > 0 else 0
    rate_text = f"{rate:.1f}%" if offered > 0 else "0%"
    
    ax.text(0, 0.1, rate_text, ha='center', va='center', fontsize=16, fontweight='bold')
    ax.text(0, -0.2, "Offer Conversion\nRate", ha='center', va='center', fontsize=7)
    
    ax.axis('equal')
    ax.legend(wedges, labels, loc="center left", bbox_to_anchor=(1, 0, 0.5, 1), frameon=False, fontsize=7, handlelength=1, handleheight=1)
    
    return _buf_from_fig(fig)

# --- Data Preparation Helper ---

def prepare_report_data(
    job_title: str,
    department: str,
    location: str,
    employment_type: str,
    applicants: list,
    report_date: str = None,
    requisition_id: str = "N/A",
    date_posted: str = "N/A",
    raw_analysis_records: list = None,
    raw_interview_records: list = None,
):
    # Calculate Summaries from raw records if provided for 100% DB accuracy
    total = len(applicants)
    
    if raw_analysis_records:
        screened = len(raw_analysis_records)
        offered = sum(1 for ra in raw_analysis_records if str(ra.status).lower() == "offered")
        shortlisted = sum(1 for ra in raw_analysis_records if str(ra.status).lower() in ["shortlisted", "offered"])
    else:
        screened = sum(1 for a in applicants if str(a.get("screened", "")).lower() == "yes")
        offered = sum(1 for a in applicants if str(a.get("status", "")).lower() == "offered")
        shortlisted = sum(1 for a in applicants if str(a.get("shortlisted", "")).lower() == "yes")
        
    if raw_interview_records:
        ai_interviews = len(raw_interview_records)
    else:
        ai_interviews = sum(1 for a in applicants if str(a.get("ai_interview", "")).lower() == "yes")

    # 1. Experience Distribution
    if raw_analysis_records:
        exp_list = []
        for ra in raw_analysis_records:
            e = str(ra.experience_level or "").strip().lower()
            if e in ["experienced", "experience"]:
                exp_list.append("Experience")
            elif e == "intermediate":
                exp_list.append("Intermediate")
            else:
                exp_list.append("Beginer")
    else:
        exp_list = [a.get("experience", "N/A") for a in applicants]

    def map_exp(e):
        if e is None or str(e).strip() == "" or str(e).lower() == "n/a":
            return "N/A"
        try:
            val = float(str(e).split()[0])
            if val < 2: return "Beginer"
            if val < 5: return "Intermediate"
            return "Experience"
        except:
            pass
        e = str(e).strip().lower()
        if e in ["fresher", "beginner", "beginer", "junior"]: return "Beginer"
        if e in ["intermediate", "mid-level", "mid"]: return "Intermediate"
        if e in ["expert", "experienced", "senior", "lead", "experience"]: return "Experience"
        return "N/A"
        
    mapped_exp = [map_exp(e) for e in exp_list if map_exp(e) != "N/A"]
    exp_counts = Counter(mapped_exp)
    exp_labels = ["Beginer", "Intermediate", "Experience"]
    exp_values = [exp_counts.get(l, 0) for l in exp_labels]
    exp_colors = ["#E67E22", "#2ECC71", "#3498DB"]

    # 2. Applications Over Time
    now = datetime.datetime.now()
    first_day = now.replace(day=1)
    if now.month == 12:
        last_day = now.replace(year=now.year+1, month=1, day=1) - datetime.timedelta(days=1)
    else:
        last_day = now.replace(month=now.month+1, day=1) - datetime.timedelta(days=1)
    
    num_days = last_day.day
    current_month_days = [(first_day + datetime.timedelta(days=i)).strftime("%d %b %Y") for i in range(num_days)]
    date_list = [a.get("applied_on", "") for a in applicants if a.get("applied_on")]
    date_counts = Counter(date_list)
    
    time_labels = []
    time_values = []
    for i in range(0, num_days, 4):
        end_day = min(i + 4, num_days)
        label_text = f"{i+1:02d}-{end_day:02d}"
        time_labels.append(label_text)
        sum_val = 0
        for day_idx in range(i, end_day):
            d_str = current_month_days[day_idx]
            sum_val += date_counts.get(d_str, 0)
        time_values.append(sum_val)

    # 3. Source Distribution (Sourced directly from tb_job_applications table)
    def map_source(s):
        if not s: return "Others"
        s = str(s).strip().lower()
        if "linkedin" in s: return "LinkedIn"
        if "nakuri" in s or "naukri" in s: return "Nakuri"
        if "website" in s: return "Website"
        if "agency" in s or "rpo" in s: return "Agency / Rpo"
        if s == "all": return "All"
        return "Others"
        
    mapped_sources = [map_source(a.get("source")) for a in applicants]
    source_counts = Counter(mapped_sources)
    
    source_labels = ["Nakuri", "LinkedIn", "Website", "Agency / Rpo", "Others", "All"]
    source_values = [source_counts.get(l, 0) for l in source_labels]
    source_colors = ["#1E5B94", "#5B9BD5", "#70AD47", "#FBBF24", "#A5A5A5", "#8E44AD"]

    # 4. Score Distributions
    def get_score_bucket(val):
        try:
            if isinstance(val, (int, float)):
                v = float(val)
            else:
                v = float(str(val).replace('%', '').strip()) if val and val != "-" else 0
            if v >= 90: return "90% and above"
            if v >= 80: return "80% - 89%"
            if v >= 70: return "70% - 79%"
            if v >= 60: return "60% - 69%"
            return "Below 60%"
        except:
            return "Below 60%"

    score_labels = ["90% and above", "80% - 89%", "70% - 79%", "60% - 69%", "Below 60%"]
    score_colors = ["#27AE60", "#2980B9", "#F39C12", "#8E44AD", "#C0392B"]

    def safe_get_score(record, field):
        if hasattr(record, field): return getattr(record, field)
        if isinstance(record, dict): return record.get(field)
        return None

    if raw_analysis_records:
        screen_list = [get_score_bucket(safe_get_score(ra, "final_score")) for ra in raw_analysis_records if safe_get_score(ra, "final_score") is not None]
    else:
        screen_list = [get_score_bucket(a.get("screening_score_raw")) for a in applicants if a.get("screening_score_raw") is not None]
    
    screen_counts = Counter(screen_list)
    screen_values = [screen_counts[l] for l in score_labels]

    if raw_interview_records:
        interview_list = [get_score_bucket(safe_get_score(ri, "total_score")) for ri in raw_interview_records if safe_get_score(ri, "total_score") is not None]
    else:
        interview_list = [get_score_bucket(a.get("interview_score_raw")) for a in applicants if a.get("interview_score_raw") is not None]
    
    interview_counts = Counter(interview_list)
    interview_values = [interview_counts[l] for l in score_labels]

    # Generate Chart Buffers
    charts = {
        "time": generate_bar_chart(time_labels, time_values, num_ticks=5),
        "experience": generate_pie_with_legend(exp_labels, exp_values, exp_colors, is_donut=False),
        "source": generate_pie_with_legend(source_labels, source_values, source_colors, is_donut=False),
        "screening": generate_pie_with_legend(score_labels, screen_values, score_colors),
        "interview": generate_pie_with_legend(score_labels, interview_values, score_colors),
        "offer": generate_conversion_donut(offered, max(total - offered, 0))
    }

    return {
        "job_title": job_title,
        "department": department,
        "location": location,
        "employment_type": employment_type,
        "requisition_id": requisition_id,
        "date_posted": date_posted,
        "total": total,
        "screened": screened,
        "offered": offered,
        "shortlisted": shortlisted,
        "ai_interviews": ai_interviews,
        "applicants": applicants,
        "charts": charts,
        "report_date": report_date or datetime.datetime.now().strftime("%d %b %Y")
    }

# --- PDF Generation ---

def generate_applicants_pdf(
    job_title: str,
    department: str,
    location: str,
    employment_type: str,
    applicants: list,
    report_date: str = None,
    requisition_id: str = "N/A",
    date_posted: str = "N/A",
    raw_analysis_records: list = None,
    raw_interview_records: list = None,
) -> io.BytesIO:
    report_data = prepare_report_data(
        job_title, department, location, employment_type, applicants,
        report_date, requisition_id, date_posted, raw_analysis_records, raw_interview_records
    )
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=14, textColor=DARK_BLUE, alignment=TA_RIGHT)
    subtitle_style = ParagraphStyle('CustomSubTitle', parent=styles['Normal'], fontName='Helvetica', fontSize=8, textColor=colors.grey, alignment=TA_RIGHT)
    company_style = ParagraphStyle('CompanyTitle', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=16, textColor=DARK_BLUE)
    slogan_style = ParagraphStyle('Slogan', parent=styles['Normal'], fontName='Helvetica', fontSize=8, textColor=colors.grey)
    section_title = ParagraphStyle('SectionTitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, textColor=colors.white)
    
    elements = []
    
    # --- LOGO HELPER ---
    def get_logo():
        try:
            drawing = svg2rlg(LOGO_PATH)
            # Resize drawing to fit (maintaining aspect ratio)
            # Standard height around 30-40 pts
            h = 30
            scale = h / drawing.height
            drawing.width *= scale
            drawing.height *= scale
            drawing.scale(scale, scale)
            return drawing
        except:
            return Paragraph(f"<font fontName='{emoji_font}' color='#0A1C40' size=18>🧊</font>", styles['Normal'])

    # 0. HEADER
    logo_part = [
        get_logo(),
        Paragraph("<b>Integrated Solutions LLP</b>", company_style)
    ]
    title_part = [
        Paragraph("JOB APPLICANTS REPORT", title_style),
        Paragraph(f"Detailed Report for {job_title}", subtitle_style)
    ]
    header_table = Table([[logo_part, title_part]], colWidths=[270, 270])
    header_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('ALIGN', (1,0), (1,0), 'RIGHT')]))
    elements.append(header_table)
    elements.append(Spacer(1, 10))

    def create_section_header(text, width=550, is_attached=False):
        # Calculate text width to make a 'tab' look
        text_w = pdfmetrics.stringWidth(text, 'Helvetica-Bold', 8)
        rect_w = text_w + 15
        d = Drawing(width, 22)
        # Main header rectangle (Tab style)
        d.add(Rect(0, 4, rect_w, 18, rx=4, ry=4, fillColor=DARK_BLUE, strokeWidth=0))
        d.add(String(7, 9, text, fontName='Helvetica-Bold', fontSize=8, fillColor=colors.white))
        # Add a thin line across the rest of the width to separate sections
        d.add(Rect(0, 4, width, 1, fillColor=DARK_BLUE, strokeWidth=0))
        return d

    # 1. JOB DETAILS - Unified Box
    label_style = ParagraphStyle('JDLabel', parent=styles['Normal'], fontSize=6, fontName='Helvetica-Bold', leading=8)
    val_style = ParagraphStyle('JDValue', parent=styles['Normal'], fontSize=7, fontName='Helvetica', leading=9)
    
    def jd_cell(img_filename, label, val):
        icon_path = os.path.join("static", "icons", img_filename)
        if os.path.exists(icon_path):
            icon = RLImage(icon_path, width=14, height=14)
        else:
            icon = Paragraph("•", styles['Normal'])
            
        t = Table([[
            icon,
            [Paragraph(label, label_style), Paragraph(val, val_style)]
        ]], colWidths=[18, 62])
        t.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 2),
            ('TOPPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ]))
        return t

    jd_data = [[
        jd_cell("briefcase.png", "Job Title", job_title),
        jd_cell("building.png", "Department", department),
        jd_cell("location.png", "Location", location),
        jd_cell("user.png", "Employment Type", employment_type),
        jd_cell("tag.png", "Job Requisition ID", requisition_id),
        jd_cell("calendar.png", "Date Posted", date_posted)
    ]]

    section_1_header = create_section_header("1. JOB DETAILS", width=550, is_attached=True)
    jd_table = Table(jd_data, colWidths=[91]*6)
    jd_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LINEAFTER', (0,0), (-2,-1), 0.5, colors.lightgrey),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('RIGHTPADDING', (0,0), (-1,-1), 5),
    ]))
    
    s1_content = Table([[section_1_header], [jd_table]], colWidths=[550], rowHeights=[18, None])
    s1_content.setStyle(TableStyle([
        ('LEFTPADDING', (0,0), (-1,-1), 0), ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    elements.append(RoundedBoxFlowable(s1_content, width=550, radius=5, strokeColor=colors.lightgrey))
    elements.append(Spacer(1, 25))

    # Calculate Summaries from raw records if provided for 100% DB accuracy
    total = len(applicants)
    
    if raw_analysis_records:
        screened = len(raw_analysis_records)
        offered = sum(1 for ra in raw_analysis_records if str(ra.status).lower() == "offered")
        shortlisted = sum(1 for ra in raw_analysis_records if str(ra.status).lower() in ["shortlisted", "offered"])
    else:
        screened = sum(1 for a in applicants if str(a.get("screened", "")).lower() == "yes")
        offered = sum(1 for a in applicants if str(a.get("status", "")).lower() == "offered")
        shortlisted = sum(1 for a in applicants if str(a.get("shortlisted", "")).lower() == "yes")
        
    if raw_interview_records:
        ai_interviews = len(raw_interview_records)
    else:
        ai_interviews = sum(1 for a in applicants if str(a.get("ai_interview", "")).lower() == "yes")
    
    # 2. OVERVIEW SUMMARY - Unified Box
    # Update alignment for horizontal layout
    sum_title_style = ParagraphStyle('SumTitle', fontName='Helvetica', fontSize=7, textColor=colors.black, alignment=TA_LEFT)
    sum_val_style = ParagraphStyle('SumVal', fontName='Helvetica-Bold', fontSize=12, textColor=DARK_BLUE, alignment=TA_LEFT)

    def m_cell(img_filename, title, val, total_count=0):
        icon_path = os.path.join("assets", "icons", img_filename)

        if os.path.exists(icon_path):
            icon = RLImage(icon_path, width=28, height=28)
        else:
            icon = Paragraph("•", styles["Normal"])

        # Right side (stacked text)
        text_block = Table([
            [Paragraph(title, sum_title_style)],
            [Paragraph(str(val), sum_val_style)]
        ])

        text_block.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 15),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))

        # Main cell: icon + text
        cell = Table([
            [icon, text_block]
        ], colWidths=[35, 65])

        cell.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),  # center whole block
            ("LEFTPADDING", (0, 0), (0, 0), 30),
            # ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))

        return cell

    sum_table = Table([[
        m_cell("total_applicants.png", "Total Applicants", total),
        m_cell("screened.png", "Resume Screened", screened, total),
        m_cell("shortlisted.png", "Shortlisted", shortlisted, total),
        m_cell("ai_interviews.png", "AI Interviews", ai_interviews, total),
        m_cell("offered.png", "Offered", offered, total)
    ]], colWidths=[110]*5)
    sum_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LINEAFTER', (0,0), (-2,-1), 0.5, colors.lightgrey),
        # ('LEFTPADDING', (0,0), (-1,-1), 5),
        # ('RIGHTPADDING', (0,0), (-1,-1), 5),
    ]))

    # 2. OVERVIEW SUMMARY - Unified "Attached" Box
    section_2_header = create_section_header("2. OVERVIEW SUMMARY", width=550, is_attached=True)
    
    s2_content = Table([[section_2_header], [sum_table]], colWidths=[550], rowHeights=[18, None])
    s2_content.setStyle(TableStyle([
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        ('ALIGN', (0,1), (0,1), 'CENTER'),
    ]))
    
    elements.append(RoundedBoxFlowable(s2_content, width=550, radius=5, strokeColor=colors.lightgrey))
    elements.append(Spacer(1, 30))

    # 3. APPLICANT OVERVIEW - Unified Box
    section_3_header = create_section_header("3. APPLICANT OVERVIEW", width=550, is_attached=True)
    
    # Chart buffers are pre-generated in prepare_report_data

    c1 = RLImage(report_data['charts']['time'], width=2.2*inch, height=1.32*inch)
    c2 = RLImage(report_data['charts']['experience'], width=2.2*inch, height=1.32*inch)
    c3 = RLImage(report_data['charts']['source'], width=2.2*inch, height=1.32*inch)
    
    ctable = Table([
        [Paragraph("<font size=8><b>APPLICATION OVER TIME</b></font>", ParagraphStyle('C', alignment=TA_CENTER)),
         Paragraph("<font size=8><b>Applicants by Experience</b></font>", ParagraphStyle('C', alignment=TA_CENTER)),
         Paragraph("<font size=8><b>Applicants by Source</b></font>", ParagraphStyle('C', alignment=TA_CENTER))],
        [c1, c2, c3]
    ], colWidths=[183, 183, 183])
    ctable.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        ('LINEAFTER', (0,0), (1,-1), 0.5, colors.lightgrey), # Vertical lines between columns 0/1 and 1/2
    ]))

    s3_content = Table([[section_3_header], [ctable]], colWidths=[550], rowHeights=[18, None])
    s3_content.setStyle(TableStyle([
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    
    elements.append(RoundedBoxFlowable(s3_content, width=550, radius=5, strokeColor=colors.lightgrey))
    elements.append(Spacer(1, 10))

    # 4. APPLICANT DETAILS
    elements.append(create_section_header("4. APPLICANT DETAILS"))
    elements.append(Spacer(1, 5))
    
    def make_chip(text, color):
        bg = colors.Color(color.red, color.green, color.blue, alpha=0.15)
        d = Drawing(45, 12)
        d.add(Rect(0, 0, 45, 12, rx=3, ry=3, fillColor=bg, strokeColor=color, strokeWidth=0.5))
        d.add(String(22.5, 4, text, fontName='Helvetica-Bold', fontSize=6, fillColor=color, textAnchor='middle'))
        return d

    def make_status_icon(text):
        is_yes = text == "Yes"
        color = colors.HexColor('#228B22') if is_yes else colors.HexColor('#B22222')
        symbol = '✔' if is_yes else '✖'
        
        d = Drawing(35, 12)
        # Draw Circle
        d.add(Circle(6, 6, 5, fillColor=color, strokeWidth=0))
        # Draw Symbol (white check or cross)
        d.add(String(6, 3.5, symbol, fontName='Helvetica-Bold', fontSize=6, fillColor=colors.white, textAnchor='middle'))
        # Draw Text (Yes/No)
        d.add(String(14, 3.5, text, fontName='Helvetica', fontSize=7, fillColor=colors.black))
        return d

    headers = ["No.", "Candidate Name", "Experience", "Current Company", "Applied On", "Screening Score", "Shortlisted", "AI Interview", "Interview Score", "Status"]
    hs = ParagraphStyle('TH', fontName='Helvetica-Bold', fontSize=7, textColor=colors.black)
    cs = ParagraphStyle('TD', fontName='Helvetica', fontSize=7, textColor=colors.black, alignment=TA_CENTER)
    app_data = [[Paragraph(h, hs) for h in headers]]
    
    for idx, app in enumerate(applicants[:15], 1): # Display up to 15 max on the first page
        status = str(app.get("status", "Applied")).title()
        shortlisted_str = str(app.get("shortlisted", "No")).title()
        ai_int_str = str(app.get("ai_interview", "No")).title()
        
        status_color = GREEN if status in ["Offered", "Shortlisted"] else YELLOW if status == "Applied" else RED if status in ["Rejected", "Not Shortlisted"] else ORANGE
        status_chip = make_chip(status, status_color)
        
        chk_1 = make_status_icon(shortlisted_str)
        chk_2 = make_status_icon(ai_int_str)
        
        app_data.append([
            Paragraph(str(idx), cs), 
            Paragraph(str(app.get("name", "")), ParagraphStyle('N', parent=cs, alignment=TA_LEFT)), 
            Paragraph(str(app.get("experience", "")), cs), 
            Paragraph(str(app.get("company", "-")), cs),
            Paragraph(str(app.get("applied_on", "")), cs), 
            Paragraph(str(app.get("screening_score", "-")), cs), 
            chk_1, 
            chk_2, 
            Paragraph(str(app.get("interview_score", "-")), cs), 
            status_chip
        ])

    atable = Table(app_data, colWidths=[25, 70, 65, 65, 50, 65, 55, 50, 55, 50])
    atable.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), GREY_BG), 
        ('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey), 
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN', (9,0), (9,-1), 'CENTER')
    ]))
    elements.append(atable)
    elements.append(Spacer(1, 10))

    # 5, 6, 7. BOTTOM CHARTS
    c5 = RLImage(report_data['charts']['screening'], width=2.2*inch, height=1.32*inch)
    c6 = RLImage(report_data['charts']['interview'], width=2.2*inch, height=1.32*inch)
    c7 = RLImage(report_data['charts']['offer'], width=2.2*inch, height=1.32*inch)

    def boxed_chart(header_text, chart_image):
        inner_table = Table([[create_section_header(header_text, width=180)], [chart_image]], colWidths=[180])
        inner_table.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ]))
        return RoundedBoxFlowable(inner_table, width=180, radius=5)

    bottom_charts = Table([
        [boxed_chart("5. SCREENING SCORE DISTRIBUTION", c5), 
         boxed_chart("6. INTERVIEW SCORE DISTRIBUTION", c6), 
         boxed_chart("7. OFFER CONVERSION RATE", c7)]
    ], colWidths=[183, 183, 183])
    bottom_charts.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
    ]))
    elements.append(bottom_charts)
    elements.append(Spacer(1, 10))

    # FOOTER: NOTES & LEGEND
    ns = ParagraphStyle('Notes', fontName='Helvetica', fontSize=6, textColor=colors.black, leading=8)
    nt_clean = "• Screening Score is based on resume matching and AI screening.<br/>• Interview Score is based on AI Interview evaluation.<br/>• Offer Conversion Rate = (Offered / Total Applicants) * 100"
    
    # Legend as a separate table with chips to match image exactly
    legend_data = [
        [make_chip("Offered", GREEN), Paragraph("Selected and offer extended", ns), 
         make_chip("In Process", ORANGE), Paragraph("Under review / Interview", ns)],
        [make_chip("Shortlisted", BLUE), Paragraph("Qualified and in process", ns), 
         make_chip("Rejected", RED), Paragraph("Not qualified", ns)]
    ]
    legend_table = Table(legend_data, colWidths=[48, 85, 48, 85], rowHeights=[15, 15])
    legend_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))

    def boxed_container(title, content, width):
        inner_table = Table([
            [Paragraph(f"<b>{title}</b>", ns)],
            [content]
        ], colWidths=[width], rowHeights=[12, 38])
        inner_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
            ('RIGHTPADDING', (0,0), (-1,-1), 8),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ]))
        return RoundedBoxFlowable(inner_table, width=width, radius=5, strokeColor=colors.lightgrey)

    notes_box = boxed_container("NOTES", Paragraph(nt_clean, ns), 268)
    legend_box = boxed_container("LEGEND", legend_table, 268)

    # Use a larger gap (14pt) to match the "space in middle" from the image
    footer_content = Table([[notes_box, Spacer(1, 1), legend_box]], colWidths=[268, 14, 268])
    footer_content.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('ALIGN', (0,0), (0,0), 'LEFT'),
        ('ALIGN', (2,0), (2,0), 'RIGHT'),
    ]))
    elements.append(footer_content)
    elements.append(Spacer(1, 10))
    def draw_footer(canvas, doc):
        canvas.saveState()
        timestamp = dt_now.now().strftime("%d %b %Y | %I:%M %p")
        footer_text_style = ParagraphStyle('FooterText', fontName='Helvetica', fontSize=7, textColor=DARK_BLUE)
        # Total width = 555 (A4 width 595 - 20 - 20 margins)
        footer_table = Table([[
            Paragraph(f"This report was automatically generated on {timestamp}", footer_text_style),
            Paragraph(f"Page {doc.page}", ParagraphStyle('FooterRight', parent=footer_text_style, alignment=TA_RIGHT))
        ]], colWidths=[400, 155], rowHeights=[20])
        
        footer_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('LEFTPADDING', (0,0), (-1,-1), 10),
            ('RIGHTPADDING', (0,0), (-1,-1), 10),
            ('LINEABOVE', (0,0), (-1,0), 0.5, colors.lightgrey),
        ]))
        footer_table.wrapOn(canvas, doc.width, doc.bottomMargin)
        footer_table.drawOn(canvas, 20, 10) # x=20 (leftMargin), y=10 from bottom
        canvas.restoreState()

    doc.build(elements, onFirstPage=draw_footer, onLaterPages=draw_footer)
    buffer.seek(0)
    return buffer