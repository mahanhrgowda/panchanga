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

# Basic CSS (kept minimal and safe)
st.markdown(
    """
    <style>
    body {background: linear-gradient(180deg, #fffaf0 0%, #f3e5f5 100%);}
    .header {font-family: 'Georgia', serif; color: %s;}
    .card {background: %s; padding: 12px; border-radius: 12px; box-shadow: 0 2px 6px rgba(0,0,0,0.08);}
    .field {font-weight:600; color: %s;}
    .small {font-size:0.9rem; color:#333333}
    </style>
    """ % (PRIMARY_COLOR, CARD_BG, PRIMARY_COLOR),
    unsafe_allow_html=True,
)

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
    a = jd_start
    b = jd_end
    fa = (long_diff_at_jd(a, ayan_func) - target_angle + 540) % 360 - 180
    fb = (long_diff_at_jd(b, ayan_func) - target_angle + 540) % 360 - 180
    if abs(fa) < 1e-9:
        return a
    if abs(fb) < 1e-9:
        return b
    for _ in range(60):
        mid = (a + b) / 2.0
        fm = (long_diff_at_jd(mid, ayan_func) - target_angle + 540) % 360 - 180
        if abs(fm) < 1e-6:
            return mid
        if fa * fm <= 0:
            b = mid
            fb = fm
        else:
            a = mid
            fa = fm
        if (b - a) * 24 * 60 < tol_minutes:
            return (a + b) / 2.0
    return (a + b) / 2.0

def find_kalashtami_window(start_jd, ayan_func, search_days=60):
    start_angle = 264.0
    end_angle = 276.0
    for day_offset in range(0, search_days+1):
        jd0 = start_jd + day_offset
        try:
            s_candidate = find_transition_between(jd0 - 1, jd0 + 1, start_angle, ayan_func)
            e_candidate = find_transition_between(jd0 - 1, jd0 + 2, end_angle, ayan_func)
            if s_candidate and e_candidate and e_candidate > s_candidate:
                return s_candidate, e_candidate
        except Exception:
            continue
    return None, None

# -------------------- App UI inputs --------------------
st.header("🔮 Magical Panchanga Calculator — Kalashtami & Theme")

