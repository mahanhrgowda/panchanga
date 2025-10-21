import streamlit as st
import math
from datetime import datetime, date, time, timedelta
import zoneinfo
import pandas as pd
import io

# Optional PDF generation; if fpdf is unavailable, PDF button will be disabled
try:
    from fpdf import FPDF
    PDF_AVAILABLE = True
except Exception:
    PDF_AVAILABLE = False

# -------------------- Styling / Theme --------------------
PRIMARY_COLOR = "#6A1B9A"  # deep violet
ACCENT_COLOR = "#FFB74D"   # warm saffron
CARD_BG = "#FFF8E1"

st.set_page_config(page_title="Magical Panchanga", layout='centered', page_icon='🔮')
st.markdown(f"""
<style>
body {{background: linear-gradient(180deg, #fffaf0 0%, #f3e5f5 100%);}}
.header {{font-family: 'Georgia', serif; color: {PRIMARY_COLOR};}}
.card {{background: {CARD_BG}; padding: 12px; border-radius: 12px; box-shadow: 0 2px 6px rgba(0,0,0,0.08);}}
.field {{font-weight:600; color: {PRIMARY_COLOR};}}
.small {{font-size:0.9rem; color:#333333}}
</style>
""", unsafe_allow_html=True)

# -------------------- Utilities --------------------
def mod360(x):
    return (x % 360 + 360) % 360

def sin_d(x):
    return math.sin(math.radians(x))

def cos_d(x):
    return math.cos(math.radians(x))

# -------------------- Julian Day helpers --------------------
def greg_to_jd(year, month, day, ut_hour, ut_min, ut_sec):
    if month <= 2:
        year -= 1
        month += 12
    a = math.floor(year / 100)
    b = 2 - a + math.floor(a / 4)
    e = math.floor(365.25 * (year + 4716))
    f = math.floor(30.6001 * (month + 1))
    jd = b + day + e + f - 1524.5 + (ut_hour + ut_min / 60.0 + ut_sec / 3600.0) / 24.0
    return jd

def jd_to_datetime_utc(jd):
    # Convert Julian Day to UTC datetime (Meeus algorithm)
    jd += 0.5
    Z = int(jd)
    F = jd - Z
    if Z < 2299161:
        A = Z
    else:
        alpha = int((Z - 1867216.25) / 36524.25)
        A = Z + 1 + alpha - int(alpha / 4)
    B = A + 1524
    C = int((B - 122.1) / 365.25)
    D = int(365.25 * C)
    E = int((B - D) / 30.6001)
    day = B - D - int(30.6001 * E) + F
    if E < 14:
        month = E - 1
    else:
        month = E - 13
    if month > 2:
        year = C - 4716
    else:
        year = C - 4715
    day_floor = int(day)
    day_frac = day - day_floor
    hour = int(day_frac * 24)
    minute = int((day_frac * 24 - hour) * 60)
    second = int((((day_frac * 24 - hour) * 60) - minute) * 60)
    return datetime(year, month, day_floor, hour, minute, second)

# -------------------- Sun & Moon models --------------------
def sun_coords(d):
    T = d / 36525.0
    L0 = mod360(280.46646 + 36000.76983 * T + 0.0003032 * T * T)
    M = mod360(357.52911 + 35999.05029 * T - 0.0001537 * T * T)
    C = (1.914602 - 0.004817 * T - 0.000014 * T * T) * sin_d(M) + \
        (0.019993 - 0.000101 * T) * sin_d(2 * M) + 0.000289 * sin_d(3 * M)
    true_long = L0 + C
    omega = mod360(125.04 - 1934.136 * T)
    lam = true_long - 0.00569 - 0.00478 * sin_d(omega)
    eps0 = 23.43929111 - 0.013004167 * T - 1.6666667e-7 * T * T + 5.02777778e-7 * T * T * T
    eps = eps0 + 0.00256 * cos_d(omega)
    decl = math.degrees(math.asin(math.sin(math.radians(eps)) * math.sin(math.radians(lam))))
    return mod360(lam), decl

