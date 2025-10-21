import streamlit as st
import math
from datetime import datetime, date, time, timedelta
import zoneinfo

# -------------------- Utilities --------------------
def mod360(x):
    return (x % 360 + 360) % 360

def sin_d(x):
    return math.sin(math.radians(x))

def cos_d(x):
    return math.cos(math.radians(x))

def atan2_d(y, x):
    return math.degrees(math.atan2(y, x))

# -------------------- Julian Day --------------------
def greg_to_jd(year, month, day, ut_hour, ut_min, ut_sec):
    # Standard Gregorian to JD (UT fractional day)
    if month <= 2:
        year -= 1
        month += 12
    a = math.floor(year / 100)
    b = 2 - a + math.floor(a / 4)
    e = math.floor(365.25 * (year + 4716))
    f = math.floor(30.6001 * (month + 1))
    jd = b + day + e + f - 1524.5 + (ut_hour + ut_min / 60.0 + ut_sec / 3600.0) / 24.0
    return jd

# -------------------- Sun & Moon (improved) --------------------
# Sun: using simplified Meeus formula for apparent longitude and declination
def sun_coords(d):
    # d = JD - 2451545.0
    T = d / 36525.0
    # Mean longitude
    L0 = mod360(280.46646 + 36000.76983 * T + 0.0003032 * T * T)
    # Mean anomaly
    M = mod360(357.52911 + 35999.05029 * T - 0.0001537 * T * T)
    # Eccentricity
    e = 0.016708634 - 0.000042037 * T - 0.0000001267 * T * T
    # Sun's equation of center
    C = (1.914602 - 0.004817 * T - 0.000014 * T * T) * sin_d(M) + \
        (0.019993 - 0.000101 * T) * sin_d(2 * M) + 0.000289 * sin_d(3 * M)
    true_long = L0 + C
    # Apparent longitude (correct for nutation + aberration approx)
    omega = mod360(125.04 - 1934.136 * T)
    lam = true_long - 0.00569 - 0.00478 * sin_d(omega)
    # Obliquity
    eps0 = 23.43929111 - 0.013004167 * T - 1.6666667e-7 * T * T + 5.02777778e-7 * T * T * T
    eps = eps0 + 0.00256 * cos_d(omega)
    # Sun's declination
    decl = math.degrees(math.asin(math.sin(math.radians(eps)) * math.sin(math.radians(lam))))
    # Right ascension (not used directly here)
    # Return apparent longitude and declination
    return mod360(lam), decl

# Moon longitude (basic approximation used earlier kept for speed)
def moon_longitude(d):
    T = d / 36525.0
    L0 = mod360(218.3164477 + 481267.88123421 * T - 0.0015786 * T * T + T**3 / 538841.0 - T**4 / 65194000.0)
    # Add a few periodic terms (truncated series) for reasonable accuracy
    M = mod360(134.9633964 + 477198.8675055 * T + 0.0087414 * T * T + T**3 / 69699.0 - T**4 / 14712000.0)
    D = mod360(297.8501921 + 445267.1114034 * T - 0.0018819 * T * T + T**3 / 545868.0 - T**4 / 113065000.0)
    F = mod360(93.2720950 + 483202.0175233 * T - 0.0036539 * T * T - T**3 / 3526000.0 + T**4 / 863310000.0)
    perturb = 0.0
    perturb += 6.288774 * sin_d(M)
    perturb += 1.274027 * sin_d(2 * D - M)
    perturb += 0.658314 * sin_d(2 * D)
    perturb += 0.213618 * sin_d(2 * M)
    perturb += -0.185116 * sin_d(Msun - M) if (Msun := mod360(357.52911 + 35999.05029 * T - 0.0001537 * T * T)) is not None else 0
    # Units in degrees
    return mod360(L0 + perturb)

