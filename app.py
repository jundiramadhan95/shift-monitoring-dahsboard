import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
import pytz
import requests

st.set_page_config(page_title="Shift Monitor", layout="wide")

# 🌏 Timezone Jakarta
tz = pytz.timezone("Asia/Jakarta")

# ⏱️ Refresh otomatis setiap 1 jam
REFRESH_INTERVAL = timedelta(hours=1)
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = datetime.now(tz)
if datetime.now(tz) - st.session_state.last_refresh > REFRESH_INTERVAL:
    st.session_state.last_refresh = datetime.now(tz)
    st.experimental_rerun()

# 🔐 Load credentials dari secrets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = st.secrets["GOOGLE_CREDENTIALS"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# 📄 Load sheet
sheet_id = "1-oRIDg05sPRTlRV6iBWk8OhS-9fcnOe8hDycjBhzdVI"
sheet = client.open_by_key(sheet_id).worksheet("New Shift 24/7 ")

# 📘 Load shift type mapping
df_shift = pd.read_csv("shift_type.csv")
shift_times = {
    row["shift_type"]: (row["begin"], row["end"])
    for _, row in df_shift.iterrows()
}

# 📅 Ambil data jadwal
def get_schedule_for_current_month(all_rows, shift_times):
    today = datetime.now(tz)
    current_month = today.month
    current_year = today.year

    all_data = []
    date_columns = []

    for i, row in enumerate(all_rows):
        for j, cell in enumerate(row):
            try:
                cell_date = datetime.strptime(cell.strip(), '%m/%d/%Y')
                if cell_date.month == current_month and cell_date.year == current_year:
                    date_columns.append((i, j, cell_date))
            except:
                continue
        if date_columns:
            break

    for date_row_index, target_col_index, target_date in date_columns:
        current_name = None
        for row in all_rows[date_row_index + 1:]:
            if len(row) <= target_col_index:
                continue

            name_cell = row[1].strip()
            shift = row[target_col_index].strip()

            if all(cell.strip() == "" for cell in row):
                break

            if name_cell:
                current_name = name_cell

            if current_name and shift:
                begin, end = shift_times.get(shift, ("-", "-"))
                all_data.append({
                    'date': target_date.strftime('%Y-%m-%d'),
                    'shift_date': target_date.strftime('%d-%m-%Y'),
                    'ops_name': current_name,
                    'shift': shift,
                    'start': begin,
                    'end': end
                })

    return pd.DataFrame(all_data)

# 🔄 Ambil data dari sheet
all_rows = sheet.get_all_values()
df_schedule = get_schedule_for_current_month(all_rows, shift_times)

# 🚫 Notifikasi jika data kosong
if df_schedule.empty:
    st.error("🚫 Tidak ada data shift untuk bulan ini.")
    st.stop()

# 🕒 Konversi jam
def parse_time(t):
    try:
        return datetime.strptime(t, "%I:%M %p").time()
    except:
        return None

df_schedule["start_time"] = df_schedule["start"].apply(parse_time)
df_schedule["end_time"] = df_schedule["end"].apply(parse_time)

# ⏱️ Hitung durasi kerja
def calc_duration(row):
    if row["start_time"] and row["end_time"]:
        start = datetime.combine(datetime.now(tz).date(), row["start_time"])
        end = datetime.combine(datetime.now(tz).date(), row["end_time"])
        if end < start:
            end += timedelta(days=1)
        return (end - start).total_seconds() / 3600
    return 0

df_schedule["duration_hours"] = df_schedule.apply(calc_duration, axis=1)

# 🔍 Cek siapa yang aktif sekarang
df_schedule["date"] = pd.to_datetime(df_schedule["date"]).dt.date

def is_active(row):
    now = datetime.now(tz)
    if pd.notnull(row["date"]) and pd.notnull(row["start_time"]) and pd.notnull(row["end_time"]):
        start_naive = datetime.combine(row["date"], row["start_time"])
        end_naive = datetime.combine(row["date"], row["end_time"])
        start = tz.localize(start_naive)
        end = tz.localize(end_naive)
        if end < start:
            end += timedelta(days=1)
        return start <= now <= end
    return False