def moon_longitude_high(d):
    T = d / 36525.0
    L0 = mod360(218.3164477 + 481267.88123421 * T - 0.0015786 * T * T + T**3 / 538841.0 - T**4 / 65194000.0)
    D = mod360(297.8501921 + 445267.1114034 * T - 0.0018819 * T * T + T**3 / 545868.0 - T**4 / 113065000.0)
    M = mod360(357.5291092 + 35999.0502909 * T - 0.0001536 * T * T)
    M_moon = mod360(134.9633964 + 477198.8675055 * T + 0.0087414 * T * T + T**3 / 69699.0 - T**4 / 14712000.0)
    F = mod360(93.2720950 + 483202.0175233 * T - 0.0036539 * T * T - T**3 / 3526000.0 + T**4 / 863310000.0)
    lon = L0
    terms = [
        (6288774, M_moon), (1274027, 2*D - M_moon), (658314, 2*D), (213618, 2*M_moon),
        (-185116, M), (-114332, 2*F), (58793, 2*D - 2*M_moon), (57066, 2*D - M - M_moon),
        (53322, 2*D + M_moon), (45758, 2*D - M), (-40923, M - M_moon), (-34720, D),
        (-30383, M + M_moon), (15327, 2*D - 2*F), (-12528, M_moon + M), (10980, M_moon - M)
    ]
    for coeff, arg in terms:
        lon += (coeff / 1000000.0) * math.sin(math.radians(arg)) * 360.0
    return mod360(lon)

# -------------------- Ayanamsa choices (precise fits) --------------------
def ayanamsa_lahiri_precise(jd):
    T = (jd - 2451545.0) / 36525.0
    a0 = 23.8534315
    a1 = 0.0130000
    a2 = -0.0000007
    return a0 + a1 * T + a2 * T * T

def ayanamsa_fagan_precise(jd):
    T = (jd - 2451545.0) / 36525.0
    return 22.460148 + 0.0140 * T

def ayanamsa_raman_precise(jd):
    T = (jd - 2451545.0) / 36525.0
    return 22.460 - 0.00001 * T

AYANAMSAS = {
    'Lahiri (precise)': ayanamsa_lahiri_precise,
    'Fagan/Bradley (precise)': ayanamsa_fagan_precise,
    'Raman (precise)': ayanamsa_raman_precise
}

# -------------------- Sunrise/Sunset iterative --------------------
def sunrise_sunset_iterative(year, month, day, lat, lon, tz_offset_hours):
    approx_noon_utc = 12 - lon / 15.0
    jd_noon = greg_to_jd(year, month, day, approx_noon_utc, 0, 0)
    d_noon = jd_noon - 2451545.0
    lam, decl = sun_coords(d_noon)
    zenith = 90.833
    try:
        ha = math.degrees(math.acos((math.cos(math.radians(zenith)) - math.sin(math.radians(lat)) * math.sin(math.radians(decl))) / (math.cos(math.radians(lat)) * math.cos(math.radians(decl)))))
    except ValueError:
        return None, None, None, decl
    sunrise_utc = approx_noon_utc - ha / 15.0
    sunset_utc = approx_noon_utc + ha / 15.0
    sunrise_local = (sunrise_utc + tz_offset_hours) % 24
    sunset_local = (sunset_utc + tz_offset_hours) % 24
    return sunrise_local, sunset_local, lam, decl

# -------------------- Tithi utilities: find exact transition via bisection --------------------
def long_diff_at_jd(jd, ayan_func):
    d = jd - 2451545.0
    sun_l, _ = sun_coords(d)
    moon_l = moon_longitude_high(d)
    ay = ayan_func(jd)
    n_sun = mod360(sun_l - ay)
    n_moon = mod360(moon_l - ay)
    ld = mod360(n_moon - n_sun)
    return ld

def find_transition_between(jd_start, jd_end, target_angle, ayan_func, tol_minutes=0.5):
    # Find time when long_diff crosses target_angle (in degrees) between jd_start and jd_end
    a = jd_start
    b = jd_end
    fa = (long_diff_at_jd(a, ayan_func) - target_angle + 540) % 360 - 180
    fb = (long_diff_at_jd(b, ayan_func) - target_angle + 540) % 360 - 180
    # if signs equal, we may need to adjust by adding multiples of 360; try to find crossing
    if abs(fa) < 1e-9:
        return a
    if abs(fb) < 1e-9:
        return b
    # Normalize so root exists
    for _ in range(60):
        mid = (a + b) / 2.0
        fm = (long_diff_at_jd(mid, ayan_func) - target_angle + 540) % 360 - 180
        # converge
        if abs(fm) < 1e-6:
            return mid
        # determine which side to keep by comparing sign of fm and fa
        if fa * fm <= 0:
            b = mid
            fb = fm
        else:
            a = mid
            fa = fm
        # stop if interval small
        if (b - a) * 24 * 60 < tol_minutes:
            return (a + b) / 2.0
    return (a + b) / 2.0