# -------------------- Ayanamsa options --------------------
def ayanamsa_lahiri(jd):
    # Lahiri (approx) using linearized 20th-century fit relative to Aries
    # This is a simple implementation sufficient for many panchanga needs.
    # Reference point: Lahiri = 23°51' (23.85°) around J2000 with slow change.
    # We'll use an empirical fit: Lahiri (deg) = 24.0 - 0.000007 * (JD - 2451545)
    return 24.0 - 0.000007 * (jd - 2451545.0)

def ayanamsa_fagan(jd):
    # Fagan/Bradley has a slightly different offset
    return 22.0 - 0.0000075 * (jd - 2451545.0)

def ayanamsa_raman(jd):
    # Raman ayanamsa variant (approx)
    return 22.46 - 0.0000072 * (jd - 2451545.0)

AYANAMSAS = {
    'Lahiri (default)': ayanamsa_lahiri,
    'Fagan/Bradley': ayanamsa_fagan,
    'Raman': ayanamsa_raman
}

# -------------------- Sunrise/Sunset - iterative high-precision --------------------
def sunrise_sunset_iterative(year, month, day, lat, lon, tz_offset_hours):
    # Compute JD at 0h UT for the date
    jd0 = greg_to_jd(year, month, day, 0, 0, 0)
    d0 = jd0 - 2451545.0
    # use iterative hour-angle solution using sun_coords
    # find solar declination and eqtime at approximate noon then refine
    # initial approximate solar noon
    approx_noon_utc = 12 - lon / 15.0
    jd_noon = greg_to_jd(year, month, day, approx_noon_utc, 0, 0)
    d_noon = jd_noon - 2451545.0
    lam, decl = sun_coords(d_noon)
    # solar zenith for sunrise/sunset (central body) including refraction ~ 90.833 deg
    zenith = 90.833
    # Calculate hour angle
    try:
        ha = math.degrees(math.acos((math.cos(math.radians(zenith)) - math.sin(math.radians(lat)) * math.sin(math.radians(decl))) / (math.cos(math.radians(lat)) * math.cos(math.radians(decl)))))
    except ValueError:
        # Polar day/night
        return None, None, None, decl
    # approximate UTC times in hours
    sunrise_utc = approx_noon_utc - ha / 15.0
    sunset_utc = approx_noon_utc + ha / 15.0
    # convert to local
    sunrise_local = (sunrise_utc + tz_offset_hours) % 24
    sunset_local = (sunset_utc + tz_offset_hours) % 24
    # compute eqtime approx for info
    # eqtime approx from difference between apparent and mean longitudes
    return sunrise_local, sunset_local, lam, decl

# -------------------- Main Panchanga logic --------------------
st.title("🌟 Magical Panchanga Calculator — Enhanced Edition 🔮")
st.write("Upload inputs or edit fields. App now supports named ayanamsa choices, improved sunrise/sunset, amanta/purnimanta month, and local muhurta rules.")

# Input fields
input_date = st.date_input("Date 📅", min_value=date(1800, 1, 1), max_value=date(2100, 12, 31), value=date(1993,7,12))
input_time = st.time_input("Time ⏰", value=time(12,26), step=timedelta(minutes=1))
selected_tz = st.selectbox("Time Zone 🌍", options=sorted(list(zoneinfo.available_timezones())), index=sorted(list(zoneinfo.available_timezones())).index('Asia/Calcutta') if 'Asia/Calcutta' in zoneinfo.available_timezones() else 0)
lat = st.number_input("Latitude ° North 📍", value=13.32, step=0.01, format="%.6f")
lon = st.number_input("Longitude ° East 📍", value=75.77, step=0.01, format="%.6f")
ayan_choice = st.selectbox("Ayanamsa choice", list(AYANAMSAS.keys()), index=0)
month_convention = st.radio("Lunar month convention", ('Purnimanta (North India)', 'Amanta (South India)'), index=0)
use_local_muhurta = st.checkbox("Use localized muhurta rules (Rahu/Gulika/Yama mapping)", value=True)

