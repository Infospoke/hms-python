import io
import os
import math
import datetime
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

if os.path.exists("static/fonts/Roboto-Regular.ttf"):
    pdfmetrics.registerFont(TTFont("Roboto", "static/fonts/Roboto-Regular.ttf"))
    pdfmetrics.registerFont(TTFont("Roboto-Bold", "static/fonts/Roboto-Bold.ttf"))
    font_regular = "Roboto"
    font_bold = "Roboto-Bold"
else:
    font_regular = "Helvetica"
    font_bold = "Helvetica-Bold"

DARK_BLUE = colors.HexColor("#122554")
TEXT_PRIMARY = colors.HexColor("#1F2937")

# Number to words conversion
def number_to_words(n):
    if n == 0:
        return "Zero"
    ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
            "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
    
    def convert(num):
        if num < 20:
            return ones[num]
        if num < 100:
            return tens[num // 10] + (" " + ones[num % 10] if num % 10 != 0 else "")
        if num < 1000:
            return ones[num // 100] + " Hundred" + (" and " + convert(num % 100) if num % 100 != 0 else "")
        if num < 100000:
            return convert(num // 1000) + " Thousand" + (" " + convert(num % 1000) if num % 1000 != 0 else "")
        if num < 10000000:
            return convert(num // 100000) + " Lakh" + (" " + convert(num % 100000) if num % 100000 != 0 else "")
        return convert(num // 10000000) + " Crore" + (" " + convert(num % 10000000) if num % 10000000 != 0 else "")
    
    return convert(int(n)).strip() + " Rupees Only"

def add_header(canvas, doc):
    canvas.saveState()
    # Draw NEXUS logo text
    canvas.setFont(font_bold, 24)
    canvas.setFillColor(colors.HexColor("#1A40BA")) # Bold Blue matching the image
    canvas.drawRightString(A4[0] - inch, A4[1] - inch, "NEXUS")
    
    # Gray right angle graphic (optional flair)
    canvas.setStrokeColor(colors.lightgrey)
    canvas.setLineWidth(1)
    canvas.line(A4[0] - inch - 10, A4[1] - inch - 20, A4[0] - inch + 10, A4[1] - inch - 20)
    canvas.line(A4[0] - inch + 10, A4[1] - inch - 20, A4[0] - inch + 10, A4[1] - inch)
    
    canvas.restoreState()

def generate_offer_letter_pdf(data: dict) -> io.BytesIO:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=inch,
        leftMargin=inch,
        topMargin=1.5 * inch,
        bottomMargin=inch,
    )

    styles = getSampleStyleSheet()
    
    style_normal = ParagraphStyle(
        'NormalStyle',
        parent=styles['Normal'],
        fontName=font_regular,
        fontSize=10,
        textColor=TEXT_PRIMARY,
        leading=14,
        alignment=TA_LEFT
    )
    
    style_bold = ParagraphStyle(
        'BoldStyle',
        parent=style_normal,
        fontName=font_bold
    )

    style_right = ParagraphStyle(
        'RightStyle',
        parent=style_normal,
        alignment=TA_RIGHT
    )
    
    style_bullet = ParagraphStyle(
        'BulletStyle',
        parent=style_normal,
        leftIndent=20,
        bulletIndent=10
    )

    elements = []

    # REF NO
    ref_no = data.get("reference_id", "REF NO: NEXUS")
    elements.append(Paragraph(f"<font color='#1E90FF'><i>REF NO: {ref_no}</i></font>", style_normal))
    elements.append(Spacer(1, 0.2 * inch))

    # Date
    elements.append(Paragraph(f"<b>Date:</b> {data.get('date', '')}", style_right))
    elements.append(Spacer(1, 0.2 * inch))

    # To Candidate
    candidate_name = data.get("candidate_name", "Candidate")
    location = "Hyderabad" # Defaulting for now
    elements.append(Paragraph(f"<b>Mr/Ms. {candidate_name}</b>,", style_bold))
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph(f"<b>{location}</b>", style_bold))
    elements.append(Spacer(1, 0.3 * inch))

    # Subject
    elements.append(Paragraph("<b>Sub:</b> Letter of Employment", style_normal))
    elements.append(Spacer(1, 0.3 * inch))

    # Dear Candidate
    elements.append(Paragraph(f"Dear <b>{candidate_name}</b>,", style_normal))
    elements.append(Spacer(1, 0.2 * inch))

    # Body paragraphs
    job_title = data.get("job_title", "Position")
    department = "Technology Division"
    joining_date = data.get("joining_date") or "TBD"
    manager_name = data.get("reporting_manager") or "your Manager"
    
    ctc = float(data.get("ctc", 0))
    ctc_words = number_to_words(ctc)

    p1 = f"We are delighted to extend the offer for the position of <b>{job_title}</b> within our Offshore Development Center, located in {location} as part of our <b>{department}</b>."
    elements.append(Paragraph(p1, style_normal))
    elements.append(Spacer(1, 0.2 * inch))

    p2 = f"Your joining date will be <b>{joining_date}</b>. Your immediate supervisor will be <b>{manager_name}</b>."
    elements.append(Paragraph(p2, style_normal))
    elements.append(Spacer(1, 0.2 * inch))

    p3 = "We trust that your knowledge, skills, and experience will be among our most valuable assets."
    elements.append(Paragraph(p3, style_normal))
    elements.append(Spacer(1, 0.2 * inch))

    p4 = "As discussed, and agreed with you, you will be eligible to receive the following starting from your joining date:"
    elements.append(Paragraph(p4, style_normal))
    elements.append(Spacer(1, 0.1 * inch))

    bullet_text = f"<b>Salary:</b> Annual gross starting salary of <b>INR: {ctc:,.2f} ({ctc_words})</b> subject to tax and other statutory deductions as deemed fit."
    elements.append(Paragraph(f"&bull; {bullet_text}", style_bullet))
    elements.append(Spacer(1, 0.2 * inch))

    p5 = f"This offer of employment is contingent upon you accepting the terms and conditions as set forth in your appointment letter, which will be mailed to you separately. You are required to join the services of the Company within but not later than <b>{joining_date}</b>. Please send a signed copy of this letter indicating your acceptance to join and resignation acceptance letter from your current employer."
    elements.append(Paragraph(p5, style_normal))
    elements.append(Spacer(1, 0.2 * inch))

    p6 = "You will be on probation period for 6 months. Your Appointment Letter will be issued upon successfully completing your initial service of 90 days. The joining formalities and induction will be conducted in our Hyderabad office."
    elements.append(Paragraph(p6, style_normal))
    elements.append(Spacer(1, 0.3 * inch))

    p7 = "We look forward to welcoming you aboard."
    elements.append(Paragraph(p7, style_normal))
    elements.append(Spacer(1, 0.4 * inch))

    elements.append(Paragraph("Sincerely,", style_normal))
    elements.append(Spacer(1, 0.2 * inch))

    # Page Break for Annexure
    elements.append(PageBreak())

    # Page 2 tables
    # First small table
    bonus = float(data.get("signing_bonus", 0))
    total_ctc = ctc

    t1_data = [
        ["Salary Component", "INR (p.a.)", "INR(p.m.)"],
        ["Cost to Company (CTC)", f"{ctc:,.2f}", f"{ctc/12:,.2f}"]
    ]
    t1 = Table(t1_data, colWidths=[2.5*inch, 1.8*inch, 1.8*inch])
    t1.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('FONTNAME', (0,0), (-1,0), font_bold),
        ('ALIGN', (1,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,-1), (-1,-1), font_bold),
    ]))
    elements.append(t1)
    elements.append(Spacer(1, 0.4 * inch))

    # Second small table (Details)
    t2_data = [
        ["ANNEXURE - I", "", ""],
        ["COMPENSATION (CTC) BREAKUP", "", ""],
        ["NAME:", candidate_name, ""],
        ["DESIGNATION:", job_title, ""],
        ["BAND / GRADE:", "Standard", ""],
        ["DEPARTMENT:", department, ""],
        ["LOCATION:", location, ""]
    ]
    t2 = Table(t2_data, colWidths=[1.8*inch, 2.3*inch, 2*inch])
    t2.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('SPAN', (0,0), (-1,0)),
        ('SPAN', (0,1), (-1,1)),
        ('ALIGN', (0,0), (-1,1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,1), font_bold),
        ('BACKGROUND', (0,1), (-1,1), colors.HexColor("#A9C5E8")),
        ('FONTNAME', (0,2), (0,-1), font_bold),
    ]))
    elements.append(t2)
    elements.append(Spacer(1, 0.4 * inch))

    # Third Table (Breakup)
    # Calculation based on the specific rule:
    # Deductions: Employer PF (1800), Employee PF (1800), Tax Compliance (200) = Total 3800
    monthly_ctc = ctc / 12
    employer_pf_pm = 1800
    employee_pf_pm = 1800
    tax_compliance_pm = 200
    
    inhand_pm = monthly_ctc - employer_pf_pm - employee_pf_pm - tax_compliance_pm
    
    basic_pm = inhand_pm * 0.50
    hra_pm = inhand_pm * 0.50
    special_allowance_pm = employee_pf_pm + tax_compliance_pm  # 2000
    
    gross_pm = basic_pm + hra_pm + special_allowance_pm
    
    basic_pa = basic_pm * 12
    hra_pa = hra_pm * 12
    pf_pa = employer_pf_pm * 12
    special_allowance_pa = special_allowance_pm * 12
    gross_pa = gross_pm * 12

    employee_pf_pa = employee_pf_pm * 12
    tax_compliance_pa = tax_compliance_pm * 12

    t3_data = [
        ["Salary Components", "Monthly\n(INR)", "Yearly\n(INR)", "Remarks"],
        ["Basic", f"{basic_pa/12:,.2f}", f"{basic_pa:,.2f}", ""],
        ["HRA", f"{hra_pa/12:,.2f}", f"{hra_pa:,.2f}", ""],
        ["Gross Salary (A)", f"{gross_pa/12:,.2f}", f"{gross_pa:,.2f}", ""],
        ["Employee PF Contribution", f"{employee_pf_pm:,.2f}", f"{employee_pf_pa:,.2f}", ""],
        ["Tax Compliance", f"{tax_compliance_pm:,.2f}", f"{tax_compliance_pa:,.2f}", ""],
        ["Employer PF Contribution (B)", f"{pf_pa/12:,.2f}", f"{pf_pa:,.2f}", ""],
        ["CTC (A) + (B)", f"{ctc/12:,.2f}", f"{ctc:,.2f}", ""]
    ]
    t3 = Table(t3_data, colWidths=[2.3*inch, 1.2*inch, 1.2*inch, 1.4*inch])
    t3.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('FONTNAME', (0,0), (-1,0), font_bold),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#EBE2C6")),
        ('ALIGN', (1,0), (2,-1), 'CENTER'),
        ('FONTNAME', (0,3), (0,3), font_bold),
        ('FONTNAME', (0,-1), (-1,-1), font_bold),
    ]))
    elements.append(t3)
    elements.append(Spacer(1, 0.4 * inch))

    # Key Notes
    elements.append(Paragraph("<b>Key Notes</b>", style_normal))
    notes = [
        "You are eligible for Health insurance of 3 lakhs per employee and family members (Example: if there are 4 members the coverage for the family is 12 lakhs with a capping 3 lakhs per member), 10 Lakhs Group Term Life Insurance Policy (GTLI) and 10 Lakhs Accidental Death Benefit Insurance",
        "Gratuity paid as per Payment of Gratuity Act, 1972",
        "Professional Tax and Income Tax (TDS) will be deducted from the salary in accordance with the respective Acts."
    ]
    for note in notes:
        elements.append(Paragraph(f"<font size=8>* {note}</font>", style_normal))
    
    elements.append(Spacer(1, 0.6 * inch))

    # Signatures
    sig_data = [
        ["Authorised Signatory", "Candidate's Signature"],
        ["Date:", "Date:"]
    ]
    # Set the second column slightly narrower and explicitly left-align the table on the page
    sig_table = Table(sig_data, colWidths=[4.2*inch, 2.0*inch], hAlign='LEFT')
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
    ]))
    elements.append(sig_table)

    # Build the PDF
    doc.build(elements, onFirstPage=add_header, onLaterPages=add_header)

    buffer.seek(0)
    return buffer

