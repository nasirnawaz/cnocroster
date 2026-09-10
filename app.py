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
# HELPER FUNCTIONS
# ============================================================

def is_duty(day, first_day, on_count, off_count):
    """
    Determines whether a particular date is a duty day.

    The cycle repeats both forward and backward from the
    first duty day.
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
    return day.strftime("%d %b %Y")


def find_next_status_day(
    start_day,
    anchor,
    days_on,
    days_off,
    target_duty=True,
    include_today=False,
):
    """
    Find next duty or off date.
    """

    offset = 0 if include_today else 1

    for i in range(offset, 366):
        candidate = start_day + timedelta(days=i)

        duty = is_duty(
            candidate,
            anchor,
            days_on,
            days_off
        )

        if duty == target_duty:
            return candidate

    return None


def get_cycle_information(day, anchor, days_on, days_off):
    """
    Return position inside ON/OFF rotation.
    """

    cycle_length = days_on + days_off

    cycle_position = (
        (day - anchor).days % cycle_length
    ) + 1

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
# DASHBOARD HTML GENERATORS
# ============================================================

def create_kpi_cards(
    duty_days,
    off_days,
    weekend_duties,
    total_hours,
    remaining_duty,
):
    return f"""
    <div class="kpi-grid">

        <div class="kpi-card duty-card">
            <div class="kpi-icon">💼</div>
            <div class="kpi-number">{duty_days}</div>
            <div class="kpi-label">Duty Days</div>
        </div>

        <div class="kpi-card off-card">
            <div class="kpi-icon">🏠</div>
            <div class="kpi-number">{off_days}</div>
            <div class="kpi-label">Off Days</div>
        </div>

        <div class="kpi-card weekend-card">
            <div class="kpi-icon">📅</div>
            <div class="kpi-number">{weekend_duties}</div>
            <div class="kpi-label">Weekend Duties</div>
        </div>

        <div class="kpi-card hours-card">
            <div class="kpi-icon">⏱️</div>
            <div class="kpi-number">{total_hours}</div>
            <div class="kpi-label">Scheduled Hours</div>
        </div>

        <div class="kpi-card remaining-card">
            <div class="kpi-icon">🎯</div>
            <div class="kpi-number">{remaining_duty}</div>
            <div class="kpi-label">Remaining Duties</div>
        </div>

    </div>
    """


def create_status_card(
    active_shift,
    moment,
    date_status,
    cycle_position,
    cycle_length,
    block_position,
    block_total,
    next_duty,
    next_off,
):
    """
    Create modern live-duty status panel.
    """

    if active_shift:
        begin, finish = active_shift

        status_class = "status-on"
        status_icon = "🟢"
        main_status = "YOU ARE ON DUTY"

        shift_text = (
            f"{begin:%H:%M} → {finish:%H:%M}"
        )

        difference = finish - moment

        total_minutes = max(
            0,
            int(difference.total_seconds() // 60)
        )

        hours_left = total_minutes // 60
        minutes_left = total_minutes % 60

        extra_text = (
            f"{hours_left}h {minutes_left}m remaining"
        )

    else:

        status_class = "status-off"
        status_icon = "🔴"
        main_status = "YOU ARE OFF DUTY"
        shift_text = "No active shift right now"
        extra_text = f"Roster date status: {date_status}"

    next_duty_text = (
        formatted_date(next_duty)
        if next_duty
        else "—"
    )

    next_off_text = (
        formatted_date(next_off)
        if next_off
        else "—"
    )

    return f"""
    <div class="status-card {status_class}">

        <div class="status-small">
            LIVE DUTY STATUS
        </div>

        <div class="status-main">
            {status_icon} {main_status}
        </div>

        <div class="status-time">
            {moment:%A, %d %B %Y • %H:%M}
        </div>

        <div class="shift-display">
            {shift_text}
        </div>

        <div class="status-extra">
            {extra_text}
        </div>

        <div class="status-info-grid">

            <div class="status-info-box">
                <div class="info-title">
                    🔄 Cycle
                </div>
                <div class="info-value">
                    Day {cycle_position} / {cycle_length}
                </div>
            </div>

            <div class="status-info-box">
                <div class="info-title">
                    📍 Current Block
                </div>
                <div class="info-value">
                    {date_status} {block_position}/{block_total}
                </div>
            </div>

            <div class="status-info-box">
                <div class="info-title">
                    💼 Next Duty
                </div>
                <div class="info-value">
                    {next_duty_text}
                </div>
            </div>

            <div class="status-info-box">
                <div class="info-title">
                    🏠 Next Off
                </div>
                <div class="info-value">
                    {next_off_text}
                </div>
            </div>

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

        # ----------------------------------------------------
        # Convert / validate inputs
        # ----------------------------------------------------

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
            raise ValueError(
                "Roster ending date cannot be before starting date."
            )

        if days_on <= 0 or days_off <= 0:
            raise ValueError(
                "Days ON and Days OFF must be greater than zero."
            )

        if shift_hours <= 0 or shift_hours > 24:
            raise ValueError(
                "Shift hours must be between 1 and 24."
            )

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

        for timestamp in pd.date_range(
            range_start,
            range_end,
            freq="D"
        ):

            day = timestamp.date()

            duty = is_duty(
                day,
                anchor,
                days_on,
                days_off
            )

            weekend = day.weekday() in weekend_set

            if duty:

                begin = datetime.combine(
                    day,
                    start_clock
                )

                finish = begin + duration

                status = "🟢 Duty"

                shift_start_display = begin.strftime("%H:%M")

                # Show date as well when shift crosses midnight
                if finish.date() != begin.date():
                    shift_end_display = finish.strftime(
                        "%H:%M (+1 day)"
                    )
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
                    "Day Type": (
                        "🏖 Weekend"
                        if weekend
                        else "Weekday"
                    ),
                    "Status": status,
                    "Shift Start": shift_start_display,
                    "Shift End": shift_end_display,
                    "Hours": hours,
                    "_raw_date": day,
                }
            )

        df = pd.DataFrame(rows)

        # ----------------------------------------------------
        # Masks
        # ----------------------------------------------------

        duty_mask = df["Status"].eq("🟢 Duty")

        weekend_mask = df["Day Type"].eq(
            "🏖 Weekend"
        )

        duty_days = int(duty_mask.sum())

        off_days = int((~duty_mask).sum())

        weekend_duties = int(
            (duty_mask & weekend_mask).sum()
        )

        weekday_duties = int(
            (duty_mask & ~weekend_mask).sum()
        )

        weekends_off = int(
            (~duty_mask & weekend_mask).sum()
        )

        total_hours = int(df["Hours"].sum())

        # ----------------------------------------------------
        # Remaining duty calculations
        # ----------------------------------------------------

        future_mask = df["_raw_date"].apply(
            lambda x: x >= check_date
        )

        remaining_duty = int(
            (duty_mask & future_mask).sum()
        )

        remaining_weekend_duty = int(
            (
                duty_mask
                & weekend_mask
                & future_mask
            ).sum()
        )

        # ----------------------------------------------------
        # Check current/selected time
        # ----------------------------------------------------

        moment = datetime.combine(
            check_date,
            selected_clock
        )

        active_shift = None

        # Previous day required because a shift may cross midnight
        candidates = [
            check_date - timedelta(days=1),
            check_date,
        ]

        for candidate in candidates:

            if is_duty(
                candidate,
                anchor,
                days_on,
                days_off
            ):

                begin = datetime.combine(
                    candidate,
                    start_clock
                )

                finish = begin + duration

                if begin <= moment < finish:

                    active_shift = (
                        begin,
                        finish
                    )

                    break

        # ----------------------------------------------------
        # Cycle information
        # ----------------------------------------------------

        (
            cycle_position,
            cycle_length,
            block_type,
            block_position,
            block_total,
        ) = get_cycle_information(
            check_date,
            anchor,
            days_on,
            days_off,
        )

        date_duty = is_duty(
            check_date,
            anchor,
            days_on,
            days_off
        )

        date_status = (
            "Duty"
            if date_duty
            else "Off"
        )

        # ----------------------------------------------------
        # Next duty/off dates
        # ----------------------------------------------------

        next_duty = find_next_status_day(
            check_date,
            anchor,
            days_on,
            days_off,
            target_duty=True,
            include_today=False,
        )

        next_off = find_next_status_day(
            check_date,
            anchor,
            days_on,
            days_off,
            target_duty=False,
            include_today=False,
        )

        # ----------------------------------------------------
        # KPI cards
        # ----------------------------------------------------

        kpi_html = create_kpi_cards(
            duty_days,
            off_days,
            weekend_duties,
            total_hours,
            remaining_duty,
        )

        # ----------------------------------------------------
        # Status card
        # ----------------------------------------------------

        status_html = create_status_card(
            active_shift,
            moment,
            date_status,
            cycle_position,
            cycle_length,
            block_position,
            block_total,
            next_duty,
            next_off,
        )

        # ----------------------------------------------------
        # Summary
        # ----------------------------------------------------

        summary = pd.DataFrame(
            {
                "📊 Measure": [
                    "Calendar Days",
                    "Duty Days",
                    "Off Days",
                    "Calendar Weekdays",
                    "Calendar Weekend Days",
                    "Duty on Weekdays",
                    "Duty on Weekends",
                    "Weekends Off",
                    "Scheduled Shift Hours",
                    "Remaining Duty Days",
                    "Remaining Weekend Duties",
                ],
                "Total": [
                    len(df),
                    duty_days,
                    off_days,
                    int((~weekend_mask).sum()),
                    int(weekend_mask.sum()),
                    weekday_duties,
                    weekend_duties,
                    weekends_off,
                    total_hours,
                    remaining_duty,
                    remaining_weekend_duty,
                ],
            }
        )

        # ----------------------------------------------------
        # Monthly breakdown
        # ----------------------------------------------------

        monthly_source = df.copy()

        monthly_source["Month"] = (
            monthly_source["_raw_date"]
            .apply(lambda x: x.strftime("%Y-%m"))
        )

        monthly_source["Duty_days"] = (
            duty_mask.astype(int)
        )

        monthly_source["Off_days"] = (
            (~duty_mask).astype(int)
        )

        monthly_source["Weekend_duties"] = (
            duty_mask & weekend_mask
        ).astype(int)

        monthly = (
            monthly_source
            .groupby(
                "Month",
                as_index=False
            )
            .agg(
                Duty_days=("Duty_days", "sum"),
                Off_days=("Off_days", "sum"),
                Weekend_duties=(
                    "Weekend_duties",
                    "sum"
                ),
                Shift_hours=("Hours", "sum"),
            )
        )

        monthly["Total_days"] = (
            monthly["Duty_days"]
            + monthly["Off_days"]
        )

        monthly["Workload_%"] = (
            (
                monthly["Duty_days"]
                / monthly["Total_days"]
            )
            * 100
        ).round(1)

        monthly.rename(
            columns={
                "Month": "Month",
                "Duty_days": "Duty Days",
                "Off_days": "Off Days",
                "Weekend_duties": "Weekend Duties",
                "Shift_hours": "Shift Hours",
                "Workload_%": "Workload %",
            },
            inplace=True,
        )

        monthly.drop(
            columns=["Total_days"],
            inplace=True,
        )

        # ----------------------------------------------------
        # Clean visible roster
        # ----------------------------------------------------

        visible_df = df.drop(
            columns=["_raw_date"]
        )

        # ----------------------------------------------------
        # CSV export
        # ----------------------------------------------------

        csv_filename = "advanced_duty_roster.csv"

        visible_df.to_csv(
            csv_filename,
            index=False
        )

        return (
            kpi_html,
            status_html,
            summary,
            monthly,
            visible_df,
            csv_filename,
        )

    except Exception as exc:

        error_html = f"""
        <div class="error-card">
            <b>❌ Input Error</b><br>
            {str(exc)}
            <br><br>
            Date format: YYYY-MM-DD<br>
            Time format: HH:MM
        </div>
        """

        return (
            "",
            error_html,
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(),
            None,
        )