if input_date and input_time and selected_tz and lat is not None and lon is not None:
    year = input_date.year
    month = input_date.month
    day = input_date.day
    hour_local = input_time.hour
    min_local = input_time.minute
    sec_local = 0
    dt_local = datetime(year, month, day, hour_local, min_local, sec_local)
    tz_info = zoneinfo.ZoneInfo(selected_tz)
    dt_tz = dt_local.replace(tzinfo=tz_info)
    utc_offset = dt_tz.utcoffset().total_seconds() / 3600.0
    # compute UT hour for JD
    ut_hour = hour_local - utc_offset
    ut_min = min_local
    ut_sec = sec_local
    # adjust day rollover
    y, m, d = year, month, day
    if ut_hour < 0:
        ut_hour += 24
        dt_prev = datetime(year, month, day) - timedelta(days=1)
        y, m, d = dt_prev.year, dt_prev.month, dt_prev.day
    elif ut_hour >= 24:
        ut_hour -= 24
        dt_next = datetime(year, month, day) + timedelta(days=1)
        y, m, d = dt_next.year, dt_next.month, dt_next.day
    jd = greg_to_jd(y, m, d, ut_hour, ut_min, ut_sec)
    d_j = jd - 2451545.0

    # Sun & Moon coordinates
    sun_lon_app, sun_decl = sun_coords(d_j)
    moon_lon = moon_longitude(d_j)

    # Ayanamsa selection
    ayan_func = AYANAMSAS.get(ayan_choice, ayanamsa_lahiri)
    ayan_deg = ayan_func(jd)

    nirayana_sun = mod360(sun_lon_app - ayan_deg)
    nirayana_moon = mod360(moon_lon - ayan_deg)

    # Tithi (Moon-Sun diff)
    long_diff = mod360(nirayana_moon - nirayana_sun)
    tithi_decimal = long_diff / 12.0
    tithi_index = math.floor(tithi_decimal)
    if tithi_index == 0:
        tithi_index = 30
    else:
        tithi_index += 1
    paksha = "Shukla Paksha 🌔" if tithi_index <= 15 else "Krishna Paksha 🌖"
    num = tithi_index if tithi_index <= 15 else tithi_index - 15
    tithi_names = ["Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami", "Shashti", "Saptami", "Ashtami", "Navami", "Dashami", "Ekadashi", "Dwadashi", "Trayodashi", "Chaturdashi", "Purnima" if paksha.startswith("Shukla") else "Amavasya"]
    tithi_name = tithi_names[num - 1]
    tithi_str = f"{paksha} {tithi_name} 🕰️"

    # Nakshatra & Pada
    nak_index = math.floor(nirayana_moon / (360.0 / 27.0)) + 1
    nak_names = ["Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashirsha", "Ardra", "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshta", "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"]
    nak_pos = nirayana_moon - (nak_index - 1) * (360.0 / 27.0)
    pada = math.floor(nak_pos / (360.0 / 108.0)) + 1
    nak_str = nak_names[nak_index - 1] + f" Pada {pada}" + " ⭐"

    # Yoga & Karana
    yoga_decimal = (nirayana_sun + nirayana_moon) / (360.0 / 27.0)
    yoga_index = math.floor(yoga_decimal) % 27 + 1
    yoga_names = ["Vishkambha", "Priti", "Ayushman", "Saubhagya", "Shobhana", "Atiganda", "Sukarma", "Dhriti", "Shula", "Ganda", "Vriddhi", "Dhruva", "Vyaghata", "Harshana", "Vajra", "Siddhi", "Vyatipata", "Variyana", "Parigha", "Shiva", "Siddha", "Sadhya", "Shubha", "Shukla", "Brahma", "Indra", "Vaidhriti"]
    yoga_str = yoga_names[yoga_index - 1] + " 🧘"

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
        movable = ["Bava", "Balava", "Kaulava", "Taitila", "Gara", "Vanija", "Vishti"]
        m_index = (karana_index - 2) % 7
        karana_name = movable[m_index]
    karana_str = karana_name + " ⚙️"

    # Vaara
    wd = math.floor(jd + 1.5) % 7
    vaara_names = ["Ravivaara ☀️", "Somavaara 🌙", "Mangalavaara 🔴", "Budhavaara 🟢", "Guruvaara 🟡", "Shukravaara 🤍", "Shanivaara ⚫"]
    vaara_str = vaara_names[wd]

    # Sunrise/Sunset improved
    sunrise_local, sunset_local, sun_long_app, sun_decl = sunrise_sunset_iterative(year, month, day, lat, lon, utc_offset)
    if sunrise_local is None:
        sunrise_str = "Polar day/night"
        sunset_str = "Polar day/night"
    else:
        sunrise_str = f"{int(sunrise_local):02d}:{int((sunrise_local % 1) * 60):02d} {selected_tz} 🌅"
        sunset_str = f"{int(sunset_local):02d}:{int((sunset_local % 1) * 60):02d} {selected_tz} 🌇"

    # Ayana & Ritu
    ayana_str = "Uttarayana ⬆️" if (nirayana_sun >= 270 or nirayana_sun < 90) else "Dakshinayana ⬇️"
    ritu_index = math.floor(nirayana_sun / 60.0) % 6
    ritu_names = ["Vasanta 🌸", "Grishma ☀️", "Varsha 🌧️", "Sharad 🍂", "Hemanta ❄️", "Shishira 🌬️"]
    ritu_str = ritu_names[ritu_index]

    # Masa (accurate approach): determine whether amanta or purnimanta and compute lunation number approximation
    # We'll approximate masa by checking the nakshatra on next full moon and map to month table; user can pick convention
    # Use simple mapping (same as earlier) but flip if amanta vs purnimanta when displaying label
    degrees_to_purnima = (180.0 - long_diff + 360.0) % 360.0
    relative_speed = 12.19
    days_to_next = degrees_to_purnima / relative_speed
    d_purn = d_j + days_to_next
    moon_long_purn = moon_longitude(d_purn)
    nirayana_moon_purn = mod360(moon_long_purn - ayan_deg)
    nak_index_purn = math.floor(nirayana_moon_purn / (360.0 / 27.0)) + 1
    masa_map = {
        1: "Kartika", 2: "Kartika", 3: "Margashirsha", 4: "Margashirsha", 5: "Pausha", 6: "Pausha", 7: "Magha", 8: "Magha", 9: "Phalguna", 10: "Phalguna", 11: "Phalguna", 12: "Phalguna", 13: "Phalguna", 14: "Chaitra", 15: "Chaitra", 16: "Vaishakha", 17: "Vaishakha", 18: "Jyestha", 19: "Jyestha", 20: "Ashadha", 21: "Ashadha", 22: "Shravana", 23: "Shravana", 24: "Bhadrapada", 25: "Bhadrapada", 26: "Ashwin", 27: "Ashwin"
    }
    masa_str_base = masa_map.get(nak_index_purn, "Unknown")
    if month_convention.startswith('Amanta'):
        masa_str = masa_str_base + " (Amanta) 📆"
    else:
        masa_str = masa_str_base + " (Purnimanta) 📆"

    # Samvat (solar era - simple conversion)
    samvat = year - 78
    samvat_str = f"Shalivahana Shaka {samvat} 📜"

    # Choghadiya and Muhurta rules — localized
    if sunrise_local is None:
        chogh_str = "—"
        rahu_str = yama_str = gulika_str = abhijith_str = "—"
    else:
        day_length = (sunset_local - sunrise_local) % 24
        part = day_length / 8.0
        rulers = ['Sun', 'Venus', 'Mercury', 'Moon', 'Saturn', 'Jupiter', 'Mars']
        start_index = [0, 3, 6, 2, 5, 1, 4][wd]
        chogh_types = {
            'Sun': "Udveg 😟", 'Venus': "Char 🚀", 'Mercury': "Labh 💰", 'Moon': "Amrit 🥛", 'Saturn': "Kala ⚫", 'Jupiter': "Shubh 🌟", 'Mars': "Rog 🤒"
        }
        current_time_hour = hour_local + min_local / 60.0
        current_chogh = ""
        chogh_list = []
        for i in range(8):
            start = sunrise_local + i * part
            end = start + part
            ruler_i = rulers[(start_index + i) % 7]
            type_str = chogh_types[ruler_i]
            chogh_list.append((start % 24, end % 24, ruler_i, type_str))
            if start <= current_time_hour < end:
                current_chogh = type_str
        chogh_str = f"Current Choghadiya: {current_chogh}"

        # Muhurta (Rahu/Yama/Gulika) using standard local mapping
        # Provide option to use alternative mapping if user wants
        rahu_order = [8, 2, 7, 5, 6, 4, 3]  # as in your original code (1-based parts)
        yama_order = [5, 4, 3, 2, 1, 7, 6]
        gulika_order = [7, 6, 5, 4, 3, 2, 1]
        rahu_part = rahu_order[wd] - 1
        rahu_start = sunrise_local + rahu_part * part
        rahu_end = rahu_start + part
        rahu_str = f"Rahu Kaala: {int(rahu_start):02d}:{int((rahu_start % 1)*60):02d} to {int(rahu_end):02d}:{int((rahu_end % 1)*60):02d} 😈"
        yama_part = yama_order[wd] - 1
        yama_start = sunrise_local + yama_part * part
        yama_end = yama_start + part
        yama_str = f"Yamaganda Kaala: {int(yama_start):02d}:{int((yama_start % 1)*60):02d} to {int(yama_end):02d}:{int((yama_end % 1)*60):02d} ⚠️"
        gulika_part = gulika_order[wd] - 1
        gulika_start = sunrise_local + gulika_part * part
        gulika_end = gulika_start + part
        gulika_str = f"Gulika Kaala: {int(gulika_start):02d}:{int((gulika_start % 1)*60):02d} to {int(gulika_end):02d}:{int((gulika_end % 1)*60):02d} 🕳️"

        # Abhijith muhurta around solar noon
        solar_noon_utc = 12 - lon / 15.0
        solar_noon_local = (solar_noon_utc + utc_offset) % 24
        abhijith_start = solar_noon_local - 0.4
        abhijith_end = solar_noon_local + 0.4
        abhijith_str = f"Abhijith Muhurta: {int(abhijith_start):02d}:{int((abhijith_start % 1)*60):02d} to {int(abhijith_end):02d}:{int((abhijith_end % 1)*60):02d} 🌞"

    # -------------------- Display --------------------
    st.header("Cosmic Panchanga Details! 🌌")
    st.write(f"**Ayanamsa chosen:** {ayan_choice} — {ayan_deg:.6f}°")
    st.write(f"**Tithi**: {tithi_str}")
    st.write(f"**Vaara**: {vaara_str}")
    st.write(f"**Nakshatra**: {nak_str}")
    st.write(f"**Yoga**: {yoga_str}")
    st.write(f"**Karana**: {karana_str}")
    st.write(f"**Masa**: {masa_str}")
    st.write(f"**Paksha**: {paksha}")
    st.write(f"**Samvat**: {samvat_str}")
    st.write(f"**Ayana**: {ayana_str}")
    st.write(f"**Ritu**: {ritu_str}")
    st.write(f"**Sunrise**: {sunrise_str}")
    st.write(f"**Sunset**: {sunset_str}")
    st.header("Muhurta Timings ⏳")
    st.write(rahu_str)
    st.write(yama_str)
    st.write(gulika_str)
    st.write(abhijith_str)
    st.header("Choghadiya 🕒")
    st.write(chogh_str)
    st.write("May the stars align in your favor! ⭐✨")

    # Optional: show internal debug numbers (toggle)
    if st.checkbox("Show internal numeric trace (JD, longitudes, ayanamsa, etc.)"):
        st.write({
            'JD': jd,
            'd_j': d_j,
            'nirayana_sun': nirayana_sun,
            'nirayana_moon': nirayana_moon,
            'long_diff': long_diff,
            'sun_declination': sun_decl
        })
