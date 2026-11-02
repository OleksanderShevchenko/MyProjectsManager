import datetime
import io
import logging
import os

from django.db.models import Sum, Q
from django.utils import timezone
from django.utils.translation import gettext as _
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from reportlab.lib import colors
from reportlab.lib import pagesizes
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)

from .models import WeeklyTimesheet, TimeLog, Project

logger = logging.getLogger(__name__)

# Register Unicode fonts for ReportLab if available
_FONTS_REGISTERED = False
_REGULAR_FONT = "Helvetica"
_BOLD_FONT = "Helvetica-Bold"


def _init_fonts():
    global _FONTS_REGISTERED, _REGULAR_FONT, _BOLD_FONT
    if _FONTS_REGISTERED:
        return

    candidate_font_paths = [
        ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
        ("C:/Windows/Fonts/calibri.ttf", "C:/Windows/Fonts/calibrib.ttf"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    ]

    for reg_path, bold_path in candidate_font_paths:
        if os.path.exists(reg_path) and os.path.exists(bold_path):
            try:
                pdfmetrics.registerFont(TTFont("AppUnicode", reg_path))
                pdfmetrics.registerFont(TTFont("AppUnicode-Bold", bold_path))
                _REGULAR_FONT = "AppUnicode"
                _BOLD_FONT = "AppUnicode-Bold"
                _FONTS_REGISTERED = True
                logger.debug("Registered Unicode fonts for PDF export: %s, %s", reg_path, bold_path)
                return
            except Exception as e:
                logger.warning("Could not register fonts %s / %s: %s", reg_path, bold_path, e)

    _FONTS_REGISTERED = True


class ExportService:
    """
    Service responsible for document generation:
    - Weekly timesheet export to PDF (A4 Landscape, print-ready)
    - Yearly timesheet export to Excel (Multi-tab formatted workbook)
    """

    @classmethod
    def generate_weekly_pdf(cls, timesheet: WeeklyTimesheet) -> bytes:
        """
        Generates a PDF document for a single weekly timesheet.
        Returns the PDF binary content as bytes.
        """
        _init_fonts()
        buffer = io.BytesIO()

        # Landscape A4 gives ample width for daily grid columns
        doc = SimpleDocTemplate(
            buffer,
            pagesize=pagesizes.landscape(pagesizes.A4),
            leftMargin=30,
            rightMargin=30,
            topMargin=30,
            bottomMargin=30,
        )

        elements = []
        styles = getSampleStyleSheet()

        # Custom typography styles
        title_style = ParagraphStyle(
            'DocTitle',
            parent=styles['Normal'],
            fontName=_BOLD_FONT,
            fontSize=18,
            leading=22,
            textColor=colors.HexColor('#1e1b4b'),
        )
        subtitle_style = ParagraphStyle(
            'DocSubtitle',
            parent=styles['Normal'],
            fontName=_REGULAR_FONT,
            fontSize=10,
            leading=14,
            textColor=colors.HexColor('#475569'),
        )
        meta_label_style = ParagraphStyle(
            'MetaLabel',
            parent=styles['Normal'],
            fontName=_BOLD_FONT,
            fontSize=9,
            leading=12,
            textColor=colors.HexColor('#475569'),
        )
        meta_value_style = ParagraphStyle(
            'MetaValue',
            parent=styles['Normal'],
            fontName=_REGULAR_FONT,
            fontSize=9,
            leading=12,
            textColor=colors.HexColor('#0f172a'),
        )
        grid_header_style = ParagraphStyle(
            'GridHeader',
            parent=styles['Normal'],
            fontName=_BOLD_FONT,
            fontSize=9,
            leading=11,
            alignment=1,  # Center
            textColor=colors.white,
        )
        grid_cell_style = ParagraphStyle(
            'GridCell',
            parent=styles['Normal'],
            fontName=_REGULAR_FONT,
            fontSize=8,
            leading=10,
            textColor=colors.HexColor('#0f172a'),
        )
        grid_cell_center = ParagraphStyle(
            'GridCellCenter',
            parent=grid_cell_style,
            alignment=1,  # Center
        )
        grid_cell_bold_center = ParagraphStyle(
            'GridCellBoldCenter',
            parent=grid_cell_style,
            fontName=_BOLD_FONT,
            alignment=1,  # Center
        )

        # Dates calculation
        monday = datetime.date.fromisocalendar(timesheet.year, timesheet.week_number, 1)
        week_dates = [monday + datetime.timedelta(days=i) for i in range(7)]
        period_str = f"{week_dates[0].strftime('%b %d, %Y')} – {week_dates[-1].strftime('%b %d, %Y')}"

        employee_name = timesheet.user.get_full_name() or timesheet.user.username
        employee_email = timesheet.user.email or _("No email specified")

        # 1. Header Section
        header_text = [
            Paragraph("MyProjectsManager", title_style),
            Paragraph(_("Weekly Working Hours Timesheet Report"), subtitle_style),
        ]
        elements.extend(header_text)
        elements.append(Spacer(1, 15))

        # 2. Metadata Block (Two-column info box)
        status_display = timesheet.get_status_display()
        if timesheet.status == WeeklyTimesheet.Status.APPROVED:
            status_color = "#15803d"
        elif timesheet.status == WeeklyTimesheet.Status.SUBMITTED:
            status_color = "#b45309"
        else:
            status_color = "#475569"

        status_text = f"<font color='{status_color}'><b>{status_display.upper()}</b></font>"

        reviewer_info = ""
        if timesheet.approved_by:
            approver_name = timesheet.approved_by.get_full_name() or timesheet.approved_by.username
            dt_str = timesheet.approved_at.strftime('%Y-%m-%d %H:%M') if timesheet.approved_at else ""
            reviewer_info = f"{approver_name} ({dt_str})"

        meta_data = [
            [
                Paragraph(_("Employee:"), meta_label_style),
                Paragraph(f"{employee_name} ({employee_email})", meta_value_style),
                Paragraph(_("Period:"), meta_label_style),
                Paragraph(f"Week {timesheet.week_number}, {timesheet.year} ({period_str})", meta_value_style),
            ],
            [
                Paragraph(_("Status:"), meta_label_style),
                Paragraph(status_text, meta_value_style),
                Paragraph(_("Reviewed By:"), meta_label_style),
                Paragraph(reviewer_info or "—", meta_value_style),
            ],
        ]

        meta_table = Table(meta_data, colWidths=[80, 300, 80, 320])
        meta_table.setStyle(
            TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
                ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ])
        )
        elements.append(meta_table)
        elements.append(Spacer(1, 15))

        # 3. Weekly Hours Grid
        logs = TimeLog.objects.filter(timesheet=timesheet).select_related('task', 'task__project')
        log_map = {(log.task_id, log.date): log for log in logs}

        # Gather distinct tasks that have logs or are assigned
        tasks = list({log.task for log in logs})
        tasks.sort(key=lambda t: (t.project.name, t.title))

        day_names = [_("Mon"), _("Tue"), _("Wed"), _("Thu"), _("Fri"), _("Sat"), _("Sun")]

        grid_header = [
            Paragraph(_("Project"), grid_header_style),
            Paragraph(_("Task"), grid_header_style),
        ]
        for name, date_val in zip(day_names, week_dates):
            date_short = date_val.strftime('%d.%m')
            grid_header.append(Paragraph(f"{name}<br/>{date_short}", grid_header_style))
        grid_header.append(Paragraph(_("Total"), grid_header_style))

        grid_rows = [grid_header]
        daily_totals = [0.0] * 7
        grand_total = 0.0
        comments_list = []

        for task in tasks:
            row = [
                Paragraph(task.project.name, grid_cell_style),
                Paragraph(task.title, grid_cell_style),
            ]
            row_total = 0.0

            for i, current_date in enumerate(week_dates):
                log = log_map.get((task.id, current_date))
                if log and log.hours:
                    hrs = float(log.hours)
                    row_total += hrs
                    daily_totals[i] += hrs
                    grand_total += hrs
                    hrs_text = f"{hrs:g}"
                    if log.comment:
                        comments_list.append((task.title, current_date.strftime('%a, %d.%m'), log.comment))
                else:
                    hrs_text = "—"

                row.append(Paragraph(hrs_text, grid_cell_center))

            row.append(Paragraph(f"<b>{row_total:g}</b>", grid_cell_bold_center))
            grid_rows.append(row)

        # Empty timesheet state
        if not tasks:
            empty_row = [
                Paragraph(_("No time entries recorded for this week."), grid_cell_style),
                Paragraph("", grid_cell_style),
            ]
            empty_row.extend([Paragraph("—", grid_cell_center) for _ in range(7)])
            empty_row.append(Paragraph("0", grid_cell_bold_center))
            grid_rows.append(empty_row)

        # Summary Row (Daily Totals)
        summary_row = [
            Paragraph(f"<b>{_('Total Hours')}</b>", grid_cell_style),
            Paragraph("", grid_cell_style),
        ]
        for total in daily_totals:
            summary_row.append(Paragraph(f"<b>{total:g}</b>", grid_cell_bold_center))
        summary_row.append(Paragraph(f"<b>{grand_total:g}</b>", grid_cell_bold_center))
        grid_rows.append(summary_row)

        # Widths: Project(150), Task(190), Mon-Sun(7*48=336), Total(54) => 730 total (matches landscape page)
        col_widths = [150, 190, 48, 48, 48, 48, 48, 48, 48, 54]
        grid_table = Table(grid_rows, colWidths=col_widths, repeatRows=1)

        t_styles = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#312e81')),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e0e7ff')),
            ('SPAN', (0, -1), (1, -1)),  # Span 'Total Hours' across Project and Task columns
        ]

        # Alternating row colors for data
        for row_idx in range(1, len(grid_rows) - 1):
            if row_idx % 2 == 0:
                t_styles.append(('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor('#f8fafc')))

        grid_table.setStyle(TableStyle(t_styles))
        elements.append(grid_table)
        elements.append(Spacer(1, 15))

        # 4. Comments Section (if any comments were recorded)
        if comments_list:
            comments_header = [
                Paragraph(_("Task"), grid_header_style),
                Paragraph(_("Date"), grid_header_style),
                Paragraph(_("Comment / Work Log Details"), grid_header_style),
            ]
            comments_rows = [comments_header]
            for task_title, dt_str, comment_text in comments_list:
                comments_rows.append([
                    Paragraph(task_title, grid_cell_style),
                    Paragraph(dt_str, grid_cell_center),
                    Paragraph(comment_text, grid_cell_style),
                ])

            comments_table = Table(comments_rows, colWidths=[180, 90, 460])
            c_styles = [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#475569')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]
            for row_idx in range(1, len(comments_rows)):
                if row_idx % 2 == 0:
                    c_styles.append(('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor('#f8fafc')))

            comments_table.setStyle(TableStyle(c_styles))

            elements.append(Paragraph(f"<b>{_('Work Comments & Notes')}</b>", subtitle_style))
            elements.append(Spacer(1, 6))
            elements.append(comments_table)
            elements.append(Spacer(1, 15))

        # 5. Signatures and Timestamp Block
        sig_data = [
            [
                Paragraph(_("Employee Signature: ____________________________________"), meta_label_style),
                Paragraph(_("Date: ________________________"), meta_label_style),
            ],
            [
                Paragraph(_("Manager Signature:  ____________________________________"), meta_label_style),
                Paragraph(_("Date: ________________________"), meta_label_style),
            ],
        ]
        sig_table = Table(sig_data, colWidths=[450, 280])
        sig_table.setStyle(
            TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ])
        )

        footer_text = Paragraph(
            f"{_('Generated by MyProjectsManager')} • {timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            subtitle_style,
        )

        elements.append(KeepTogether([sig_table, Spacer(1, 10), footer_text]))

        # Build Document
        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()

    @classmethod
    def generate_yearly_excel(cls, user, year: int) -> bytes:
        """
        Generates an Excel workbook for an employee's annual work report.
        Contains:
        1. Weekly Summary (Weeks 1..52/53 with status and hours)
        2. Project Breakdown (Distribution across projects and budgets)
        3. Detailed Time Logs (Audit trail of every logged entry)
        """
        wb = openpyxl.Workbook()

        # Common Styles
        header_fill = PatternFill(start_color="312E81", end_color="312E81", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        total_fill = PatternFill(start_color="E0E7FF", end_color="E0E7FF", fill_type="solid")
        total_font = Font(name="Calibri", size=11, bold=True, color="1E1B4B")
        center_align = Alignment(horizontal="center", vertical="center")
        right_align = Alignment(horizontal="right", vertical="center")
        left_align = Alignment(horizontal="left", vertical="center")
        thin_border = Border(
            left=Side(style="thin", color="CBD5E1"),
            right=Side(style="thin", color="CBD5E1"),
            top=Side(style="thin", color="CBD5E1"),
            bottom=Side(style="thin", color="CBD5E1"),
        )

        # ----------------------------------------------------
        # SHEET 1: Weekly Summary
        # ----------------------------------------------------
        ws_summary = wb.active
        ws_summary.title = _("Weekly Summary")
        ws_summary.views.sheetView[0].showGridLines = True

        summary_headers = [
            _("Week #"),
            _("Period Start"),
            _("Period End"),
            _("Status"),
            _("Logged Hours"),
            _("Standard Hours"),
            _("Difference"),
            _("Approved By"),
        ]
        ws_summary.append(summary_headers)

        for col_idx in range(1, len(summary_headers) + 1):
            cell = ws_summary.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center_align

        # Fetch timesheets for this user and year
        timesheets = {
            ts.week_number: ts
            for ts in WeeklyTimesheet.objects.filter(user=user, year=year).select_related('approved_by')
        }

        # Calculate time totals per timesheet
        totals_qs = (
            TimeLog.objects.filter(user=user, date__year=year)
            .values('timesheet__week_number')
            .annotate(total=Sum('hours'))
        )
        week_hours = {item['timesheet__week_number']: float(item['total'] or 0) for item in totals_qs}

        max_weeks = datetime.date(year, 12, 28).isocalendar()[1]

        row_start = 2
        for w in range(1, max_weeks + 1):
            monday = datetime.date.fromisocalendar(year, w, 1)
            sunday = monday + datetime.timedelta(days=6)
            ts = timesheets.get(w)
            status_text = ts.get_status_display() if ts else _("Not Started")
            approver = (ts.approved_by.get_full_name() or ts.approved_by.username) if (ts and ts.approved_by) else ""

            hours = week_hours.get(w, 0.0)
            standard = 40.0
            diff = hours - standard

            row_data = [
                f"W{w:02d}",
                monday.strftime('%Y-%m-%d'),
                sunday.strftime('%Y-%m-%d'),
                status_text,
                hours,
                standard,
                diff,
                approver,
            ]
            ws_summary.append(row_data)

            current_row = ws_summary.max_row
            ws_summary.cell(row=current_row, column=1).alignment = center_align
            ws_summary.cell(row=current_row, column=2).alignment = center_align
            ws_summary.cell(row=current_row, column=3).alignment = center_align
            ws_summary.cell(row=current_row, column=4).alignment = center_align
            ws_summary.cell(row=current_row, column=5).alignment = right_align
            ws_summary.cell(row=current_row, column=6).alignment = right_align
            ws_summary.cell(row=current_row, column=7).alignment = right_align
            ws_summary.cell(row=current_row, column=8).alignment = left_align

            # Number formatting
            ws_summary.cell(row=current_row, column=5).number_format = '0.00'
            ws_summary.cell(row=current_row, column=6).number_format = '0.00'
            ws_summary.cell(row=current_row, column=7).number_format = '+0.00;-0.00;0.00'

            for c in range(1, len(summary_headers) + 1):
                ws_summary.cell(row=current_row, column=c).border = thin_border

        row_end = ws_summary.max_row

        # Summary total row with formulas
        total_row_idx = row_end + 1
        ws_summary.cell(row=total_row_idx, column=1, value=_("Total"))
        ws_summary.cell(row=total_row_idx, column=5, value=f"=SUM(E{row_start}:E{row_end})")
        ws_summary.cell(row=total_row_idx, column=6, value=f"=SUM(F{row_start}:F{row_end})")
        ws_summary.cell(row=total_row_idx, column=7, value=f"=SUM(G{row_start}:G{row_end})")

        ws_summary.cell(row=total_row_idx, column=5).number_format = '0.00'
        ws_summary.cell(row=total_row_idx, column=6).number_format = '0.00'
        ws_summary.cell(row=total_row_idx, column=7).number_format = '+0.00;-0.00;0.00'

        for c in range(1, len(summary_headers) + 1):
            cell = ws_summary.cell(row=total_row_idx, column=c)
            cell.fill = total_fill
            cell.font = total_font
            cell.border = thin_border

        # ----------------------------------------------------
        # SHEET 2: Project Breakdown
        # ----------------------------------------------------
        ws_projects = wb.create_sheet(title=_("Project Breakdown"))
        ws_projects.views.sheetView[0].showGridLines = True

        proj_headers = [
            _("Project Name"),
            _("Project Type"),
            _("Logged Hours"),
            _("% of Annual Time"),
        ]
        ws_projects.append(proj_headers)

        for col_idx in range(1, len(proj_headers) + 1):
            cell = ws_projects.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center_align

        projects_qs = (
            Project.objects.filter(tasks__time_logs__user=user, tasks__time_logs__date__year=year)
            .annotate(user_spent=Sum('tasks__time_logs__hours', filter=Q(tasks__time_logs__user=user, tasks__time_logs__date__year=year)))
            .distinct()
            .order_by('project_type', 'name')
        )

        annual_total_hours = sum(float(p.user_spent or 0) for p in projects_qs)

        p_row_start = 2
        for proj in projects_qs:
            spent = float(proj.user_spent or 0)
            pct = (spent / annual_total_hours) if annual_total_hours > 0 else 0.0

            ws_projects.append([
                proj.name,
                proj.get_project_type_display(),
                spent,
                pct,
            ])

            curr_row = ws_projects.max_row
            ws_projects.cell(row=curr_row, column=1).alignment = left_align
            ws_projects.cell(row=curr_row, column=2).alignment = center_align
            ws_projects.cell(row=curr_row, column=3).alignment = right_align
            ws_projects.cell(row=curr_row, column=4).alignment = right_align

            ws_projects.cell(row=curr_row, column=3).number_format = '0.00'
            ws_projects.cell(row=curr_row, column=4).number_format = '0.0%'

            for c in range(1, len(proj_headers) + 1):
                ws_projects.cell(row=curr_row, column=c).border = thin_border

        p_row_end = ws_projects.max_row
        if p_row_end >= p_row_start:
            p_total_idx = p_row_end + 1
            ws_projects.cell(row=p_total_idx, column=1, value=_("Total"))
            ws_projects.cell(row=p_total_idx, column=3, value=f"=SUM(C{p_row_start}:C{p_row_end})")
            ws_projects.cell(row=p_total_idx, column=4, value=f"=SUM(D{p_row_start}:D{p_row_end})")

            ws_projects.cell(row=p_total_idx, column=3).number_format = '0.00'
            ws_projects.cell(row=p_total_idx, column=4).number_format = '0.0%'

            for c in range(1, len(proj_headers) + 1):
                cell = ws_projects.cell(row=p_total_idx, column=c)
                cell.fill = total_fill
                cell.font = total_font
                cell.border = thin_border

        # ----------------------------------------------------
        # SHEET 3: Detailed Time Logs
        # ----------------------------------------------------
        ws_logs = wb.create_sheet(title=_("Detailed Time Logs"))
        ws_logs.views.sheetView[0].showGridLines = True

        log_headers = [
            _("Date"),
            _("Day of Week"),
            _("Week #"),
            _("Project"),
            _("Task"),
            _("Logged Hours"),
            _("Comment / Details"),
        ]
        ws_logs.append(log_headers)

        for col_idx in range(1, len(log_headers) + 1):
            cell = ws_logs.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center_align

        all_logs = (
            TimeLog.objects.filter(user=user, date__year=year)
            .select_related('task', 'task__project', 'timesheet')
            .order_by('date', 'task__project__name', 'task__title')
        )

        for log in all_logs:
            ws_logs.append([
                log.date.strftime('%Y-%m-%d'),
                log.date.strftime('%A'),
                f"W{log.date.isocalendar()[1]:02d}",
                log.task.project.name,
                log.task.title,
                float(log.hours),
                log.comment or "",
            ])

            curr_row = ws_logs.max_row
            ws_logs.cell(row=curr_row, column=1).alignment = center_align
            ws_logs.cell(row=curr_row, column=2).alignment = center_align
            ws_logs.cell(row=curr_row, column=3).alignment = center_align
            ws_logs.cell(row=curr_row, column=4).alignment = left_align
            ws_logs.cell(row=curr_row, column=5).alignment = left_align
            ws_logs.cell(row=curr_row, column=6).alignment = right_align
            ws_logs.cell(row=curr_row, column=7).alignment = left_align

            ws_logs.cell(row=curr_row, column=6).number_format = '0.00'

            for c in range(1, len(log_headers) + 1):
                ws_logs.cell(row=curr_row, column=c).border = thin_border

        # Auto-adjust column widths across all sheets
        for sheet in [ws_summary, ws_projects, ws_logs]:
            for col in sheet.columns:
                max_len = 0
                col_letter = get_column_letter(col[0].column)
                for cell in col:
                    if cell.value is not None:
                        val_str = str(cell.value)
                        max_len = max(max_len, len(val_str))
                sheet.column_dimensions[col_letter].width = max(max_len + 4, 12)

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()