# ============================================================
# CURRENT TIME BUTTON
# ============================================================

def use_current_time():

    now = datetime.now(APP_TIMEZONE)

    return (
        now.strftime("%Y-%m-%d"),
        now.strftime("%H:%M"),
    )


# ============================================================
# PRESET FUNCTIONS
# ============================================================

def preset_4_4():
    return 4, 4


def preset_5_2():
    return 5, 2


def preset_7_7():
    return 7, 7


def preset_14_14():
    return 14, 14


# ============================================================
# CSS
# ============================================================

css = """

/* ==========================================================
   GLOBAL
   ========================================================== */

.gradio-container {
    max-width: 1450px !important;
    margin: auto !important;
    padding-top: 20px !important;
}

body {
    font-family:
        Inter,
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
}


/* ==========================================================
   HEADER
   ========================================================== */

.hero {
    padding: 25px 30px;
    border-radius: 20px;
    margin-bottom: 20px;

    background:
        linear-gradient(
            135deg,
            #111827,
            #1f2937
        );

    color: white;

    box-shadow:
        0 12px 30px
        rgba(0,0,0,0.12);
}

.hero-title {
    font-size: 31px;
    font-weight: 800;
    margin-bottom: 6px;
}

.hero-subtitle {
    font-size: 14px;
    opacity: 0.82;
}


/* ==========================================================
   KPI
   ========================================================== */

.kpi-grid {

    display: grid;

    grid-template-columns:
        repeat(5, 1fr);

    gap: 12px;

    margin:
        5px 0
        20px 0;
}

.kpi-card {

    padding:
        18px 12px;

    border-radius:
        16px;

    text-align:
        center;

    background:
        var(--block-background-fill);

    border:
        1px solid
        var(--border-color-primary);

    box-shadow:
        0 4px 15px
        rgba(0,0,0,0.06);

    transition:
        transform 0.2s ease;
}

.kpi-card:hover {
    transform:
        translateY(-3px);
}

.kpi-icon {
    font-size: 22px;
}

.kpi-number {

    font-size: 29px;

    font-weight: 800;

    margin:
        4px 0;
}

.kpi-label {

    font-size: 12px;

    opacity: 0.70;

    font-weight: 600;
}


/* ==========================================================
   LIVE STATUS
   ========================================================== */

.status-card {

    padding:
        26px;

    border-radius:
        20px;

    margin-bottom:
        18px;

    text-align:
        center;

    box-shadow:
        0 8px 25px
        rgba(0,0,0,0.08);

    border:
        1px solid
        rgba(255,255,255,0.20);
}

.status-on {

    background:
        linear-gradient(
            135deg,
            rgba(16,185,129,.16),
            rgba(5,150,105,.05)
        );

    border:
        1px solid
        rgba(16,185,129,.30);
}

.status-off {

    background:
        linear-gradient(
            135deg,
            rgba(239,68,68,.13),
            rgba(220,38,38,.04)
        );

    border:
        1px solid
        rgba(239,68,68,.25);
}

.status-small {

    font-size:
        11px;

    letter-spacing:
        2px;

    font-weight:
        700;

    opacity:
        0.65;
}

.status-main {

    font-size:
        27px;

    font-weight:
        850;

    margin:
        8px 0;
}

.status-time {

    font-size:
        14px;

    opacity:
        0.70;
}

.shift-display {

    margin:
        13px auto 4px auto;

    font-size:
        23px;

    font-weight:
        800;
}

.status-extra {

    font-size:
        13px;

    opacity:
        0.70;

    margin-bottom:
        20px;
}


/* ==========================================================
   STATUS INFO
   ========================================================== */

.status-info-grid {

    display:
        grid;

    grid-template-columns:
        repeat(4, 1fr);

    gap:
        10px;
}

.status-info-box {

    background:
        rgba(
            255,
            255,
            255,
            0.07
        );

    border-radius:
        12px;

    padding:
        12px 7px;

    border:
        1px solid
        rgba(
            128,
            128,
            128,
            0.15
        );
}

.info-title {

    font-size:
        11px;

    opacity:
        0.65;

    margin-bottom:
        4px;
}

.info-value {

    font-size:
        14px;

    font-weight:
        700;
}


/* ==========================================================
   PANEL
   ========================================================== */

.section-heading {

    font-size:
        16px;

    font-weight:
        800;

    margin:
        12px 0 7px 0;
}


/* ==========================================================
   BUTTONS
   ========================================================== */

.primary-button {

    font-weight:
        700 !important;
}


/* ==========================================================
   ERROR
   ========================================================== */

.error-card {

    background:
        rgba(
            239,
            68,
            68,
            0.10
        );

    border:
        1px solid
        rgba(
            239,
            68,
            68,
            0.35
        );

    border-radius:
        15px;

    padding:
        20px;

    font-size:
        14px;
}


/* ==========================================================
   TABLE
   ========================================================== */

table {
    font-size:
        13px !important;
}


/* ==========================================================
   MOBILE
   ========================================================== */

@media (
    max-width: 1000px
) {

    .kpi-grid {
        grid-template-columns:
            repeat(2, 1fr);
    }

    .status-info-grid {
        grid-template-columns:
            repeat(2, 1fr);
    }

}


@media (
    max-width: 600px
) {

    .kpi-grid {
        grid-template-columns:
            1fr;
    }

    .status-info-grid {
        grid-template-columns:
            1fr;
    }

    .hero-title {
        font-size:
            23px;
    }

}

"""


