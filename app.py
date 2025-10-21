import streamlit as st
import math
from datetime import datetime, date, time, timedelta, timezone
import zoneinfo
import pandas as pd
import io

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

def get_sun_long(d):
    T = d / 36525.0
    M = mod360(357.52910 + 35999.05030 * T - 0.0001559 * T**2 - 0.00000048 * T**3)
    L0 = mod360(280.46645 + 36000.76983 * T + 0.0003032 * T**2)
    DL = (1.914600 - 0.004817 * T - 0.000014 * T**2) * sin_d(M) + \
         (0.019993 - 0.000101 * T) * sin_d(2 * M) + \
         0.000290 * sin_d(3 * M)
    return mod360(L0 + DL)

def get_moon_long(d):
    T = d / 36525.0
    L0 = mod360(218.31617 + 481267.88088 * T)
    M = mod360(134.96292 + 477198.86753 * T)
    Msun = mod360(357.52543 + 35999.04944 * T)
    F = mod360(93.27283 + 483202.01873 * T)
    D = mod360(297.85027 + 445267.11135 * T)
    pert = 0.0
    pert += 22640 * sin_d(M)
    pert += 769 * sin_d(2 * M)
    pert += -4586 * sin_d(M - 2 * D)
    pert += 2370 * sin_d(2 * D)
    pert += -668 * sin_d(Msun)
    pert += -412 * sin_d(2 * F)
    pert += -125 * sin_d(D)
    pert += -212 * sin_d(2 * M - 2 * D)
    pert += -206 * sin_d(M + Msun - 2 * D)
    pert += 192 * sin_d(M + 2 * D)
    pert += -165 * sin_d(Msun - 2 * D)
    pert += 148 * sin_d(L0 - Msun)
    pert += -110 * sin_d(M + Msun)
    pert += -55 * sin_d(2 * F - 2 * D)
    return mod360(L0 + pert / 3600.0)

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

def long_diff_at_jd(jd):
    d = jd - 2451545.0
    sun_l = get_sun_long(d)
    moon_l = get_moon_long(d)
    ay = get_ayanamsa(d)
    n_sun = mod360(sun_l - ay)
    n_moon = mod360(moon_l - ay)
    ld = mod360(n_moon - n_sun)
    return ld

def find_transition_between(jd_start, jd_end, target_angle, tol_minutes=0.5):
    a = jd_start
    b = jd_end
    fa = (long_diff_at_jd(a) - target_angle + 540) % 360 - 180
    fb = (long_diff_at_jd(b) - target_angle + 540) % 360 - 180
    if abs(fa) < 1e-9:
        return a
    if abs(fb) < 1e-9:
        return b
    for _ in range(60):
        mid = (a + b) / 2.0
        fm = (long_diff_at_jd(mid) - target_angle + 540) % 360 - 180
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

def find_kalashtami_window(start_jd, search_days=60):
    start_angle = 264.0
    end_angle = 276.0
    for day_offset in range(0, search_days+1):
        jd0 = start_jd + day_offset
        try:
            s_candidate = find_transition_between(jd0 - 1, jd0 + 1, start_angle)
            e_candidate = find_transition_between(jd0 - 1, jd0 + 2, end_angle)
            if s_candidate and e_candidate and e_candidate > s_candidate:
                return s_candidate, e_candidate
        except Exception:
            continue
    return None, None

# Streamlit App
st.title("🌟 Magical Panchanga Calculator App! 🔮")

st.write("Enter the details to discover the cosmic blueprint with fun emojis! ✨")

# Default values
default_date = date(1993, 7, 12)
default_time = time(12, 26)
default_tz = 'Asia/Kolkata'
default_lat = 13.32
default_lon = 75.77

input_date = st.date_input("Date 📅", min_value=date(1900, 1, 1), max_value=date(2100, 12, 31), value=default_date)
input_time = st.time_input("Time ⏰", value=default_time, step=timedelta(minutes=1))
tz_list = sorted(list(zoneinfo.available_timezones()))
tz_index = tz_list.index(default_tz)
selected_tz = st.selectbox("Time Zone 🌍", options=tz_list, index=tz_index)
lat = st.number_input("Latitude ° North 📍", value=default_lat, step=0.01)
long = st.number_input("Longitude ° East 📍", value=default_lon, step=0.01)

