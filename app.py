import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import gradio as gr
import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

APP_TIMEZONE = ZoneInfo("Asia/Karachi")

WEEKDAY_MAP = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}


# ============================================================
# CORE CALCULATION HELPERS
# ============================================================

def is_duty(day, first_day, on_count, off_count):
    """
    Determines whether a particular date is a duty day.
    The cycle repeats forward and backward from the first duty day.
    """
    cycle_length = on_count + off_count
    cycle_position = (day - first_day).days % cycle_length
    return cycle_position < on_count


def parse_date(value):
    """Convert YYYY-MM-DD text into Python date."""
    return datetime.strptime(value.strip(), "%Y-%m-%d").date()


def parse_time(value):
    """Convert HH:MM text into Python time."""
    return datetime.strptime(value.strip(), "%H:%M").time()


def formatted_date(day):
    """Friendly date formatting."""
    return day.strftime("%d %b %Y") if day else "—"


def get_next_block_dates(check_date, anchor, days_on, days_off):
    """
    Intelligently determines:
      - When the NEXT off block begins
      - When the NEXT duty block begins
    Works whether user is currently in an ON-duty block or an OFF-duty block.
    """
    currently_duty = is_duty(check_date, anchor, days_on, days_off)

    next_transition = None
    for i in range(1, 366):
        candidate = check_date + timedelta(days=i)
        if is_duty(candidate, anchor, days_on, days_off) != currently_duty:
            next_transition = candidate
            break

    subsequent_transition = None
    if next_transition:
        for i in range(1, 366):
            candidate = next_transition + timedelta(days=i)
            if is_duty(candidate, anchor, days_on, days_off) == currently_duty:
                subsequent_transition = candidate
                break

    if currently_duty:
        return subsequent_transition, next_transition
    else:
        return next_transition, subsequent_transition


def get_cycle_information(day, anchor, days_on, days_off):
    """
    Return position inside ON/OFF rotation.
    """
    cycle_length = days_on + days_off
    cycle_position = ((day - anchor).days % cycle_length) + 1

    if cycle_position <= days_on:
        block_type = "Duty"
        block_position = cycle_position
        block_total = days_on
    else:
        block_type = "Off"
        block_position = cycle_position - days_on
        block_total = days_off

    return (
        cycle_position,
        cycle_length,
        block_type,
        block_position,
        block_total,
    )


# ============================================================
# HTML GENERATORS (Shopeers Analytics Design & Uneditable Tables)
# ============================================================

def create_kpi_cards(
    total_days,
    duty_days,
    off_days,
    weekend_duties,
    total_hours,
    remaining_duty,
    completed_duty,
    avg_weekly_hours,
):
    duty_pct = round((duty_days / total_days * 100), 1) if total_days > 0 else 0
    off_pct = round((off_days / total_days * 100), 1) if total_days > 0 else 0

    return f"""
    <div class="kpi-grid">
        <div class="kpi-card kpi-card-duty">
            <div class="kpi-card-top">
                <div class="kpi-icon-tile icon-duty">💼</div>
                <div class="kpi-badge badge-duty-soft">{duty_pct}% of roster</div>
            </div>
            <div class="kpi-number">{duty_days}</div>
            <div class="kpi-label">Duty Days</div>
            <div class="kpi-footer-note">Scheduled in period</div>
        </div>

        <div class="kpi-card kpi-card-off">
            <div class="kpi-card-top">
                <div class="kpi-icon-tile icon-off">🏠</div>
                <div class="kpi-badge badge-off-soft">{off_pct}% of roster</div>
            </div>
            <div class="kpi-number">{off_days}</div>
            <div class="kpi-label">Off Days</div>
            <div class="kpi-footer-note">Rest & recovery days</div>
        </div>

        <div class="kpi-card kpi-card-weekend">
            <div class="kpi-card-top">
                <div class="kpi-icon-tile icon-weekend">📅</div>
                <div class="kpi-badge badge-weekend-soft">Weekend Shifts</div>
            </div>
            <div class="kpi-number">{weekend_duties}</div>
            <div class="kpi-label">Weekend Duties</div>
            <div class="kpi-footer-note">Active weekend shifts</div>
        </div>

        <div class="kpi-card kpi-card-hours">
            <div class="kpi-card-top">
                <div class="kpi-icon-tile icon-hours">⏱️</div>
                <div class="kpi-badge badge-hours-soft">{avg_weekly_hours} hrs/wk</div>
            </div>
            <div class="kpi-number">{total_hours}</div>
            <div class="kpi-label">Scheduled Hours</div>
            <div class="kpi-footer-note">Total operational time</div>
        </div>

        <div class="kpi-card kpi-card-target">
            <div class="kpi-card-top">
                <div class="kpi-icon-tile icon-target">🎯</div>
                <div class="kpi-badge badge-target-soft">{completed_duty} done</div>
            </div>
            <div class="kpi-number">{remaining_duty}</div>
            <div class="kpi-label">Remaining Duties</div>
            <div class="kpi-footer-note">From check date forward</div>
        </div>
    </div>
    """


