# Shift Monitor Dashboard

Dashboard Streamlit untuk memantau jadwal shift bulanan dari Google Sheets.

## Fitur
- Tampilkan jadwal hari ini
- Toggle semua jadwal
- Deteksi perubahan data
- Notifikasi Telegram
- Auto-refresh setiap 1 jam

## Setup
1. Buat bot Telegram via @BotFather
2. Tambahkan token dan chat_id ke Streamlit Secrets
3. Upload file `shift_type.csv` ke repo
4. Deploy via Streamlit Cloud

## Secrets (contoh)
Tambahkan ini ke Streamlit Cloud → Settings → Secrets:

```toml
GOOGLE_CREDENTIALS = """{ ... isi file JSON ... }"""
TELEGRAM_TOKEN = "123456789:ABCdefGhIjKlmNoPQRstuVwXyZ"
TELEGRAM_CHAT_ID = "123456789"