# -------------------- Find Kalashtami (exact tithi window) --------------------
def find_kalashtami_window(start_jd, ayan_func, search_days=60):
    # Kalashtami = Krishna Ashtami = tithi number 23 (1..30). So target range: [264°, 276°)
    start_angle = 264.0
    end_angle = 276.0
    for day_offset in range(0, search_days+1):
        jd0 = start_jd + day_offset
        # check if tithi 23 occurs on this day by sampling
        ld_mid = long_diff_at_jd(jd0 + 0.5, ayan_func)
        # if within some margin, attempt to find transitions within +/-1 day
        # find crossing into start_angle between jd0-1 and jd0+1
        try:
            # find start (entering Ashtami)
            s_candidate = find_transition_between(jd0 - 1, jd0 + 1, start_angle, ayan_func)
            e_candidate = find_transition_between(jd0 - 1, jd0 + 2, end_angle, ayan_func)
            # verify order
            if s_candidate and e_candidate and e_candidate > s_candidate:
                return s_candidate, e_candidate
        except Exception:
            continue
    return None, None

# -------------------- App UI inputs --------------------
st.header("🔮 Magical Panchanga Calculator — Kalashtami & Theme")
input_date = st.date_input("Date 📅", value=date(1993,7,12))
input_time = st.time_input("Time ⏰", value=time(12,26))
selected_tz = st.selectbox("Time Zone 🌍", options=sorted(list(zoneinfo.available_timezones())), index=sorted(list(zoneinfo.available_timezones())).index('Asia/Calcutta') if 'Asia/Calcutta' in zoneinfo.available_timezones() else 0)
lat = st.number_input("Latitude ° North 📍", value=13.32, format="%.6f")
lon = st.number_input("Longitude ° East 📍", value=75.77, format="%.6f")
ayan_choice = st.selectbox("Ayanamsa choice", list(AYANAMSAS.keys()), index=0)