# ============================================================
# DEFAULT VALUES
# ============================================================

current_now = datetime.now(APP_TIMEZONE)

today_string = current_now.strftime("%Y-%m-%d")
current_time_string = current_now.strftime("%H:%M")


# ============================================================
# GRADIO FRONTEND
# ============================================================

with gr.Blocks(
    css=css,
    theme=gr.themes.Soft(),
    title="Advanced Shift & Duty Roster",
) as demo:

    # --------------------------------------------------------
    # Header
    # --------------------------------------------------------

    gr.HTML(
        """
        <div class="hero">

            <div class="hero-title">
                🗓 Advanced Shift & Duty Roster
            </div>

            <div class="hero-subtitle">
                Rotational duty planning • Live shift status •
                Workload analysis • Weekend tracking
            </div>

        </div>
        """
    )

    # --------------------------------------------------------
    # KPI
    # --------------------------------------------------------

    kpi_output = gr.HTML()

    # --------------------------------------------------------
    # Main Layout
    # --------------------------------------------------------

    with gr.Row():

        # ====================================================
        # LEFT PANEL
        # ====================================================

        with gr.Column(
            scale=1,
            min_width=330
        ):

            gr.Markdown(
                "## ⚙️ Roster Configuration"
            )

            anchor = gr.Textbox(
                label="📌 First Duty Day",
                value="2026-09-09",
                placeholder="YYYY-MM-DD",
                info="First day of your ON-duty cycle",
            )

            with gr.Row():

                range_start = gr.Textbox(
                    label="📅 Roster From",
                    value="2026-09-09",
                    placeholder="YYYY-MM-DD",
                )

                range_end = gr.Textbox(
                    label="📅 Roster To",
                    value="2026-12-31",
                    placeholder="YYYY-MM-DD",
                )

            gr.Markdown(
                "### 🔄 Rotation"
            )

            with gr.Row():

                days_on = gr.Number(
                    label="Days ON",
                    value=4,
                    minimum=1,
                    maximum=30,
                    precision=0,
                )

                days_off = gr.Number(
                    label="Days OFF",
                    value=4,
                    minimum=1,
                    maximum=30,
                    precision=0,
                )

            gr.Markdown(
                "**Quick Presets**"
            )

            with gr.Row():

                preset44 = gr.Button(
                    "4 ON / 4 OFF",
                    size="sm",
                )

                preset52 = gr.Button(
                    "5 ON / 2 OFF",
                    size="sm",
                )

            with gr.Row():

                preset77 = gr.Button(
                    "7 ON / 7 OFF",
                    size="sm",
                )

                preset1414 = gr.Button(
                    "14 ON / 14 OFF",
                    size="sm",
                )

            gr.Markdown(
                "### ⏱ Shift Configuration"
            )

            with gr.Row():

                shift_start = gr.Textbox(
                    label="Shift Start",
                    value="08:00",
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
                choices=list(
                    WEEKDAY_MAP.keys()
                ),
                value=[
                    "Saturday",
                    "Sunday"
                ],
            )

            gr.Markdown(
                "## 🕒 Duty Status Check"
            )

            with gr.Row():

                check_date = gr.Textbox(
                    label="Check Date",
                    value=today_string,
                    placeholder="YYYY-MM-DD",
                )

                check_time = gr.Textbox(
                    label="Check Time",
                    value=current_time_string,
                    placeholder="HH:MM",
                )

            current_btn = gr.Button(
                "🕒 Use Current Pakistan Time"
            )

            generate_btn = gr.Button(
                "🚀 Generate & Analyze Roster",
                variant="primary",
                size="lg",
                elem_classes=[
                    "primary-button"
                ],
            )

            gr.Markdown(
                """
                ---
                **💡 Tip**

                `First Duty Day` should represent the
                first day of an ON-duty block.

                Example:

                **4 ON → 4 OFF → repeat**
                """
            )

        # ====================================================
        # RIGHT PANEL
        # ====================================================

        with gr.Column(
            scale=2,
            min_width=600
        ):

            gr.Markdown(
                "## 📍 Current / Selected Status"
            )

            status_output = gr.HTML()

            # ------------------------------------------------
            # Summary
            # ------------------------------------------------

            gr.Markdown(
                "## 📊 Roster Summary"
            )

            summary_output = gr.Dataframe(
                interactive=False,
                wrap=True,
            )

            # ------------------------------------------------
            # Monthly
            # ------------------------------------------------

            gr.Markdown(
                "## 📈 Monthly Workload"
            )

            monthly_output = gr.Dataframe(
                interactive=False,
                wrap=True,
            )

    # ========================================================
    # DAILY ROSTER
    # ========================================================

    gr.Markdown(
        "## 📅 Full Daily Roster"
    )

    roster_output = gr.Dataframe(
        interactive=False,
        wrap=True,
        max_height=500,
    )

    # ========================================================
    # DOWNLOAD
    # ========================================================

    with gr.Row():

        download_file = gr.File(
            label="📥 Download Complete Roster CSV"
        )


    # ========================================================
    # INPUT / OUTPUT ARRAYS
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
        summary_output,
        monthly_output,
        roster_output,
        download_file,
    ]


    # ========================================================
    # EVENTS
    # ========================================================

    generate_btn.click(
        fn=generate_roster,
        inputs=inputs,
        outputs=outputs,
    )


    # --------------------------------------------------------
    # CURRENT TIME
    # --------------------------------------------------------

    current_btn.click(
        fn=use_current_time,
        inputs=[],
        outputs=[
            check_date,
            check_time,
        ],
    ).then(
        fn=generate_roster,
        inputs=inputs,
        outputs=outputs,
    )


    # --------------------------------------------------------
    # PRESETS
    # --------------------------------------------------------

    preset44.click(
        fn=preset_4_4,
        inputs=[],
        outputs=[
            days_on,
            days_off
        ],
    )

    preset52.click(
        fn=preset_5_2,
        inputs=[],
        outputs=[
            days_on,
            days_off
        ],
    )

    preset77.click(
        fn=preset_7_7,
        inputs=[],
        outputs=[
            days_on,
            days_off
        ],
    )

    preset1414.click(
        fn=preset_14_14,
        inputs=[],
        outputs=[
            days_on,
            days_off
        ],
    )


    # --------------------------------------------------------
    # GENERATE AUTOMATICALLY ON LOAD
    # --------------------------------------------------------

    demo.load(
        fn=generate_roster,
        inputs=inputs,
        outputs=outputs,
    )


# ============================================================
# RUN APP
# ============================================================

if __name__ == "__main__":

    demo.launch()