def create_status_card(
    active_shift,
    upcoming_shift,
    moment,
    date_status,
    cycle_position,
    cycle_length,
    block_position,
    block_total,
    next_duty,
    next_off,
):
    if active_shift:
        begin, finish = active_shift
        status_class = "status-on"
        status_icon = "🟢"
        main_status = "ACTIVE ON-DUTY SHIFT"

        midnight_note = " (+1 day)" if finish.date() != begin.date() else ""
        shift_text = f"{begin:%H:%M} → {finish:%H:%M}{midnight_note}"

        diff = finish - moment
        total_minutes = max(0, int(diff.total_seconds() // 60))
        hours_left = total_minutes // 60
        mins_left = total_minutes % 60
        extra_text = f"{hours_left}h {mins_left}m remaining in this shift"

    elif upcoming_shift:
        begin, finish = upcoming_shift
        status_class = "status-upcoming"
        status_icon = "⏳"
        main_status = "DUTY DAY — UPCOMING SHIFT"

        midnight_note = " (+1 day)" if finish.date() != begin.date() else ""
        shift_text = f"Starts today: {begin:%H:%M} → {finish:%H:%M}{midnight_note}"

        diff = begin - moment
        total_minutes = max(0, int(diff.total_seconds() // 60))
        hours_until = total_minutes // 60
        mins_until = total_minutes % 60
        extra_text = f"Shift commences in {hours_until}h {mins_until}m"

    else:
        status_class = "status-off"
        status_icon = "🔴"
        main_status = "OFF-DUTY REST PERIOD"
        shift_text = "No active shift right now"
        extra_text = f"Rotation position: {date_status} block ({block_position}/{block_total})"

    next_duty_text = formatted_date(next_duty)
    next_off_text = formatted_date(next_off)
    cycle_percent = round((cycle_position / cycle_length * 100), 1) if cycle_length > 0 else 0

    return f"""
    <div class="status-card {status_class}">
        <div class="status-header-bar">
            <span class="live-pill"><span class="pulse-dot"></span> LIVE DUTY MONITOR</span>
            <span class="status-timestamp">{moment:%A, %d %B %Y • %H:%M} PKT</span>
        </div>

        <div class="status-main-title">
            {status_icon} {main_status}
        </div>

        <div class="status-shift-banner">
            {shift_text}
        </div>

        <div class="status-extra-note">
            {extra_text}
        </div>

        <div class="status-metrics-grid">
            <div class="status-metric-cell">
                <div class="metric-cell-title">🔄 Cycle Progress</div>
                <div class="metric-cell-value">Day {cycle_position} / {cycle_length}</div>
                <div class="metric-mini-bar"><div class="mini-bar-fill" style="width: {cycle_percent}%"></div></div>
            </div>

            <div class="status-metric-cell">
                <div class="metric-cell-title">📍 Current Block</div>
                <div class="metric-cell-value">{date_status} {block_position}/{block_total}</div>
                <div class="metric-cell-sub">Block day {block_position} of {block_total}</div>
            </div>

            <div class="status-metric-cell">
                <div class="metric-cell-title">💼 Next Duty Block</div>
                <div class="metric-cell-value">{next_duty_text}</div>
                <div class="metric-cell-sub">Upcoming ON-duty cycle</div>
            </div>

            <div class="status-metric-cell">
                <div class="metric-cell-title">🏠 Next Off Block</div>
                <div class="metric-cell-value">{next_off_text}</div>
                <div class="metric-cell-sub">Upcoming rest cycle</div>
            </div>
        </div>
    </div>
    """


def render_daily_roster_html(df):
    """
    Renders clean, styled, uneditable HTML table for Full Daily Roster.
    """
    tbody_rows = []
    for _, row in df.iterrows():
        is_duty_day = "Duty" in row["Status"]
        is_weekend = "Weekend" in row["Day Type"]

        status_badge = (
            f'<span class="table-badge badge-duty-pill"><span class="badge-dot dot-green"></span>Duty</span>'
            if is_duty_day
            else f'<span class="table-badge badge-off-pill"><span class="badge-dot dot-gray"></span>Off</span>'
        )

        type_badge = (
            f'<span class="table-badge badge-weekend-pill">🏖 Weekend</span>'
            if is_weekend
            else f'<span class="table-badge badge-weekday-pill">🏢 Weekday</span>'
        )

        timing_display = (
            f'{row["Shift Start"]} → {row["Shift End"]}'
            if is_duty_day
            else '—'
        )

        hours_display = f'<b>{row["Hours"]}h</b>' if row["Hours"] > 0 else '<span class="text-muted">0h</span>'
        row_class = "row-duty" if is_duty_day else "row-off"

        tbody_rows.append(f"""
        <tr class="{row_class}">
            <td class="cell-bold">{row["Date"]}</td>
            <td>{row["Day"]}</td>
            <td>{type_badge}</td>
            <td>{status_badge}</td>
            <td>{timing_display}</td>
            <td>{hours_display}</td>
        </tr>
        """)

    return f"""
    <div class="roster-table-card">
        <div class="table-toolbar">
            <div class="table-toolbar-title">📅 Full Daily Roster Schedule</div>
            <div class="table-toolbar-count">{len(df)} calendar days • Read-only display</div>
        </div>
        <div class="roster-scroll-box">
            <table class="modern-roster-table">
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Day</th>
                        <th>Day Type</th>
                        <th>Status</th>
                        <th>Shift Timing</th>
                        <th>Hours</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(tbody_rows)}
                </tbody>
            </table>
        </div>
    </div>
    """


def render_weekly_roster_html(df):
    """
    Renders aggregated Weekly Roster table in pure HTML/CSS.
    """
    df_temp = df.copy()
    df_temp["Week_Start"] = df_temp["_raw_date"].apply(lambda d: d - timedelta(days=d.weekday()))
    weekly_groups = df_temp.groupby("Week_Start")

    tbody_rows = []
    for w_start, grp in weekly_groups:
        w_min = grp["_raw_date"].min()
        w_max = grp["_raw_date"].max()
        iso_wk = w_start.isocalendar()[1]

        duty_count = (grp["Status"] == "🟢 Duty").sum()
        off_count = (grp["Status"] == "⚪ Off").sum()
        weekend_duty = ((grp["Status"] == "🟢 Duty") & (grp["Day Type"] == "🏖 Weekend")).sum()
        total_hours = grp["Hours"].sum()
        total_days = len(grp)
        workload_pct = round(duty_count / total_days * 100, 1)

        tbody_rows.append(f"""
        <tr>
            <td class="cell-bold">Week {iso_wk}</td>
            <td>{w_min.strftime('%d %b')} – {w_max.strftime('%d %b %Y')}</td>
            <td><span class="table-badge badge-duty-pill">{duty_count} Days</span></td>
            <td><span class="table-badge badge-off-pill">{off_count} Days</span></td>
            <td><b>{weekend_duty}</b></td>
            <td><b>{total_hours}h</b></td>
            <td>
                <div class="workload-pill-wrap">
                    <div class="workload-mini-track">
                        <div class="workload-mini-fill" style="width: {workload_pct}%"></div>
                    </div>
                    <span class="workload-text">{workload_pct}%</span>
                </div>
            </td>
        </tr>
        """)

    return f"""
    <div class="roster-table-card">
        <div class="table-toolbar">
            <div class="table-toolbar-title">🗓️ Weekly Operational Summary</div>
            <div class="table-toolbar-count">Aggregated week-by-week analysis</div>
        </div>
        <div class="roster-scroll-box">
            <table class="modern-roster-table">
                <thead>
                    <tr>
                        <th>Week</th>
                        <th>Date Range</th>
                        <th>Duty Days</th>
                        <th>Off Days</th>
                        <th>Weekend Duties</th>
                        <th>Shift Hours</th>
                        <th>Workload %</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(tbody_rows)}
                </tbody>
            </table>
        </div>
    </div>
    """


def render_monthly_roster_html(df):
    """
    Renders aggregated Monthly Roster table in pure HTML/CSS.
    """
    df_temp = df.copy()
    df_temp["Month_Key"] = df_temp["_raw_date"].apply(lambda d: d.strftime("%Y-%m"))
    monthly_groups = df_temp.groupby("Month_Key")

    tbody_rows = []
    for m_key, grp in monthly_groups:
        sample_date = grp["_raw_date"].iloc[0]
        month_label = sample_date.strftime("%B %Y")
        total_days = len(grp)

        duty_count = (grp["Status"] == "🟢 Duty").sum()
        off_count = (grp["Status"] == "⚪ Off").sum()
        weekend_duty = ((grp["Status"] == "🟢 Duty") & (grp["Day Type"] == "🏖 Weekend")).sum()
        shift_hours = grp["Hours"].sum()
        workload_pct = round(duty_count / total_days * 100, 1)

        tbody_rows.append(f"""
        <tr>
            <td class="cell-bold">{month_label}</td>
            <td>{total_days} days</td>
            <td><span class="table-badge badge-duty-pill">{duty_count} Days</span></td>
            <td><span class="table-badge badge-off-pill">{off_count} Days</span></td>
            <td><b>{weekend_duty}</b></td>
            <td><b>{shift_hours}h</b></td>
            <td>
                <div class="workload-pill-wrap">
                    <div class="workload-mini-track">
                        <div class="workload-mini-fill" style="width: {workload_pct}%"></div>
                    </div>
                    <span class="workload-text">{workload_pct}%</span>
                </div>
            </td>
        </tr>
        """)

    return f"""
    <div class="roster-table-card">
        <div class="table-toolbar">
            <div class="table-toolbar-title">📈 Monthly Workload Distribution</div>
            <div class="table-toolbar-count">High-level month-by-month breakdown</div>
        </div>
        <div class="roster-scroll-box">
            <table class="modern-roster-table">
                <thead>
                    <tr>
                        <th>Month</th>
                        <th>Total Days</th>
                        <th>Duty Days</th>
                        <th>Off Days</th>
                        <th>Weekend Duties</th>
                        <th>Shift Hours</th>
                        <th>Workload %</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(tbody_rows)}
                </tbody>
            </table>
        </div>
    </div>
    """


def render_summary_metrics_html(metrics_dict):
    """
    Renders executive summary cards table in HTML.
    """
    items = [
        ("Calendar Days", f"{metrics_dict['total_days']} days", "🗓️"),
        ("Scheduled Duty Days", f"{metrics_dict['duty_days']} days", "💼"),
        ("Total Off Days", f"{metrics_dict['off_days']} days", "🏠"),
        ("Overall Workload", f"{metrics_dict['workload_pct']}%", "📊"),
        ("Scheduled Shift Hours", f"{metrics_dict['total_hours']} hrs", "⏱️"),
        ("Average Weekly Hours", f"{metrics_dict['avg_weekly_hours']} hrs/wk", "📈"),
        ("Weekend Duties", f"{metrics_dict['weekend_duties']} shifts", "🏖️"),
        ("Completed Duties", f"{metrics_dict['completed_duty']} days", "✅"),
        ("Remaining Duties", f"{metrics_dict['remaining_duty']} days", "🎯"),
        ("Remaining Weekend Duties", f"{metrics_dict['remaining_weekend_duty']} shifts", "📌"),
    ]

    cards_html = []
    for label, val, icon in items:
        cards_html.append(f"""
        <div class="summary-stat-box">
            <div class="stat-box-icon">{icon}</div>
            <div class="stat-box-info">
                <div class="stat-box-label">{label}</div>
                <div class="stat-box-val">{val}</div>
            </div>
        </div>
        """)

    return f"""
    <div class="roster-table-card">
        <div class="table-toolbar">
            <div class="table-toolbar-title">📊 Comprehensive Roster Metrics</div>
            <div class="table-toolbar-count">Calculated dynamically from active configuration</div>
        </div>
        <div class="summary-metrics-grid">
            {"".join(cards_html)}
        </div>
    </div>
    """


# ============================================================
# MAIN ROSTER ENGINE
# ============================================================

def generate_roster(
    anchor_str,
    start_str,
    end_str,
    check_date_str,
    shift_start_str,
    check_time_str,
    shift_hours,
    days_on,
    days_off,
    weekend_names,
):
    try:
        anchor = parse_date(anchor_str)
        range_start = parse_date(start_str)
        range_end = parse_date(end_str)
        check_date = parse_date(check_date_str)

        start_clock = parse_time(shift_start_str)
        selected_clock = parse_time(check_time_str)

        shift_hours = int(shift_hours)
        days_on = int(days_on)
        days_off = int(days_off)

        if range_end < range_start:
            raise ValueError("Roster ending date cannot be before starting date.")

        if days_on <= 0 or days_off <= 0:
            raise ValueError("Days ON and Days OFF must be greater than zero.")

        if shift_hours <= 0 or shift_hours > 24:
            raise ValueError("Shift hours must be between 1 and 24.")

        weekend_names = weekend_names or []
        weekend_set = {
            WEEKDAY_MAP[name]
            for name in weekend_names
            if name in WEEKDAY_MAP
        }

        duration = timedelta(hours=shift_hours)

        # ----------------------------------------------------
        # Build Daily Roster
        # ----------------------------------------------------
        rows = []
        for timestamp in pd.date_range(range_start, range_end, freq="D"):
            day = timestamp.date()
            duty = is_duty(day, anchor, days_on, days_off)
            weekend = day.weekday() in weekend_set

            if duty:
                begin = datetime.combine(day, start_clock)
                finish = begin + duration
                status = "🟢 Duty"
                shift_start_display = begin.strftime("%H:%M")

                if finish.date() != begin.date():
                    shift_end_display = finish.strftime("%H:%M (+1 day)")
                else:
                    shift_end_display = finish.strftime("%H:%M")

                hours = shift_hours
            else:
                status = "⚪ Off"
                shift_start_display = "—"
                shift_end_display = "—"
                hours = 0

            rows.append(
                {
                    "Date": day.strftime("%d %b %Y"),
                    "Day": day.strftime("%A"),
                    "Day Type": "🏖 Weekend" if weekend else "Weekday",
                    "Status": status,
                    "Shift Start": shift_start_display,
                    "Shift End": shift_end_display,
                    "Hours": hours,
                    "_raw_date": day,
                }
            )

        df = pd.DataFrame(rows)

        # ----------------------------------------------------
        # Metrics Calculations
        # ----------------------------------------------------
        duty_mask = df["Status"].eq("🟢 Duty")
        weekend_mask = df["Day Type"].eq("🏖 Weekend")

        total_days = len(df)
        duty_days = int(duty_mask.sum())
        off_days = int((~duty_mask).sum())
        weekend_duties = int((duty_mask & weekend_mask).sum())
        weekday_duties = int((duty_mask & ~weekend_mask).sum())
        total_hours = int(df["Hours"].sum())

        future_mask = df["_raw_date"].apply(lambda x: x >= check_date)
        remaining_duty = int((duty_mask & future_mask).sum())
        remaining_weekend_duty = int((duty_mask & weekend_mask & future_mask).sum())
        completed_duty = max(0, duty_days - remaining_duty)

        workload_pct = round((duty_days / total_days * 100), 1) if total_days > 0 else 0
        avg_weekly_hours = round((total_hours / total_days * 7), 1) if total_days > 0 else 0

        # ----------------------------------------------------
        # Live Shift Detection
        # ----------------------------------------------------
        moment = datetime.combine(check_date, selected_clock)
        active_shift = None
        upcoming_shift = None
        shift_source_date = check_date

        candidates = [check_date - timedelta(days=1), check_date]
        for candidate in candidates:
            if is_duty(candidate, anchor, days_on, days_off):
                begin = datetime.combine(candidate, start_clock)
                finish = begin + duration
                if begin <= moment < finish:
                    active_shift = (begin, finish)
                    shift_source_date = candidate
                    break

        if not active_shift and is_duty(check_date, anchor, days_on, days_off):
            today_begin = datetime.combine(check_date, start_clock)
            today_finish = today_begin + duration
            if moment < today_begin:
                upcoming_shift = (today_begin, today_finish)

        effective_date = shift_source_date if active_shift else check_date
        (
            cycle_position,
            cycle_length,
            block_type,
            block_position,
            block_total,
        ) = get_cycle_information(effective_date, anchor, days_on, days_off)

        date_status = "Duty" if is_duty(effective_date, anchor, days_on, days_off) else "Off"
        next_duty, next_off = get_next_block_dates(check_date, anchor, days_on, days_off)

        # ----------------------------------------------------
        # HTML Output Generation
        # ----------------------------------------------------
        kpi_html = create_kpi_cards(
            total_days,
            duty_days,
            off_days,
            weekend_duties,
            total_hours,
            remaining_duty,
            completed_duty,
            avg_weekly_hours,
        )

        status_html = create_status_card(
            active_shift,
            upcoming_shift,
            moment,
            date_status,
            cycle_position,
            cycle_length,
            block_position,
            block_total,
            next_duty,
            next_off,
        )

        daily_html = render_daily_roster_html(df)
        weekly_html = render_weekly_roster_html(df)
        monthly_html = render_monthly_roster_html(df)

        metrics_dict = {
            "total_days": total_days,
            "duty_days": duty_days,
            "off_days": off_days,
            "workload_pct": workload_pct,
            "total_hours": total_hours,
            "avg_weekly_hours": avg_weekly_hours,
            "weekend_duties": weekend_duties,
            "completed_duty": completed_duty,
            "remaining_duty": remaining_duty,
            "remaining_weekend_duty": remaining_weekend_duty,
        }
        summary_html = render_summary_metrics_html(metrics_dict)

        # CSV Export with UTF-8 BOM
        visible_df = df.drop(columns=["_raw_date"])
        csv_filename = "advanced_duty_roster.csv"
        visible_df.to_csv(csv_filename, index=False, encoding="utf-8-sig")

        return (
            kpi_html,
            status_html,
            daily_html,
            weekly_html,
            monthly_html,
            summary_html,
            csv_filename,
        )

    except Exception as exc:
        err_html = f"""
        <div class="error-card">
            <b>❌ Input Validation Error</b><br>
            {str(exc)}<br><br>
            Please check Date format (YYYY-MM-DD) and Time format (HH:MM).
        </div>
        """
        return ("", err_html, err_html, err_html, err_html, err_html, None)


# ============================================================
# EVENT HANDLERS & PRESETS
# ============================================================

def handle_shift_preset(choice):
    """
    Quickly selects standard 12-hour operational shifts or custom mode.
    """
    if "07:00 – 19:00" in choice or "Day" in choice:
        return "07:00", 12
    elif "19:00 – 07:00" in choice or "Night" in choice:
        return "19:00", 12
    return gr.update(), gr.update()


def use_current_live_time():
    """
    Samples real-time in Pakistan timezone.
    """
    now = datetime.now(APP_TIMEZONE)
    return now.strftime("%Y-%m-%d"), now.strftime("%H:%M")


def load_live_roster_on_open(
    anchor_str,
    start_str,
    end_str,
    shift_start_str,
    shift_hours,
    days_on,
    days_off,
    weekend_names,
):
    """
    Executed dynamically whenever any user opens the website.
    Ensures check date, check time, and all KPIs reflect the exact current second!
    """
    live_date, live_time = use_current_live_time()
    results = generate_roster(
        anchor_str,
        start_str,
        end_str,
        live_date,
        shift_start_str,
        live_time,
        shift_hours,
        days_on,
        days_off,
        weekend_names,
    )
    return (live_date, live_time, *results)


# ============================================================
# CSS (Shopeers B2B Analytics Aesthetic)
# ============================================================

css = """
/* ==========================================================
   GLOBAL LAYOUT & FONTS
   ========================================================== */

.gradio-container {
    max-width: 1520px !important;
    margin: auto !important;
    padding: 16px 20px !important;
    background-color: #f8fafc !important;
}

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    color: #1e293b;
    background-color: #f8fafc;
}

/* ==========================================================
   HEADER / HERO
   ========================================================== */

.hero {
    padding: 24px 30px;
    border-radius: 20px;
    margin-bottom: 20px;
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%);
    color: #ffffff;
    box-shadow: 0 10px 30px -8px rgba(15, 23, 42, 0.25);
    border: 1px solid rgba(255, 255, 255, 0.08);
}

.hero-title {
    font-size: 27px;
    font-weight: 850;
    letter-spacing: -0.5px;
    margin-bottom: 4px;
    display: flex;
    align-items: center;
    gap: 8px;
}

.hero-subtitle {
    font-size: 13.5px;
    opacity: 0.85;
    font-weight: 450;
}

/* ==========================================================
   KPI CARDS (Shopeers Analytics Grid)
   ========================================================== */

.kpi-grid {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 14px;
    margin: 4px 0 20px 0;
}

.kpi-card {
    background: #ffffff;
    border-radius: 18px;
    padding: 18px;
    border: 1px solid #e2e8f0;
    box-shadow: 0 4px 18px -2px rgba(15, 23, 42, 0.04);
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
    display: flex;
    flex-direction: column;
}

.kpi-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 12px 28px -4px rgba(15, 23, 42, 0.09);
    border-color: #cbd5e1;
}

.kpi-card-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
}

.kpi-icon-tile {
    width: 42px;
    height: 42px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
}

.icon-duty { background: #ecfdf5; }
.icon-off { background: #f1f5f9; }
.icon-weekend { background: #fef3c7; }
.icon-hours { background: #ede9fe; }
.icon-target { background: #e0f2fe; }

.kpi-badge {
    font-size: 11.5px;
    font-weight: 700;
    padding: 3px 9px;
    border-radius: 20px;
    letter-spacing: 0.2px;
}

.badge-duty-soft { background: #d1fae5; color: #065f46; }
.badge-off-soft { background: #e2e8f0; color: #334155; }
.badge-weekend-soft { background: #fde68a; color: #92400e; }
.badge-hours-soft { background: #ddd6fe; color: #5b21b6; }
.badge-target-soft { background: #bae6fd; color: #075985; }

.kpi-number {
    font-size: 32px;
    font-weight: 850;
    color: #0f172a;
    letter-spacing: -1px;
    line-height: 1.1;
    margin-bottom: 4px;
}

.kpi-label {
    font-size: 13px;
    font-weight: 700;
    color: #475569;
    margin-bottom: 2px;
}

.kpi-footer-note {
    font-size: 11.5px;
    color: #94a3b8;
    font-weight: 500;
}

/* ==========================================================
   LIVE STATUS CARD
   ========================================================== */

.status-card {
    padding: 24px;
    border-radius: 20px;
    margin-bottom: 20px;
    box-shadow: 0 8px 24px -4px rgba(15, 23, 42, 0.06);
    border: 1px solid #e2e8f0;
    background: #ffffff;
}

.status-header-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
}

.live-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: #f1f5f9;
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 1px;
    color: #334155;
}

.pulse-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #10b981;
    display: inline-block;
    box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7);
    animation: pulse 1.6s infinite;
}

@keyframes pulse {
    0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
    70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
    100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
}

.status-timestamp {
    font-size: 12.5px;
    font-weight: 600;
    color: #64748b;
}

.status-main-title {
    font-size: 26px;
    font-weight: 850;
    letter-spacing: -0.5px;
    margin-bottom: 6px;
}

.status-on .status-main-title { color: #047857; }
.status-upcoming .status-main-title { color: #b45309; }
.status-off .status-main-title { color: #b91c1c; }

.status-shift-banner {
    font-size: 21px;
    font-weight: 800;
    color: #0f172a;
    margin-bottom: 4px;
}

.status-extra-note {
    font-size: 13px;
    font-weight: 600;
    color: #64748b;
    margin-bottom: 20px;
}

.status-metrics-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
}

.status-metric-cell {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 12px;
}

.metric-cell-title {
    font-size: 11px;
    font-weight: 700;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 4px;
}

.metric-cell-value {
    font-size: 15px;
    font-weight: 800;
    color: #0f172a;
}

.metric-cell-sub {
    font-size: 11px;
    color: #94a3b8;
    margin-top: 2px;
}

.metric-mini-bar {
    width: 100%;
    height: 4px;
    background: #e2e8f0;
    border-radius: 4px;
    margin-top: 6px;
    overflow: hidden;
}

.mini-bar-fill {
    height: 100%;
    background: #6366f1;
    border-radius: 4px;
}

/* ==========================================================
   UNEDITABLE HTML ROSTER TABLES
   ========================================================== */

.roster-table-card {
    background: #ffffff;
    border-radius: 18px;
    border: 1px solid #e2e8f0;
    box-shadow: 0 4px 20px -2px rgba(15, 23, 42, 0.04);
    overflow: hidden;
    margin-top: 6px;
}

.table-toolbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 20px;
    border-bottom: 1px solid #e2e8f0;
    background: #ffffff;
}

.table-toolbar-title {
    font-size: 15px;
    font-weight: 800;
    color: #0f172a;
}

.table-toolbar-count {
    font-size: 12px;
    font-weight: 600;
    color: #64748b;
}

.roster-scroll-box {
    max-height: 520px;
    overflow-y: auto;
    overflow-x: auto;
}

.modern-roster-table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    font-size: 13.5px;
    text-align: left;
}

.modern-roster-table thead th {
    position: sticky;
    top: 0;
    z-index: 2;
    background: #f8fafc;
    color: #475569;
    font-weight: 700;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 12px 16px;
    border-bottom: 1px solid #e2e8f0;
}

.modern-roster-table tbody tr {
    transition: background 0.15s ease;
}

.modern-roster-table tbody tr:hover {
    background: #f1f5f9 !important;
}

.modern-roster-table tbody td {
    padding: 11px 16px;
    border-bottom: 1px solid #f1f5f9;
    color: #334155;
    user-select: text;
}

.cell-bold {
    font-weight: 700;
    color: #0f172a;
}

.text-muted {
    color: #94a3b8;
}

/* ==========================================================
   BADGES & PROGRESS BARS
   ========================================================== */

.table-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 9px;
    border-radius: 12px;
    font-size: 11.5px;
    font-weight: 700;
    line-height: 1.2;
}

.badge-duty-pill { background: #ecfdf5; color: #065f46; border: 1px solid #a7f3d0; }
.badge-off-pill { background: #f8fafc; color: #64748b; border: 1px solid #e2e8f0; }
.badge-weekend-pill { background: #fffbeb; color: #b45309; border: 1px solid #fde68a; }
.badge-weekday-pill { background: #f8fafc; color: #475569; border: 1px solid #e2e8f0; }

.badge-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
}
.dot-green { background: #10b981; }
.dot-gray { background: #94a3b8; }

.workload-pill-wrap {
    display: flex;
    align-items: center;
    gap: 8px;
}

.workload-mini-track {
    width: 80px;
    height: 6px;
    background: #e2e8f0;
    border-radius: 4px;
    overflow: hidden;
}

.workload-mini-fill {
    height: 100%;
    background: linear-gradient(90deg, #6366f1, #3b82f6);
    border-radius: 4px;
}

.workload-text {
    font-size: 12px;
    font-weight: 700;
    color: #334155;
}

/* ==========================================================
   EXECUTIVE SUMMARY METRICS GRID
   ========================================================== */

.summary-metrics-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 12px;
    padding: 16px;
}

.summary-stat-box {
    display: flex;
    align-items: center;
    gap: 12px;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 12px 14px;
}

.stat-box-icon {
    font-size: 22px;
}

.stat-box-label {
    font-size: 12px;
    color: #64748b;
    font-weight: 600;
}

.stat-box-val {
    font-size: 16px;
    color: #0f172a;
    font-weight: 800;
}

/* ==========================================================
   BUTTONS & PRESETS
   ========================================================== */

.preset-btn {
    border-radius: 10px !important;
    font-size: 12px !important;
    font-weight: 600 !important;
}

.generate-btn {
    background: linear-gradient(135deg, #4f46e5 0%, #6366f1 100%) !important;
    color: #ffffff !important;
    border: none !important;
    font-weight: 800 !important;
    font-size: 15px !important;
    border-radius: 14px !important;
    padding: 12px !important;
    box-shadow: 0 4px 14px rgba(79, 70, 229, 0.35) !important;
    transition: all 0.2s ease !important;
}

.generate-btn:hover {
    box-shadow: 0 8px 20px rgba(79, 70, 229, 0.45) !important;
    transform: translateY(-1px) !important;
}

.error-card {
    background: #fef2f2;
    border: 1px solid #fecaca;
    color: #991b1b;
    border-radius: 14px;
    padding: 16px;
    font-size: 13.5px;
}

/* ==========================================================
   RESPONSIVE QUERIES
   ========================================================== */

@media (max-width: 1100px) {
    .kpi-grid { grid-template-columns: repeat(3, 1fr); }
    .status-metrics-grid { grid-template-columns: repeat(2, 1fr); }
}

@media (max-width: 700px) {
    .kpi-grid { grid-template-columns: 1fr; }
    .status-metrics-grid { grid-template-columns: 1fr; }
    .summary-metrics-grid { grid-template-columns: 1fr; }
    .hero-title { font-size: 22px; }
}
"""


# ============================================================
# INITIAL VALUES (Dynamic default time)
# ============================================================

init_now = datetime.now(APP_TIMEZONE)
default_today = init_now.strftime("%Y-%m-%d")
default_time = init_now.strftime("%H:%M")


# ============================================================
# GRADIO FRONTEND
# ============================================================

with gr.Blocks(
    css=css,
    theme=gr.themes.Soft(),
    title="CNOC Duty Roster & Analytics",
) as demo:

    # --------------------------------------------------------
    # Header Banner
    # --------------------------------------------------------
    gr.HTML(
        """
        <div class="hero" style="background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%) !important;">
            <div class="hero-title">
                ⚡ CNOC Advanced Shift & Duty Analytics
            </div>
            <div class="hero-subtitle">
                Rotational roster planning • Real-time shift tracking • Uneditable analytics tables • Excel UTF-8 export
            </div>
        </div>
        """
    )

    # --------------------------------------------------------
    # Top KPI Metrics Cards
    # --------------------------------------------------------
    kpi_output = gr.HTML()

    # --------------------------------------------------------
    # Main Operations Area
    # --------------------------------------------------------
    with gr.Row():

        # ====================================================
        # LEFT COLUMN: Configuration & Controls
        # ====================================================
        with gr.Column(scale=1, min_width=340):

            gr.Markdown("### ⚙️ Roster Dates & Range")

            anchor = gr.Textbox(
                label="📌 First Duty Day (Anchor)",
                value=default_today,
                placeholder="YYYY-MM-DD",
                info="Day 1 of any ON-duty block (projects forward & back)",
            )

            with gr.Row():
                range_start = gr.Textbox(
                    label="📅 From",
                    value=default_today,
                    placeholder="YYYY-MM-DD",
                )
                range_end = gr.Textbox(
                    label="📅 To",
                    value=f"{init_now.year}-12-31",
                    placeholder="YYYY-MM-DD",
                )

            gr.Markdown("### 🔄 Rotation & Presets")

            with gr.Row():
                days_on = gr.Number(
                    label="Days ON (Manual)",
                    value=4,
                    minimum=1,
                    maximum=60,
                    precision=0,
                )
                days_off = gr.Number(
                    label="Days OFF (Manual)",
                    value=4,
                    minimum=1,
                    maximum=60,
                    precision=0,
                )

            gr.Markdown("**Quick Rotation Presets**")

            with gr.Row():
                preset44 = gr.Button("4 ON / 4 OFF", size="sm", elem_classes=["preset-btn"])
                preset52 = gr.Button("5 ON / 2 OFF", size="sm", elem_classes=["preset-btn"])
                preset33 = gr.Button("3 ON / 3 OFF", size="sm", elem_classes=["preset-btn"])

            with gr.Row():
                preset77 = gr.Button("7 ON / 7 OFF", size="sm", elem_classes=["preset-btn"])
                preset1414 = gr.Button("14 ON / 14 OFF", size="sm", elem_classes=["preset-btn"])
                preset22 = gr.Button("2 ON / 2 OFF", size="sm", elem_classes=["preset-btn"])

            with gr.Row():
                preset63 = gr.Button("6 ON / 3 OFF", size="sm", elem_classes=["preset-btn"])
                preset2121 = gr.Button("21 ON / 21 OFF", size="sm", elem_classes=["preset-btn"])
                preset_custom = gr.Button("Manual", size="sm", elem_classes=["preset-btn"])

            gr.Markdown("### ⏱️ Shift Timing (12h Operations)")

            shift_preset = gr.Radio(
                label="Duty Shift Selection",
                choices=[
                    "☀️ Day Shift (07:00 – 19:00)",
                    "🌙 Night Shift (19:00 – 07:00)",
                    "⚙️ Custom Hours",
                ],
                value="☀️ Day Shift (07:00 – 19:00)",
                info="Select 12h operational shift or configure custom times",
            )

            with gr.Row():
                shift_start = gr.Textbox(
                    label="Shift Start",
                    value="07:00",
                    placeholder="HH:MM",
                )
                shift_hours = gr.Number(
                    label="Shift Hours",
                    value=12,
                    minimum=1,
                    maximum=24,
                    precision=0,
                )

            weekends = gr.CheckboxGroup(
                label="🏖 Weekend Days",
                choices=list(WEEKDAY_MAP.keys()),
                value=["Saturday", "Sunday"],
            )

            gr.Markdown("### 🕒 Real-Time Status Check")

            with gr.Row():
                check_date = gr.Textbox(
                    label="Check Date",
                    value=default_today,
                    placeholder="YYYY-MM-DD",
                )
                check_time = gr.Textbox(
                    label="Check Time",
                    value=default_time,
                    placeholder="HH:MM",
                )

            current_btn = gr.Button(
                "🕒 Sync Current Pakistan Time",
                variant="secondary",
            )

            generate_btn = gr.Button(
                "🚀 Calculate & Analyze Roster",
                variant="primary",
                elem_classes=["generate-btn"],
            )

        # ====================================================
        # RIGHT COLUMN: Live Monitor & Tabs for HTML Tables
        # ====================================================
        with gr.Column(scale=2, min_width=600):

            # Live Status Monitor
            status_output = gr.HTML()

            # Output Tabs (Pure Uneditable HTML Tables)
            with gr.Tabs():
                with gr.TabItem("📅 Daily Roster"):
                    daily_output = gr.HTML()

                with gr.TabItem("🗓️ Weekly Roster"):
                    weekly_output = gr.HTML()

                with gr.TabItem("📈 Monthly Roster"):
                    monthly_output = gr.HTML()

                with gr.TabItem("📊 Executive Metrics"):
                    summary_output = gr.HTML()

            with gr.Row():
                download_file = gr.File(
                    label="📥 Download Complete Roster (Excel UTF-8 Compatible CSV)"
                )

    # ========================================================
    # INPUTS & OUTPUTS BINDING
    # ========================================================
    inputs = [
        anchor,
        range_start,
        range_end,
        check_date,
        shift_start,
        check_time,
        shift_hours,
        days_on,
        days_off,
        weekends,
    ]

    outputs = [
        kpi_output,
        status_output,
        daily_output,
        weekly_output,
        monthly_output,
        summary_output,
        download_file,
    ]

    # --------------------------------------------------------
    # EVENT HANDLERS
    # --------------------------------------------------------

    # Manual Generate Click
    generate_btn.click(
        fn=generate_roster,
        inputs=inputs,
        outputs=outputs,
    )

    # Shift Timing Preset Click (Updates start time & hours and triggers re-calc)
    shift_preset.change(
        fn=handle_shift_preset,
        inputs=[shift_preset],
        outputs=[shift_start, shift_hours],
    ).then(
        fn=generate_roster,
        inputs=inputs,
        outputs=outputs,
    )

    # Sync Live Time Click
    current_btn.click(
        fn=use_current_live_time,
        inputs=[],
        outputs=[check_date, check_time],
    ).then(
        fn=generate_roster,
        inputs=inputs,
        outputs=outputs,
    )

    # Rotation Preset Handlers (Instant auto-refresh)
    preset44.click(
        fn=lambda: (4, 4),
        inputs=[],
        outputs=[days_on, days_off],
    ).then(fn=generate_roster, inputs=inputs, outputs=outputs)

    preset52.click(
        fn=lambda: (5, 2),
        inputs=[],
        outputs=[days_on, days_off],
    ).then(fn=generate_roster, inputs=inputs, outputs=outputs)

    preset33.click(
        fn=lambda: (3, 3),
        inputs=[],
        outputs=[days_on, days_off],
    ).then(fn=generate_roster, inputs=inputs, outputs=outputs)

    preset77.click(
        fn=lambda: (7, 7),
        inputs=[],
        outputs=[days_on, days_off],
    ).then(fn=generate_roster, inputs=inputs, outputs=outputs)

    preset1414.click(
        fn=lambda: (14, 14),
        inputs=[],
        outputs=[days_on, days_off],
    ).then(fn=generate_roster, inputs=inputs, outputs=outputs)

    preset22.click(
        fn=lambda: (2, 2),
        inputs=[],
        outputs=[days_on, days_off],
    ).then(fn=generate_roster, inputs=inputs, outputs=outputs)

    preset63.click(
        fn=lambda: (6, 3),
        inputs=[],
        outputs=[days_on, days_off],
    ).then(fn=generate_roster, inputs=inputs, outputs=outputs)

    preset2121.click(
        fn=lambda: (21, 21),
        inputs=[],
        outputs=[days_on, days_off],
    ).then(fn=generate_roster, inputs=inputs, outputs=outputs)

    preset_custom.click(
        fn=lambda: (gr.update(), gr.update()),
        inputs=[],
        outputs=[days_on, days_off],
    )

    # --------------------------------------------------------
    # REAL-TIME DYNAMIC CALCULATION ON OPEN
    # --------------------------------------------------------
    demo.load(
        fn=load_live_roster_on_open,
        inputs=[
            anchor,
            range_start,
            range_end,
            shift_start,
            shift_hours,
            days_on,
            days_off,
            weekends,
        ],
        outputs=[check_date, check_time, *outputs],
    )


# ============================================================
# LAUNCH
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    demo.launch(
        server_name="0.0.0.0",
        server_port=port,
    )