if st.button('Compute Panchanga & Kalashtami'):
    # prepare
    year = input_date.year
    month = input_date.month
    day = input_date.day
    hour_local = input_time.hour
    min_local = input_time.minute
    sec_local = 0
    tz_info = zoneinfo.ZoneInfo(selected_tz)
    dt_local = datetime(year, month, day, hour_local, min_local, sec_local)
    utc_offset = dt_local.replace(tzinfo=tz_info).utcoffset().total_seconds() / 3600.0
    # compute JD at local time
    ut_hour = hour_local - utc_offset
    y, m, d = year, month, day
    if ut_hour < 0:
        ut_hour += 24
        prev = datetime(year, month, day) - timedelta(days=1)
        y, m, d = prev.year, prev.month, prev.day
    elif ut_hour >= 24:
        ut_hour -= 24
        nxt = datetime(year, month, day) + timedelta(days=1)
        y, m, d = nxt.year, nxt.month, nxt.day
    jd = greg_to_jd(y, m, d, ut_hour, min_local, sec_local)
    d_j = jd - 2451545.0

    ayan_func = AYANAMSAS.get(ayan_choice, ayanamsa_lahiri_precise)
    ayan_deg = ayan_func(jd)

    sun_lon_app, sun_decl = sun_coords(d_j)
    moon_lon = moon_longitude_high(d_j)
    nirayana_sun = mod360(sun_lon_app - ayan_deg)
    nirayana_moon = mod360(moon_lon - ayan_deg)
    long_diff = mod360(nirayana_moon - nirayana_sun)
    tithi_decimal = long_diff / 12.0
    tithi_index = math.floor(tithi_decimal) + 1
    paksha = 'Shukla' if tithi_index <=15 else 'Krishna'
    tithi_in_paksha = tithi_index if tithi_index<=15 else tithi_index-15

    # sunrise/sunset
    sunrise_local, sunset_local, _, _ = sunrise_sunset_iterative(year, month, day, lat, lon, utc_offset)

    # find kalashtami window
    s_jd, e_jd = find_kalashtami_window(jd, ayan_func, search_days=60)
    if s_jd and e_jd:
        s_dt_utc = jd_to_datetime_utc(s_jd)
        e_dt_utc = jd_to_datetime_utc(e_jd)
        s_dt_local = (s_dt_utc + timedelta(hours=utc_offset))
        e_dt_local = (e_dt_utc + timedelta(hours=utc_offset))
        kalashtami_today = (s_dt_local.date() == date(year, month, day)) or (e_dt_local.date() == date(year, month, day))
    else:
        s_dt_local = e_dt_local = None
        kalashtami_today = False

    # compute muhurta windows for the local day and check overlaps with Kalashtami tithi window
    muhurta_info = []
    if sunrise_local is not None:
        day_length = (sunset_local - sunrise_local) % 24
        part = day_length / 15.0  # muhurta = 1/30 day? Traditional muhurta is 48 minutes -> day has 15 muhurtas
        # But many muhurta calculators use 30 muhurtas in 24 hours (48 min each) -> day has 15 daylight muhurtas
        # We'll compute common muhurta labels (1..15) for the day and check overlap
        muhurtas = []
        for i in range(15):
            start = sunrise_local + i * part
            end = start + part
            muhurtas.append((start % 24, end % 24, i+1))
        # check overlap
        if s_dt_local and e_dt_local:
            s_hour = s_dt_local.hour + s_dt_local.minute/60 + s_dt_local.second/3600
            e_hour = e_dt_local.hour + e_dt_local.minute/60 + e_dt_local.second/3600
            for (st, en, idx) in muhurtas:
                # handle wrap-around by mapping to continuous hours using same day anchor
                st_c = st
                en_c = en if en>st else en+24
                # normalize s/e into same scale
                s_c = s_hour if s_hour>=st_c-1 else s_hour+24
                e_c = e_hour if e_hour>=st_c-1 else e_hour+24
                overlap = max(0, min(en_c, e_c) - max(st_c, s_c))
                if overlap > 0:
                    muhurta_info.append((idx, st, en, overlap))

    # -------------------- Output (styled cards) --------------------
    st.markdown(f"<div class='card'><h2 class='header'>✨ Panchanga — {input_date.isoformat()} {input_time.strftime('%H:%M')} ({selected_tz})</h2>", unsafe_allow_html=True)
    st.markdown(f"<p class='small'><span class='field'>Ayanamsa:</span> {ayan_choice} — {ayan_deg:.6f}°</p>", unsafe_allow_html=True)
    st.markdown(f"<p class='small'><span class='field'>Tithi:</span> {paksha} Paksha — {tithi_in_paksha} ({'Ashtami' if tithi_in_paksha==8 else ''})</p>", unsafe_allow_html=True)
    st.markdown(f"<p class='small'><span class='field'>Moon–Sun diff:</span> {long_diff:.4f}°</p>", unsafe_allow_html=True)
    st.markdown(f"<p class='small'><span class='field'>Sunrise / Sunset:</span> {('N/A' if sunrise_local is None else f'{int(sunrise_local):02d}:{int((sunrise_local%1)*60):02d} / {int(sunset_local):02d}:{int((sunset_local%1)*60):02d}')}</p>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # Kalashtami block
    if s_dt_local and e_dt_local:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown(f"<h3 style='color:{PRIMARY_COLOR}'>🕯️ Kalashtami (Krishna Ashtami) Window</h3>", unsafe_allow_html=True)
        st.write(f"Start (local): {s_dt_local.strftime('%Y-%m-%d %H:%M:%S')}")
        st.write(f"End   (local): {e_dt_local.strftime('%Y-%m-%d %H:%M:%S')}")
        st.write(f"Occurs on selected date? {'Yes' if kalashtami_today else 'No'}")
        # show overlapping muhurtas
        if muhurta_info:
            st.write("Overlapping local muhurtas (index, start, end, overlap_hours):")
            for idx, stt, enn, ov in muhurta_info:
                st.write(f"• Muhurta {idx}: {int(stt):02d}:{int((stt%1)*60):02d} to {int(enn):02d}:{int((enn%1)*60):02d} — overlap {ov*60:.1f} minutes")
        else:
            st.write("No daylight muhurta overlaps found (Kalashtami window may be nocturnal).")
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info('Could not locate Kalashtami precisely within search window.')

    # Export CSV quick
    rows = {
        'field': ['date','time','timezone','ayanamsa','tithi','moon-sun-diff','sunrise','sunset','kalashtami_start_local','kalashtami_end_local'],
        'value': [input_date.isoformat(), input_time.strftime('%H:%M'), selected_tz, ayan_choice, f"{paksha} {tithi_in_paksha}", f"{long_diff:.4f}", (None if sunrise_local is None else f"{int(sunrise_local):02d}:{int((sunrise_local%1)*60):02d}"), (None if sunrise_local is None else f"{int(sunset_local):02d}:{int((sunset_local%1)*60):02d}"), (s_dt_local.strftime('%Y-%m-%d %H:%M:%S') if s_dt_local else 'Unknown'), (e_dt_local.strftime('%Y-%m-%d %H:%M:%S') if e_dt_local else 'Unknown')]
    }
    df = pd.DataFrame(rows)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    st.download_button('Download Panchanga CSV', data=buf.getvalue().encode('utf-8'), file_name='panchanga_kalashtami.csv', mime='text/csv')

    st.write('\n')
    st.success('Calculation complete — scroll up for results.')

else:
    st.info('Enter inputs and click Compute Panchanga & Kalashtami')