if st.button("Compute Panchanga"):
    if not all([input_date, input_time, selected_tz, lat is not None, long is not None]):
        st.warning("Please fill all fields.")
    else:
        year = input_date.year
        month = input_date.month
        day = input_date.day
        hour_local = input_time.hour
        min_local = input_time.minute
        sec_local = 0
        dt_local = datetime(year, month, day, hour_local, min_local, sec_local)
        tz_info = zoneinfo.ZoneInfo(selected_tz)
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
        nak_pos = nirayana_moon - (nak_index - 1) * (360 / 27)
        pada = math.floor(nak_pos / (360 / 108)) + 1
        nak_str = nak_names[nak_index - 1] + f" Pada {pada}" + " ⭐"

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
        nirayana_moon_purn = mod360(moon_long_purn - get_ayanamsa(d_purn))
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

        # Kalashtami
        s_jd, e_jd = find_kalashtami_window(jd, search_days=60)
        kalashtami_str = ""
        if s_jd and e_jd:
            s_dt_utc_naive = jd_to_datetime_utc(s_jd)
            e_dt_utc_naive = jd_to_datetime_utc(e_jd)
            s_dt_utc_aware = s_dt_utc_naive.replace(tzinfo=timezone.utc)
            e_dt_utc_aware = e_dt_utc_naive.replace(tzinfo=timezone.utc)
            s_dt_local = s_dt_utc_aware.astimezone(tz_info)
            e_dt_local = e_dt_utc_aware.astimezone(tz_info)
            kalashtami_today = (s_dt_local.date() == input_date) or (e_dt_local.date() == input_date)
            kalashtami_str = f"Kalashtami Window: {s_dt_local.strftime('%H:%M:%S')} to {e_dt_local.strftime('%H:%M:%S')} (Today: {'Yes' if kalashtami_today else 'No'}) 🕯️"
        else:
            kalashtami_str = "Kalashtami not found within 60 days 🔍"

        # Display
        st.header("Cosmic Panchanga Details! 🌌")
        st.write(f"**Tithi**: {tithi_str}")
        st.write("🌙🕰️ Tithi is the lunar day, dividing the month into 30 parts! Each lasts about 23 hours 36 minutes, based on the Moon-Sun angle 📐. It can vary from 21 to 26 hours due to elliptical orbits ⬭. Starts every 12 degrees of separation! Timing isn't fixed to solar days, so festivals align with these phases 🌕🌑.")
        st.write(f"**Vaara**: {vaara_str}")
        st.write("📅☀️ Vaara is the weekday, like Monday or Tuesday, but starts at sunrise 🌅 instead of midnight 🕛. It's a solar day in the Hindu calendar, lasting ~24 hours, guiding daily routines and auspicious times! 🗓️🌟")
        st.write(f"**Nakshatra**: {nak_str}")
        st.write("⭐🌌 Nakshatra is the lunar mansion, one of 27 sky regions the Moon passes through! Each represents a slice of the zodiac, influencing personality and events. Pada divides it into 4 quarters for precision! 🔭✨")
        st.write(f"**Yoga**: {yoga_str}")
        st.write("🧘‍♂️📐 Yoga is a special period defined by Sun-Moon positions, one of 27 types! It signifies energy for activities—some auspicious, others not. Perfect for planning events with cosmic harmony! 🌞🌙")
        st.write(f"**Karana**: {karana_str}")
        st.write("⚙️🌗 Karana is half a Tithi, dividing the lunar day into smaller segments! There are 11 types, each with unique vibes for tasks. Helps fine-tune timings for success! 🕒🔄")
        st.write(f"**Masa**: {masa_str}")
        st.write("📆🌕 Masa is the lunar month, ~29.53 days from new moon to new moon! Divided into Shukla (waxing) and Krishna (waning) halves. Aligns with seasons and festivals! 🍁❄️")
        st.write(f"**Paksha**: {paksha}")
        st.write("🌔🌖 Paksha is the fortnight—Shukla for waxing Moon (brightening vibes!) or Krishna for waning (introspective energy!). Each ~15 days, guiding rituals and moods! 🔄✨")
        st.write(f"**Samvat**: {samvat_str}")
        st.write("📜🗓️ Samvat denotes the solar year in Hindu eras like Shalivahana Shaka! It's about 1 year long, starting around March/April. Tracks historical and astrological timelines! ⏳🌟")
        st.write(f"**Ayana**: {ayana_str}")
        st.write("⬆️⬇️ Ayana is the solstice half-year—Uttarayana (Sun's northern path, auspicious!) or Dakshinayana (southern). Each ~6 months, influencing seasons and festivals! ☀️❄️")
        st.write(f"**Ritu**: {ritu_str}")
        st.write("🌸☀️ Ritu signifies the season, one of 6 like Vasanta (spring) or Grishma (summer)! Each spans 2 lunar months, tied to nature's cycles for agriculture and celebrations! 🌧️🍂❄️🌬️")
        st.write(f"**Sunrise**: {sunrise_str}")
        st.write("🌅🕰️ Sunrise marks the start of the Vaara in Hindu time! Calculated for your location, it's when the Sun appears on the horizon. Sets the tone for the day's energy! ☀️✨")
        st.write(f"**Sunset**: {sunset_str}")
        st.write("🌇🕰️ Sunset ends the solar day, transitioning to night vibes! Location-specific, it influences evening rituals and Muhurta calculations. Beautiful closure to daily cycles! 🌙💫")
        st.write(f"**Kalashtami**: {kalashtami_str}")
        st.write("🕯️🌙 Kalashtami is the auspicious 8th day of Krishna Paksha, dedicated to Lord Shiva! A time for fasting, worship, and midnight rituals for protection and blessings. Window shows the specific timing! 🙏✨")
        st.header("Muhurta Timings ⏳")
        st.write(rahu_str)
        st.write("😈🕒 Rahu Kaala is an inauspicious 1.5-hour slot daily, ruled by mythical Rahu! Avoid new ventures to dodge destructive influences. Varies by weekday and location! ⚠️🌑")
        st.write(yama_str)
        st.write("⚠️🕒 Yamaganda Kaala, linked to Yama (god of death), is unfavorable for starts! Lasts ~1.5 hours; activities may face obstacles. Plan around it for smooth sailing! 🚧💀")
        st.write(gulika_str)
        st.write("🕳️🕒 Gulika Kaala, tied to Saturn's destructive side, brings challenges if ignored! ~1.5 hours; skip important tasks to avoid negative outcomes. Cosmic caution zone! 🪐🚫")
        st.write(abhijith_str)
        st.write("🌞🕒 Abhijith Muhurta is super auspicious, ~48 minutes around midday! Sun's peak position brings success for ventures and ceremonies. Grab this golden window! 🏆✨")
        st.header("Choghadiya 🕒")
        st.write(chogh_str)
        st.write("🕰️🚀 Choghadiya divides day/night into 8 parts (~1.5 hours each), ruled by planets! Good ones (Shubh, Labh) for auspicious acts; bad (Rog, Udveg) for specific or avoidance. Overlaps with Rahu etc. matter—choose wisely for fruitful results! 🌟😟💰🥛")

        # CSV Export
        rows = {
            "field": ["date", "time", "timezone", "tithi", "vaara", "nakshatra", "yoga", "karana", "masa", "paksha", "samvat", "ayana", "ritu", "sunrise", "sunset", "kalashtami", "rahu_kaala", "yamaganda_kaala", "gulika_kaala", "abhijith_muhurta", "choghadiya"],
            "value": [
                input_date.isoformat(),
                input_time.strftime('%H:%M'),
                selected_tz,
                tithi_str,
                vaara_str,
                nak_str,
                yoga_str,
                karana_str,
                masa_str,
                paksha,
                samvat_str,
                ayana_str,
                ritu_str,
                sunrise_str,
                sunset_str,
                kalashtami_str,
                rahu_str,
                yama_str,
                gulika_str,
                abhijith_str,
                chogh_str
            ]
        }
        df = pd.DataFrame(rows)
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        st.download_button("Download Panchanga CSV", data=buf.getvalue().encode("utf-8"), file_name="panchanga.csv", mime="text/csv")

        st.write("May the stars align in your favor! ⭐✨")
else:
    st.info("Click the button to compute after filling details.")
