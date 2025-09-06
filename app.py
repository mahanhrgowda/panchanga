import streamlit as st
import math
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo

# Helper functions
def mod360(x):
    return (x % 360 + 360) % 360

def sin_d(x):
    return math.sin(x * math.pi / 180)

def cos_d(x):
    return math.cos(x * math.pi / 180)

def atan2_d(y, x):
    return math.atan2(y, x) * 180 / math.pi

def greg_to_jd(year, month, day, ut_hour, ut_min, ut_sec):
    if month <= 2:
        year -= 1
        month += 12
    a = math.floor(year / 100)
    b = math.floor(a / 4)
    c = 2 - a + b
    e = math.floor(365.25 * (year + 4716))
    f = math.floor(30.6001 * (month + 1))
    jd = c + day + e + f - 1524.5 + (ut_hour + ut_min / 60 + ut_sec / 3600) / 24
    return jd

def get_sun_long(d):
    w = 282.9404 + 4.70935e-5 * d
    e = 0.016709 - 1.151e-9 * d
    M = mod360(356.0470 + 0.9856002585 * d)
    E = M + (180 / math.pi) * e * sin_d(M) * (1 + e * cos_d(M))
    xv = cos_d(E) - e
    yv = sin_d(E) * math.sqrt(1 - e * e)
    v = atan2_d(yv, xv)
    lonsun = mod360(v + w)
    return lonsun

def get_moon_long(d):
    N = mod360(125.1228 - 0.0529538083 * d)
    i = 5.1454
    w = mod360(318.0634 + 0.1643573223 * d)
    a = 60.2666
    e = 0.054900
    M = mod360(115.3654 + 13.0649929509 * d)
    E = M + (180 / math.pi) * e * sin_d(M) * (1 + e * cos_d(M))
    for _ in range(5):
        E = E - (E - (180 / math.pi) * e * sin_d(E) - M) / (1 - e * cos_d(E))
    xv = a * (cos_d(E) - e)
    yv = a * math.sqrt(1 - e * e) * sin_d(E)
    v = atan2_d(yv, xv)
    r = math.sqrt(xv**2 + yv**2)
    l = mod360(v + w)
    xh = r * (cos_d(N) * cos_d(l) - sin_d(N) * sin_d(l) * cos_d(i))
    yh = r * (sin_d(N) * cos_d(l) + cos_d(N) * sin_d(l) * cos_d(i))
    zh = r * sin_d(l) * sin_d(i)
    lonecl = atan2_d(yh, xh)
    # Perturbations for better accuracy
    sun_long = get_sun_long(d)
    Ls = mod360(sun_long)
    Lm = mod360(N + w + M)
    D = mod360(Lm - Ls)
    F = mod360(Lm - N)
    long_pert = -1.274 * sin_d(M - 2 * D) + 0.658 * sin_d(2 * D) - 0.186 * sin_d(M) - 0.059 * sin_d(2 * M - 2 * D) - 0.057 * sin_d(M - 2 * D + M) + 0.053 * sin_d(M + 2 * D) + 0.046 * sin_d(2 * D - M) + 0.041 * sin_d(M - M) - 0.035 * sin_d(D) - 0.031 * sin_d(M + M) - 0.015 * sin_d(2 * F - 2 * D) + 0.011 * sin_d(M - 4 * D)
    moon_long = mod360(Lm + long_pert)
    return moon_long

def get_ayanamsa(d):
    return 23.853 + (d / 365.25) * (50.2388 / 3600)

def is_leap_year(year):
    if year % 4 != 0:
        return False
    if year % 100 != 0:
        return True
    return year % 400 == 0

def day_of_year(year, month, day):
    days = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    dy = sum(days[1:month]) + day
    if month > 2 and is_leap_year(year):
        dy += 1
    return dy

def get_sunrise_sunset(year, month, day, lat, long, timezone):
    dy = day_of_year(year, month, day)
    days_in_year = 366 if is_leap_year(year) else 365
    gamma = 2 * math.pi / days_in_year * (dy - 1 + (12 - 12) / 24)  # Noon for approx
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma) - 0.014615 * math.cos(2 * gamma) - 0.040849 * math.sin(2 * gamma))
    decl = 0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma) - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma) - 0.002697 * math.cos(3 * gamma) + 0.00148 * math.sin(3 * gamma)
    decl_deg = decl * 180 / math.pi
    cos_zen = math.cos(90.833 * math.pi / 180)
    ha = math.acos(cos_zen / (cos_d(lat) * cos_d(decl_deg)) - math.tan(lat * math.pi / 180) * math.tan(decl_deg * math.pi / 180))
    ha = ha * 180 / math.pi
    sunrise_utc_min = 720 - 4 * (long + ha) - eqtime
    sunset_utc_min = 720 - 4 * (long - ha) - eqtime
    sunrise_local = (sunrise_utc_min / 60 + timezone) % 24
    sunset_local = (sunset_utc_min / 60 + timezone) % 24
    return sunrise_local, sunset_local, eqtime, decl_deg

