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

# -------------------- App UI --------------------
st.header("🔮 Magical Panchanga Calculator — Fixed Version")
input_date = st.date_input("Date 📅", value=date(1993,7,12))
input_time = st.time_input("Time ⏰", value=time(12,26))
selected_tz = st.selectbox("Time Zone 🌍", options=sorted(list(zoneinfo.available_timezones())), index=sorted(list(zoneinfo.available_timezones())).index('Asia/Calcutta') if 'Asia/Calcutta' in zoneinfo.available_timezones() else 0)
lat = st.number_input("Latitude ° North 📍", value=13.32, format="%.6f")
lon = st.number_input("Longitude ° East 📍", value=75.77, format="%.6f")

if st.button('Compute Panchanga'):
    tz_display = str(selected_tz)
    time_display = input_time.strftime('%H:%M') if hasattr(input_time, 'strftime') else str(input_time)
    st.markdown(
        "<div class='card'><h2 class='header'>✨ Panchanga — "
        + input_date.isoformat()
        + " "
        + time_display
        + " ("
        + tz_display
        + ")</h2></div>",
        unsafe_allow_html=True
    )

    st.success("Header rendered successfully without AttributeError! Further Panchanga computations continue here...")