df_schedule["active_now"] = df_schedule.apply(is_active, axis=1)

# 🧼 Format ulang
df_schedule["shift_date"] = pd.to_datetime(df_schedule["shift_date"], format="%d-%m-%Y")
df_schedule["start_time"] = pd.to_datetime(df_schedule["start_time"], format="%H:%M:%S", errors="coerce").dt.strftime("%H:%M:%S")
df_schedule["end_time"] = pd.to_datetime(df_schedule["end_time"], format="%H:%M:%S", errors="coerce").dt.strftime("%H:%M:%S")

df_dashboard = df_schedule[["shift_date", "ops_name", "shift", "start_time", "end_time", "active_now"]].rename(columns={
    "shift_date": "SHIFT_DATE",
    "ops_name": "USER_DESCRIPTION",
    "shift": "SHIFT",
    "start_time": "START_TIME",
    "end_time": "END_TIME",
    "active_now": "ACTIVE_NOW"
})

df_dashboard["SHIFT_DATE"] = pd.to_datetime(df_dashboard["SHIFT_DATE"], format="%d-%m-%Y").dt.strftime("%d-%m-%Y")
df_dashboard["START_TIME"] = df_dashboard["START_TIME"].apply(lambda x: "00:00:00" if pd.isna(x) else x)
df_dashboard["END_TIME"] = df_dashboard["END_TIME"].apply(lambda x: "00:00:00" if pd.isna(x) else x)

# 🚨 Deteksi perubahan (abaikan kolom ACTIVE_NOW)
df_snapshot = df_dashboard.drop(columns=["ACTIVE_NOW"])

def detect_changes(old_df, new_df):
    changes = []
    old_df = old_df.reset_index(drop=True)
    new_df = new_df.reset_index(drop=True)
    for i in range(min(len(old_df), len(new_df))):
        row_old = old_df.loc[i]
        row_new = new_df.loc[i]
        for col in old_df.columns:
            if row_old[col] != row_new[col]:
                changes.append({
                    "Row": i + 1,
                    "Column": col,
                    "From": row_old[col],
                    "To": row_new[col]
                })
    return pd.DataFrame(changes)

def send_telegram_message(message):
    token = st.secrets["TELEGRAM_TOKEN"]
    chat_id = st.secrets["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        st.error(f"Gagal kirim notifikasi Telegram: {e}")

if "prev_df" not in st.session_state:
    st.session_state.prev_df = df_snapshot.copy()

if not df_snapshot.equals(st.session_state.prev_df):
    st.warning("⚠️ Terjadi perubahan pada jadwal shift!")
    change_details = detect_changes(st.session_state.prev_df, df_snapshot)
    if not change_details.empty:
        with st.expander("📌 Detail Perubahan Data"):
            st.dataframe(change_details, width='stretch')

        # 🔔 Kirim notifikasi ke Telegram
        notif_lines = ["🚨 Perubahan Jadwal Terdeteksi:"]
        for _, row in change_details.iterrows():
            notif_lines.append(f"• Baris {row['Row']} kolom {row['Column']}: '{row['From']}' → '{row['To']}'")
        send_telegram_message("\n".join(notif_lines))

    st.session_state.prev_df = df_snapshot.copy()

# 📊 Tampilkan dashboard
st.title("📅 Shift Monitoring Dashboard Ops")

# 🔎 Filter hari ini
today_str = datetime.now(tz).strftime("%d-%m-%Y")
df_today = df_dashboard[df_dashboard["SHIFT_DATE"] == today_str]

st.subheader(f"👥 Jadwal Shift Hari Ini ({today_str})")
st.dataframe(df_today, width='stretch')

# 🔘 Toggle tombol untuk tampilkan/sembunyikan semua jadwal
if "show_all" not in st.session_state:
    st.session_state.show_all = False

if st.button("Tampilkan Semua Jadwal Bulan Ini" if not st.session_state.show_all else "Sembunyikan Semua Jadwal"):
    st.session_state