# Streamlit App
st.title("🌟 Magical Panchanga Calculator App! 🔮")

st.write("Enter the details to discover the cosmic blueprint with fun emojis! ✨")

input_date = st.date_input("Date 📅", min_value=date(1900, 1, 1), max_value=date(2100, 12, 31), value=None)
input_time = st.time_input("Time ⏰", value=None, step=timedelta(minutes=1))
selected_tz = st.selectbox("Time Zone 🌍", options=sorted(list(zoneinfo.available_timezones())), index=None)
lat = st.number_input("Latitude ° North 📍", value=None, step=0.01)
long = st.number_input("Longitude ° East 📍", value=None, step=0.01)

if input_date and input_time and selected_tz and lat is not None and long is not None:
    year = input_date.year
    month = input_date.month
    day = input_date.day
    hour_local = input_time.hour
    min_local = input_time.minute
    sec_local = 0
    dt_local = datetime(year, month, day, hour_local, min_local, sec_local)
    tz_info = ZoneInfo(selected_tz)
    dt_tz = dt_local.replace(tzinfo=tz_info)
    utc_offset = dt_tz.utcoffset().total_seconds() / 3600
    ut_hour = hour_local - utc_offset
    ut_min = min_local
    ut_sec = sec_local
    # Adjust for day rollover
    if ut_hour < 0:
        ut_hour += 24
        # Subtract a day from date
        temp_dt = datetime(year, month, day) - timedelta(days=1)
        year = temp_dt.year
        month = temp_dt.month
        day = temp_dt.day
    elif ut_hour >= 24:
        ut_hour -= 24
        # Add a day
        temp_dt = datetime(year, month, day) + timedelta(days=1)
        year = temp_dt.year
        month = temp_dt.month
        day = temp_dt.day
    jd = greg_to_jd(year, month, day, ut_hour, ut_min, ut_sec)
    d = jd - 2451545.0
    sun_long = get_sun_long(d)
    moon_long = get_moon_long(d)
    ayanamsa = get_ayanamsa(d)
    nirayana_sun = mod360(sun_long - ayanamsa)
    nirayana_moon = mod360(moon_long - ayanamsa)
    long_diff = mod360(nirayana_moon - nirayana_sun)
    tithi_decimal = long_diff / 12
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

    nak_index = math.floor(nirayana_moon / (360 / 27)) + 1
    nak_names = ["Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashirsha", "Ardra", "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshta", "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"]
    nak_str = nak_names[nak_index - 1] + " ⭐"

    yoga_decimal = (nirayana_sun + nirayana_moon) / (360 / 27)
    yoga_index = math.floor(yoga_decimal) % 27 + 1
    yoga_names = ["Vishkambha", "Priti", "Ayushman", "Saubhagya", "Shobhana", "Atiganda", "Sukarma", "Dhriti", "Shula", "Ganda", "Vriddhi", "Dhruva", "Vyaghata", "Harshana", "Vajra", "Siddhi", "Vyatipata", "Variyana", "Parigha", "Shiva", "Siddha", "Sadhya", "Shubha", "Shukla", "Brahma", "Indra", "Vaidhriti"]
    yoga_str = yoga_names[yoga_index - 1] + " 🧘"

    karana_decimal = long_diff / 6
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

    wd = math.floor(jd + 1.5) % 7
    vaara_names = ["Ravivaara ☀️", "Somavaara 🌙", "Mangalavaara 🔴", "Budhavaara 🟢", "Guruvaara 🟡", "Shukravaara 🤍", "Shanivaara ⚫"]
    vaara_str = vaara_names[wd]

    # Sunrise, Sunset
    sunrise, sunset, eqtime, decl_deg = get_sunrise_sunset(year, month, day, lat, long, utc_offset)
    sunrise_str = f"{int(sunrise):02d}:{int((sunrise % 1)*60):02d} {selected_tz} 🌅"
    sunset_str = f"{int(sunset):02d}:{int((sunset % 1)*60):02d} {selected_tz} 🌇"

    # Ayana
    ayana_str = "Uttarayana ⬆️" if (nirayana_sun >= 270 or nirayana_sun < 90) else "Dakshinayana ⬇️"

    # Ritu
    ritu_index = math.floor(nirayana_sun / 60) % 6
    ritu_names = ["Vasanta 🌸", "Grishma ☀️", "Varsha 🌧️", "Sharad 🍂", "Hemanta ❄️", "Shishira 🌬️"]
    ritu_str = ritu_names[ritu_index]

    # Approximate Masa using Purnima Nakshatra
    degrees_to_purnima = (180 - long_diff + 360) % 360
    relative_speed = 12.19
    days_to_next = degrees_to_purnima / relative_speed
    d_purn = d + days_to_next
    moon_long_purn = get_moon_long(d_purn)
    nirayana_moon_purn = mod360(moon_long_purn - ayanamsa)
    nak_index_purn = math.floor(nirayana_moon_purn / (360 / 27)) + 1
    masa_map = {
        1: "Kartika", 2: "Kartika", 3: "Margashirsha", 4: "Margashirsha", 5: "Pausha", 6: "Pausha", 7: "Magha", 8: "Magha", 9: "Phalguna", 10: "Phalguna", 11: "Phalguna", 12: "Phalguna", 13: "Phalguna", 14: "Chaitra", 15: "Chaitra", 16: "Vaishakha", 17: "Vaishakha", 18: "Jyestha", 19: "Jyestha", 20: "Ashadha", 21: "Ashadha", 22: "Shravana", 23: "Shravana", 24: "Bhadrapada", 25: "Bhadrapada", 26: "Ashwin", 27: "Ashwin"
    }
    masa_str = masa_map.get(nak_index_purn, "Unknown") + " 📆"

    # Samvat
    samvat = year - 78
    samvat_str = f"Shalivahana Shaka {samvat} 📜"

    # Choghadiya
    day_length = (sunset - sunrise) % 24
    part = day_length / 8
    rulers = ['Sun', 'Venus', 'Mercury', 'Moon', 'Saturn', 'Jupiter', 'Mars']
    start_index = [0, 3, 6, 2, 5, 1, 4][wd]
    chogh_types = {
        'Sun': "Udveg 😟", 'Venus': "Char 🚀", 'Mercury': "Labh 💰", 'Moon': "Amrit 🥛", 'Saturn': "Kala ⚫", 'Jupiter': "Shubh 🌟", 'Mars': "Rog 🤒"
    }
    current_time_hour = hour_local + min_local / 60
    current_chogh = ""
    for i in range(8):
        start = sunrise + i * part
        end = start + part
        ruler_i = rulers[(start_index + i) % 7]
        type_str = chogh_types[ruler_i]
        if start <= current_time_hour < end:
            current_chogh = type_str
    chogh_str = f"Current Choghadiya: {current_chogh}"

    # Muhurta
    rahu_part = [8, 2, 7, 5, 6, 4, 3][wd] - 1
    rahu_start = sunrise + rahu_part * part
    rahu_end = rahu_start + part
    rahu_str = f"Rahu Kaala: {int(rahu_start):02d}:{int((rahu_start % 1)*60):02d} to {int(rahu_end):02d}:{int((rahu_end % 1)*60):02d} 😈"

    yama_part = [5, 4, 3, 2, 1, 7, 6][wd] - 1
    yama_start = sunrise + yama_part * part
    yama_end = yama_start + part
    yama_str = f"Yamaganda Kaala: {int(yama_start):02d}:{int((yama_start % 1)*60):02d} to {int(yama_end):02d}:{int((yama_end % 1)*60):02d} ⚠️"

    gulika_part = [7, 6, 5, 4, 3, 2, 1][wd] - 1
    gulika_start = sunrise + gulika_part * part
    gulika_end = gulika_start + part
    gulika_str = f"Gulika Kaala: {int(gulika_start):02d}:{int((gulika_start % 1)*60):02d} to {int(gulika_end):02d}:{int((gulika_end % 1)*60):02d} 🕳️"

    solar_noon_utc_min = 720 - 4 * long - eqtime
    solar_noon_local = (solar_noon_utc_min / 60 + utc_offset) % 24
    abhijith_start = solar_noon_local - 0.4
    abhijith_end = solar_noon_local + 0.4
    abhijith_str = f"Abhijith Muhurta: {int(abhijith_start):02d}:{int((abhijith_start % 1)*60):02d} to {int(abhijith_end):02d}:{int((abhijith_end % 1)*60):02d} 🌞"

    # Display
    st.header("Cosmic Panchanga Details! 🌌")
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