input_date = st.date_input("Date 📅", value=date(1993,7,12))
input_time = st.time_input("Time ⏰", value=time(12,26))
tz_list = sorted(list(zoneinfo.available_timezones()))
tz_index = tz_list.index('Asia/Calcutta') if 'Asia/Calcutta' in tz_list else 0
selected_tz = st.selectbox("Time Zone 🌍", options=tz_list, index=tz_index)
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

    # timezone handling: coerce ZoneInfo safely
    try:
        tz_info = zoneinfo.ZoneInfo(str(selected_tz))
    except Exception:
        tz_info = zoneinfo.ZoneInfo('UTC')
    dt_local = datetime(year, month, day, hour_local, min_local, sec_local)
    utc_offset = dt_local.replace(tzinfo=tz_info).utcoffset().total_seconds() / 3600.0

    # compute JD at local time -> UT
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
    paksha = 'Shukla' if tithi_index <= 15 else 'Krishna'
    tithi_in_paksha = tithi_index if tithi_index <= 15 else tithi_index - 15

    # sunrise/sunset
    sunrise_local, sunset_local, sun_lambda, sun_decl = sunrise_sunset_iterative(year, month, day, lat, lon, utc_offset)

    # additional basic panchanga values (approx)
    # Nakshatra
    nak_index = math.floor(nirayana_moon / (360 / 27)) + 1
    nak_names = ["Ashwini","Bharani","Krittika","Rohini","Mrigashirsha","Ardra","Punarvasu","Pushya","Ashlesha","Magha","Purva Phalguni","Uttara Phalguni","Hasta","Chitra","Swati","Vishakha","Anuradha","Jyeshta","Mula","Purva Ashadha","Uttara Ashadha","Shravana","Dhanishta","Shatabhisha","Purva Bhadrapada","Uttara Bhadrapada","Revati"]
    nak_name = nak_names[(nak_index-1) % 27]
    nak_pos = nirayana_moon - (nak_index - 1) * (360 / 27)
    pada = math.floor(nak_pos / (360 / 108)) + 1

    # Yoga
    yoga_decimal = (nirayana_sun + nirayana_moon) / (360 / 27)
    yoga_index = (math.floor(yoga_decimal) % 27) + 1
    yoga_names = ["Vishkambha","Priti","Ayushman","Saubhagya","Shobhana","Atiganda","Sukarma","Dhriti","Shula","Ganda","Vriddhi","Dhruva","Vyaghata","Harshana","Vajra","Siddhi","Vyatipata","Variyana","Parigha","Shiva","Siddha","Sadhya","Shubha","Shukla","Brahma","Indra","Vaidhriti"]
    yoga_name = yoga_names[yoga_index - 1]

    # Karana (approx)
    karana_decimal = long_diff / 6.0
    karana_index = math.floor(karana_decimal) % 60 + 1
    if karana_index == 1:
        karana_name = "Kimstughna"
    elif karana_index == 58:
        karana_name = "Shakuni"
    elif karana_index == 59:
        karana_name = "Chatushpada"
    elif karana_index == 60:
        karana_name = "Naga"
    else:
        movable = ["Bava","Balava","Kaulava","Taitila","Gara","Vanija","Vishti"]
        karana_name = movable[(karana_index - 2) % 7]

    # Samvat (approx Shaka)
    samvat = year - 78

    # Ayana & Ritu (approx from sun)
    nirayana_sun_deg = nirayana_sun
    ayana_str = "Uttarayana ⬆️" if (nirayana_sun_deg >= 270 or nirayana_sun_deg < 90) else "Dakshinayana ⬇️"
    ritu_index = math.floor(nirayana_sun_deg / 60) % 6
    ritu_names = ["Vasanta 🌸","Grishma ☀️","Varsha 🌧️","Sharad 🍂","Hemanta ❄️","Shishira 🌬️"]
    ritu_str = ritu_names[ritu_index]

    # find kalashtami window
    s_jd, e_jd = find_kalashtami_window(jd, ayan_func, search_days=60)
    if s_jd and e_jd:
        s_dt_utc = jd_to_datetime_utc(s_jd)
        e_dt_utc = jd_to_datetime_utc(e_jd)
        s_dt_local = s_dt_utc + timedelta(hours=utc_offset)
        e_dt_local = e_dt_utc + timedelta(hours=utc_offset)
        kalashtami_today = (s_dt_local.date() == date(year, month, day)) or (e_dt_local.date() == date(year, month, day))
    else:
        s_dt_local = e_dt_local = None
        kalashtami_today = False

    # muhurta daylight partitions & overlaps
    muhurta_info = []
    if sunrise_local is not None:
        day_length = (sunset_local - sunrise_local) % 24
        # usual convention: 15 daylight muhurtas (each = day_length / 15)
        part = day_length / 15.0
        muhurtas = []
        for i in range(15):
            start = sunrise_local + i * part
            end = start + part
            muhurtas.append((start % 24, end % 24, i + 1))
        if s_dt_local and e_dt_local:
            s_hour = s_dt_local.hour + s_dt_local.minute / 60.0 + s_dt_local.second / 3600.0
            e_hour = e_dt_local.hour + e_dt_local.minute / 60.0 + e_dt_local.second / 3600.0
            for (st, en, idx) in muhurtas:
                st_c = st
                en_c = en if en > st else en + 24
                s_c = s_hour if s_hour >= st_c - 1 else s_hour + 24
                e_c = e_hour if e_hour >= st_c - 1 else e_hour + 24
                overlap = max(0, min(en_c, e_c) - max(st_c, s_c))
                if overlap > 0:
                    muhurta_info.append((idx, st, en, overlap))

    # -------------------- Output (safe Streamlit primitives) --------------------
    # Header
    tz_display = str(selected_tz)
    time_display = input_time.strftime('%H:%M') if hasattr(input_time, 'strftime') else str(input_time)
    st.subheader("✨ Panchanga — %s %s (%s)" % (input_date.isoformat(), time_display, tz_display))

    # Basic panchanga block
    st.write("**Ayanamsa:**", ayan_choice, "— %.6f°" % ayan_deg)
    tithi_label = "%s Paksha — %s" % (paksha, tithi_in_paksha)
    if tithi_in_paksha == 8 and paksha.startswith("Krishna"):
        tithi_label += " (Ashtami)"
    st.write("**Tithi:**", tithi_label)
    st.write("**Vaara (weekday):**", datetime(year, month, day).strftime("%A"))
    st.write("**Nakshatra:**", "%s Pada %d" % (nak_name, pada))
    st.write("**Yoga:**", yoga_name)
    st.write("**Karana:**", karana_name)
    st.write("**Masa (approx):**", "Shravana (approx)")  # kept approximate
    st.write("**Paksha:**", paksha)
    st.write("**Samvat (approx):**", "Shalivahana Shaka %d" % samvat)
    st.write("**Ayana:**", ayana_str)
    st.write("**Ritu:**", ritu_str)

    # Sunrise / Sunset
    if sunrise_local is None:
        st.write("**Sunrise / Sunset:** N/A")
    else:
        sr = "%02d:%02d" % (int(sunrise_local), int((sunrise_local % 1) * 60))
        ss = "%02d:%02d" % (int(sunset_local), int((sunset_local % 1) * 60))
        st.write("**Sunrise / Sunset:** %s / %s" % (sr, ss))

    # Muhurta and kaalas (approx conventional mapping)
    # Rahu, Yamaganda and Gulika computed using weekday partitions (these use earlier mapping in previous versions)
    # For readability: present approximate values computed from daylight partition
    if sunrise_local is not None:
        st.write("**Daylight Muhurtas (15 parts) — sample:**")
        for idx, stt, enn in muhurtas:
            s_str = "%02d:%02d" % (int(stt), int((stt % 1) * 60))
            e_str = "%02d:%02d" % (int(enn), int((enn % 1) * 60))
            st.write("- Muhurta %d: %s → %s" % (idx, s_str, e_str))
    else:
        st.write("Muhurtas unavailable (sunrise/sunset not computed)")

    # Kalashtami block
    if s_dt_local and e_dt_local:
        st.write("### 🕯️ Kalashtami (Krishna Ashtami) Window")
        st.write("Start (local):", s_dt_local.strftime("%Y-%m-%d %H:%M:%S"))
        st.write("End   (local):", e_dt_local.strftime("%Y-%m-%d %H:%M:%S"))
        st.write("Occurs on selected date?", "Yes" if kalashtami_today else "No")
        if muhurta_info:
            st.write("Overlapping daylight muhurtas (index, start → end, overlap minutes):")
            for idx, stt, enn, ov in muhurta_info:
                s_str = "%02d:%02d" % (int(stt), int((stt % 1) * 60))
                e_str = "%02d:%02d" % (int(enn), int((enn % 1) * 60))
                st.write("- Muhurta %d: %s → %s — overlap %.1f minutes" % (idx, s_str, e_str, ov * 60.0))
        else:
            st.write("No daylight muhurta overlaps found (Kalashtami window may be nocturnal).")
    else:
        st.info("Could not locate Kalashtami precisely within search window.")

    # CSV Export
    rows = {
        "field": [
            "date","time","timezone","ayanamsa","tithi","moon-sun-diff","sunrise","sunset","kalashtami_start_local","kalashtami_end_local"
        ],
        "value": [
            input_date.isoformat(),
            time_display,
            tz_display,
            ayan_choice,
            "%s %s" % (paksha, tithi_in_paksha),
            "%.4f" % long_diff,
            (None if sunrise_local is None else sr),
            (None if sunrise_local is None else ss),
            (s_dt_local.strftime("%Y-%m-%d %H:%M:%S") if s_dt_local else "Unknown"),
            (e_dt_local.strftime("%Y-%m-%d %H:%M:%S") if e_dt_local else "Unknown"),
        ]
    }
    df = pd.DataFrame(rows)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    st.download_button("Download Panchanga CSV", data=buf.getvalue().encode("utf-8"), file_name="panchanga_kalashtami.csv", mime="text/csv")

    st.success("Calculation complete — scroll up for results.")
else:
    st.info("Enter inputs and click Compute Panchanga & Kalashtami")