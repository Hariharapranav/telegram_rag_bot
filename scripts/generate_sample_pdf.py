import os
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

def generate_pdf():
    output_dir = Path(__file__).resolve().parent.parent
    pdf_path = output_dir / "slidio_technology_policy_2026.pdf"

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=letter,
        rightMargin=54,
        leftMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=6
    )

    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#475569"),
        spaceAfter=15
    )

    h1_style = ParagraphStyle(
        "SectionH1",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12.5,
        leading=16,
        textColor=colors.HexColor("#1E293B"),
        spaceBefore=12,
        spaceAfter=5
    )

    body_style = ParagraphStyle(
        "DocBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor("#334155"),
        spaceAfter=5
    )

    bullet_style = ParagraphStyle(
        "DocBullet",
        parent=body_style,
        leftIndent=15,
        spaceAfter=4
    )

    story = []

    # Title & Metadata Header
    story.append(Paragraph("SLIDIO INC - GLOBAL TECHNOLOGY & WORKPLACE POLICY", title_style))
    story.append(Paragraph("<b>Document Ref:</b> SLI-POL-2026-v2.1 &nbsp;|&nbsp; <b>Effective:</b> October 2026 &nbsp;|&nbsp; <b>Classification:</b> Internal Confidential", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2563EB"), spaceAfter=14))

    # Section 1
    story.append(Paragraph("1. Purpose & Scope", h1_style))
    story.append(Paragraph("This policy establishes corporate guidelines for workstation hardware, remote work subsidies, generative AI governance, business travel expense caps, and wellness allowances for all team members at Slidio Inc worldwide.", body_style))
    story.append(Spacer(1, 4))

    # Section 2
    story.append(Paragraph("2. Equipment & Remote Work Stipends", h1_style))
    story.append(Paragraph("Slidio Inc provides every team member with modern, enterprise-grade hardware to ensure productivity and data security:", body_style))
    story.append(Paragraph("• <b>Primary Hardware:</b> Technical staff receive an Apple MacBook Pro 16-inch (M3 Max, 36GB RAM) or Dell XPS 15 (Intel Core i9, 32GB RAM). Equipment is refreshed every 36 months.", bullet_style))
    story.append(Paragraph("• <b>Home Office Grant:</b> Every full-time hire receives a one-time <b>$1,500 USD</b> home workstation grant disbursed in their first paycheck for monitors, standing desks, and ergonomic chairs.", bullet_style))
    story.append(Paragraph("• <b>Mobile Phone Allowance:</b> Employees in on-call engineering, customer success, or executive roles receive up to <b>$75 USD per month</b> in mobile service expense reimbursements.", bullet_style))
    story.append(Spacer(1, 4))

    # Section 3
    story.append(Paragraph("3. Generative AI & Data Governance Guidelines", h1_style))
    story.append(Paragraph("To protect customer privacy and corporate intellectual property while adopting artificial intelligence safely:", body_style))
    story.append(Paragraph("• <b>Approved AI Platform:</b> Employees must exclusively query internal knowledge bases via Slidio's private Telegram RAG Bot. Confidential client records, API keys, and unreleased source code must never be submitted into public consumer tools.", bullet_style))
    story.append(Paragraph("• <b>Hardware Security Keys:</b> All engineering production access, GitHub repositories, and Supabase database administrative consoles require FIDO2 hardware security keys (e.g. YubiKey 5 Series).", bullet_style))
    story.append(Spacer(1, 4))

    # Section 4
    story.append(Paragraph("4. Professional Learning & Certification Budget", h1_style))
    story.append(Paragraph("Slidio Inc is committed to continuous skill growth and industry excellence:", body_style))
    story.append(Paragraph("• <b>Annual L&D Allowance:</b> Every full-time employee is allotted an annual budget of <b>$2,200 USD</b> for professional certifications (AWS, GCP, CISA, PMP), technical conferences, and books.", bullet_style))
    story.append(Paragraph("• <b>Paid Learning Days:</b> Employees receive <b>3 dedicated paid Learning Days</b> per year, separate from standard paid time off.", bullet_style))
    story.append(Spacer(1, 4))

    # Section 5 - Table
    story.append(Paragraph("5. Business Travel & Expense Limits", h1_style))
    story.append(Paragraph("All business trips must be authorized in advance via the corporate travel portal. Standard per diem limits apply as follows:", body_style))

    table_data = [
        [Paragraph("<b>Expense Category</b>", body_style), Paragraph("<b>Domestic (Within Country)</b>", body_style), Paragraph("<b>International Travel</b>", body_style)],
        [Paragraph("Daily Meal & Incidentals (Per Diem)", body_style), Paragraph("<b>$85 USD / day</b>", body_style), Paragraph("<b>$120 USD / day</b>", body_style)],
        [Paragraph("Hotel Lodging Rate Cap", body_style), Paragraph("$250 USD / night", body_style), Paragraph("$350 USD / night", body_style)],
        [Paragraph("Airfare Class Eligibility", body_style), Paragraph("Economy Class (Under 6 hours)", body_style), Paragraph("Premium Economy / Business (&gt;6 hours)", body_style)],
        [Paragraph("Ground Transportation", body_style), Paragraph("Uber / Lyft / Airport Taxi", body_style), Paragraph("Airport Express / Taxi Reimbursable", body_style)]
    ]

    t = Table(table_data, colWidths=[150, 175, 175])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))

    # Section 6
    story.append(Paragraph("6. Employee Wellness & Mental Health Perks", h1_style))
    story.append(Paragraph("• <b>Fitness Reimbursement:</b> Team members can claim up to <b>$60 USD per month</b> for gym memberships, fitness trackers, swimming pool passes, or yoga classes.", bullet_style))
    story.append(Paragraph("• <b>Mental Health Support:</b> Up to 8 confidential therapy or coaching sessions per calendar year fully covered through Lyra Health.", bullet_style))
    story.append(Paragraph("• <b>Annual Wellness Day:</b> The first Friday of October is an official company-wide paid Wellness Holiday.", bullet_style))
    story.append(Spacer(1, 12))

    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#E2E8F0"), spaceAfter=8))
    story.append(Paragraph("<b>Slidio Inc</b> &nbsp;|&nbsp; People &amp; Culture Operations &nbsp;|&nbsp; Contact: <code>people@slidio.com</code>", ParagraphStyle("Foot", parent=body_style, fontSize=8, textColor=colors.HexColor("#64748B"))))

    doc.build(story)
    print(f"PDF generated successfully: {pdf_path}")
    print(f"File size: {os.path.getsize(pdf_path)} bytes")

if __name__ == "__main__":
    generate_pdf()