def add_signature_to_pdf(
    original_pdf_bytes: bytes,
    candidate_name: str = "Candidate",
    accepted_date: str = None,
    signature_base64: str = None,
    signature_text: str = None,
    is_company_signature: bool = False
) -> bytes:
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas
    import base64
    import tempfile
    signature_path = None
    temp_sig_file = None
    
    if signature_base64:
        # Handle prefix if present
        if "," in signature_base64:
            signature_base64 = signature_base64.split(",")[1]
        try:
            img_data = base64.b64decode(signature_base64)
            temp_sig_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            temp_sig_file.write(img_data)
            temp_sig_file.close()
            signature_path = temp_sig_file.name
        except Exception as e:
            print(f"Failed to decode base64 signature: {e}")
            
    # 1. First Page Overlay (Company Signature under "Sincerely,")
    packet_first = io.BytesIO()
    c_first = canvas.Canvas(packet_first, pagesize=A4)
    if is_company_signature and signature_path and os.path.exists(signature_path):
        # Company signature under "Sincerely," on Page 1
        c_first.drawImage(signature_path, 55, 140, width=1.5*inch, height=0.6*inch, mask='auto')
    c_first.showPage()
    c_first.save()
    packet_first.seek(0)
    overlay_pdf_first = PdfReader(packet_first)
    overlay_page_first = overlay_pdf_first.pages[0]
    
    # 2. Last Page Overlay
    packet_last = io.BytesIO()
    c_last = canvas.Canvas(packet_last, pagesize=A4)
    if is_company_signature:
        if signature_path and os.path.exists(signature_path):
            # Authorised Signatory signature on LEFT side above "Authorised Signatory"
            c_last.drawImage(signature_path, 55, 195, width=1.5*inch, height=0.6*inch, mask='auto')
    else:
        if signature_path and os.path.exists(signature_path):
            # Candidate signature on RIGHT side above "Candidate's Signature"
            c_last.drawImage(signature_path, 350, 195, width=1.5*inch, height=0.6*inch, mask='auto')
        elif signature_text:
            # Candidate typed signature text on RIGHT side
            c_last.setFont("Helvetica-Oblique", 14)
            c_last.setFillColorRGB(0.0, 0.15, 0.45) # Navy blue signature ink
            c_last.drawString(350, 205, signature_text)
            c_last.setLineWidth(0.5)
            c_last.setStrokeColorRGB(0.2, 0.2, 0.6)
            c_last.line(350, 200, 480, 200)

    c_last.showPage()
    c_last.save()
    packet_last.seek(0)
    overlay_pdf_last = PdfReader(packet_last)
    overlay_page_last = overlay_pdf_last.pages[0]
    
    original_pdf = PdfReader(io.BytesIO(original_pdf_bytes))
    writer = PdfWriter()
    
    last_page_idx = len(original_pdf.pages) - 1
    
    for i, page in enumerate(original_pdf.pages):
        if i == 0:
            page.merge_page(overlay_page_first)
        if i == last_page_idx:
            page.merge_page(overlay_page_last)
        writer.add_page(page)
        
    output = io.BytesIO()
    writer.write(output)
    
    if temp_sig_file:
        try:
            os.remove(temp_sig_file.name)
        except:
            pass
            
    return output.getvalue()