#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TikTok Dashboard — Apple Pro ✦ (v25.0 - Instant Boot Edition)
- Mở App cực nhanh (0.1s): Khởi động tức thì với dữ liệu Cache, Check Key chạy ẩn nền (Background Auth).
- Auto Log-out ngầm nếu phát hiện API báo khóa hoặc hết hạn.
- Đưa thanh hiển thị Bản Quyền (License) xuống Footer dưới cùng.
- Không tàn ảnh (Ghosting).
- API Quản lý đa thiết bị (Max Devices) & Tùy chọn Bật/Tắt xuất file lưu ổ đĩa.
"""
import os
import sys
import re
import json
import time
import random
import threading
import traceback
import webbrowser
import subprocess
import hashlib
from queue import Queue, Empty
from datetime import datetime, timedelta, timezone

import tkinter as tk
from tkinter import filedialog, ttk, messagebox

import requests
from bs4 import BeautifulSoup
import pycountry

# =============== CẤU HÌNH THƯ MỤC ===============
INPUT_DIR  = 'input'
OUTPUT_DIR = 'output'
LOG_DIR    = os.path.join(OUTPUT_DIR, 'logs')
LICENSE_FILE = os.path.join(INPUT_DIR, 'license.dat')

# =============== THÔNG TIN ỨNG DỤNG ===============
APP_TITLE = "TikTok Dashboard — Apple Pro"
UA_STRING = "Mozilla/5.0 (Linux; Android 8.0.0; Plume L2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.88 Mobile Safari/537.36"

STATIC_FIELDS = {
    'Tên hiển thị': 'Tên hiển thị TikTok',
    'Follower': 'Số Follower',
    'Tổng Tim': 'Tổng Tim',
    'Số Video': 'Số Video',
    'Ngày tạo': 'Ngày tạo tài khoản',
    'Quốc gia (Tên)': 'Quốc gia'
}

# =============== LICENSE MANAGER ===============
def get_hwid():
    """Lấy mã máy duy nhất (Mainboard UUID trên Windows hoặc MAC Address)"""
    try:
        hwid = subprocess.check_output('wmic csproduct get uuid').decode().split('\n')[1].strip()
        return hashlib.md5(hwid.encode()).hexdigest().upper()
    except Exception:
        import uuid
        return hashlib.md5(str(uuid.getnode()).encode()).hexdigest().upper()

def verify_license_api(key, hwid):
    """Xác thực Key và Mã máy qua API Google Sheets"""
    API_URL = "https://script.google.com/macros/s/AKfycbwnuUmwjD65qmX-2-tThbGzjjUschY5MI7m5JqO2Qig8C1mhuv5yFYviDRp-Jt8YbNH/exec"
    try:
        response = requests.post(API_URL, json={"action": "auth", "key": key, "hwid": hwid}, timeout=15)
        return response.json()
    except Exception as e:
        return {"status": "error", "message": f"Lỗi kết nối máy chủ xác thực: {e}"}

# =============== TIỆN ÍCH QUỐC GIA ===============
def country_code_to_flag_emoji(country_code):
    if not country_code: 
        return ""
    try: 
        return ''.join(chr(127397 + ord(char)) for char in country_code.upper())
    except Exception: 
        return ""

def country_code_to_name(country_code):
    if not country_code: 
        return "Unknown"
    try:
        country = pycountry.countries.get(alpha_2=country_code.upper())
        return country.name if country else "Unknown"
    except Exception: 
        return "Unknown"

# =============== TIỆN ÍCH NỀN/ANIMATION ===============
class AppleBackground(tk.Canvas):
    def __init__(self, master, **kw):
        super().__init__(master, highlightthickness=0, bd=0, **kw)
        self.width = 800
        self.height = 600
        self.base_bg = "#f5f7fa"
        self.bind("<Configure>", self._on_resize)
        self._draw_background()

    def _on_resize(self, e):
        self.width = e.width
        self.height = e.height
        self._draw_background()

    def _draw_background(self):
        self.delete("all")
        for i in range(self.height):
            ratio = i / self.height
            r = int(245 * (1 - ratio) + 228 * ratio)
            g = int(247 * (1 - ratio) + 231 * ratio)
            b = int(250 * (1 - ratio) + 236 * ratio)
            color = f"#{r:02x}{g:02x}{b:02x}"
            self.create_line(0, i, self.width, i, fill=color)
        self.lower("all")

    def set_theme(self, theme):
        if theme == "Dark":
            self.base_bg = "#1d1d1f"
        else:
            self.base_bg = "#f5f7fa"
        self._draw_background()

class SmoothCounter:
    def __init__(self, label, fmt=str):
        self.label = label
        self.fmt = fmt
        self.current = 0

    def set(self, value, duration=250):
        try: 
            target = int(value)
        except Exception: 
            self.label.config(text=self.fmt(value))
            return
            
        start = self.current
        steps = max(1, duration // 16)
        delta = (target - start) / steps
        idx = 0
        
        def tick():
            nonlocal idx
            if idx >= steps:
                self.current = target
                self.label.config(text=self.fmt(self.current))
                return
            self.current = start + int(delta * idx)
            self.label.config(text=self.fmt(self.current))
            idx += 1
            self.label.after(16, tick)
            
        tick()

class AppleToast:
    def __init__(self, master):
        self.master = master
        self.container = tk.Toplevel(master)
        self.container.withdraw()
        self.container.overrideredirect(1)
        self.container.attributes("-topmost", True)
        self.container.attributes("-alpha", 0.95)
        
        self.msg = tk.Label(
            self.container, font=('Helvetica', 12), 
            bg="white", fg="black", padx=20, pady=12, bd=0, relief='flat'
        )
        self.msg.pack()
        self._hide_job = None
        master.bind("<Configure>", self._reposition)

    def _reposition(self, e=None):
        try:
            self.container.update_idletasks()
            x = self.master.winfo_rootx() + self.master.winfo_width() - self.container.winfo_width() - 20
            y = self.master.winfo_rooty() + self.master.winfo_height() - self.container.winfo_height() - 20
            self.container.geometry(f"+{x}+{y}")
        except Exception: 
            pass

    def show(self, text, timeout=2000, bg="white", fg="black"):
        theme = self.themes[self.current_theme]
        is_dark = self.current_theme == "Dark"
        
        final_bg = theme["card_bg"] if bg == "#111827" else (theme["card_bg"] if is_dark else "white")
        final_fg = fg if bg == "#111827" else (theme["fg"] if is_dark else "black")
        
        self.msg.config(text=text, bg=final_bg, fg=final_fg)
        self.container.deiconify()
        self._reposition()
        
        if self._hide_job: 
            self.container.after_cancel(self._hide_job)
        self._hide_job = self.container.after(timeout, self.hide)

    def hide(self): 
        self.container.withdraw()

# =============== SCRAPER CORE ===============
def _extract_country_code_from_jsonblobs(username, soup, html_text):
    for script_id in ['__UNIVERSAL_DATA_FOR_REHYDRATION__', 'SIGI_STATE']:
        try:
            tag = soup.find('script', id=script_id)
            if tag and tag.string:
                data = json.loads(tag.string)
                if script_id == '__UNIVERSAL_DATA_FOR_REHYDRATION__':
                    user = data.get('__DEFAULT_SCOPE__', {}).get('webapp.user-detail', {}).get('userInfo', {}).get('user', {})
                else:
                    user = data.get('UserPage', {}).get('userInfo', {}).get('user', {})
                    if not user.get('region'): 
                        user = data.get('UserModule', {}).get('users', {}).get(username, {})
                        
                code = user.get('region') or user.get('country') or user.get('countryCode')
                if code: 
                    return code.upper()
        except Exception: 
            pass
            
    try:
        m = re.search(r'"region"\s*:\s*"([A-Za-z]{2})"', html_text) or re.search(r'"countryCode"\s*:\s*"([A-Za-z]{2})"', html_text)
        if m: 
            return m.group(1).upper()
    except Exception: 
        pass
        
    return ""

def get_tiktok_stats(username, proxy=None):
    url = f"https://www.tiktok.com/@{username}"
    headers = {
        "Accept-Language": "en-US,en;q=0.9,ar;q=0.8", 
        "Accept": "text/html,application/xhtml+xml,*/*",
        "Connection": "keep-alive", 
        "User-Agent": UA_STRING, 
        "sec-ch-ua-platform": "\"Android\"", 
        "Sec-Fetch-Site": "same-origin"
    }
    
    proxies = {'http': proxy, 'https': proxy} if proxy else None
    
    try:
        response = requests.get(url, headers=headers, proxies=proxies, timeout=10)
        if response.status_code == 404: 
            return {"User": username, "Status": "Lỗi: Không tìm thấy (404)"}
        response.raise_for_status()
    except requests.exceptions.HTTPError as e: 
        return {"User": username, "Status": f"Lỗi: HTTP {getattr(e.response, 'status_code', '???')}"}
    except requests.exceptions.Timeout: 
        return {"User": username, "Status": "Lỗi: Timeout"}
    except requests.exceptions.RequestException: 
        return {"User": username, "Status": "Lỗi: Kết nối"}

    html = response.text
    soup = BeautifulSoup(html, 'html.parser')
    
    profile_ok = False
    nickname = ''
    follower = 0
    heart = 0
    videos = 0
    create_time_str = "Unknown"

    try:
        script_tag = soup.find('script', id='__UNIVERSAL_DATA_FOR_REHYDRATION__')
        if script_tag and script_tag.string:
            data = json.loads(script_tag.string)
            user_info = data['__DEFAULT_SCOPE__']['webapp.user-detail']['userInfo']
            nickname = user_info['user'].get('nickname', '')
            follower = user_info['stats'].get('followerCount', 0)
            heart = user_info['stats'].get('heartCount', 0)
            videos = user_info['stats'].get('videoCount', 0)
            
            ct_unix = user_info['user'].get('createTime')
            if ct_unix:
                try: 
                    create_time_str = datetime.fromtimestamp(int(ct_unix), timezone.utc).strftime('%Y-%m-%d | %H:%M:%S')
                except Exception: 
                    pass
            profile_ok = True
    except Exception:
        try:
            st = json.loads(soup.find('script', id='SIGI_STATE').string)
            u = st.get('UserPage', {}).get('userInfo', {})
            if u:
                nickname = u.get('user', {}).get('nickname', '') or nickname
                follower = u.get('stats', {}).get('followerCount', follower)
                heart = u.get('stats', {}).get('heartCount', heart)
                videos = u.get('stats', {}).get('videoCount', videos)
                
                ct_unix = u.get('user', {}).get('createTime')
                if ct_unix:
                    try: 
                        create_time_str = datetime.fromtimestamp(int(ct_unix), timezone.utc).strftime('%Y-%m-%d | %H:%M:%S')
                    except Exception: 
                        pass
                profile_ok = True
        except Exception: 
            profile_ok = False

    code = _extract_country_code_from_jsonblobs(username, soup, html)
    full_name = f"{country_code_to_name(code)} {country_code_to_flag_emoji(code)}".strip() if code else "Unknown"

    if not profile_ok:
        if "Profile is private" in html: 
            return {"User": username, "Status": "Lỗi: Profile Riêng tư"}
        if "Couldn't find this account" in html: 
            return {"User": username, "Status": "Lỗi: Không tìm thấy (HTML)"}
        return {"User": username, "Status": "Lỗi: Không trích xuất"}

    return {
        "User": username, 
        "Tên hiển thị": nickname, 
        "Follower": follower, 
        "Tổng Tim": heart,
        "Số Video": videos, 
        "Quốc gia": code or "N/A", 
        "Quốc gia (Tên)": full_name,
        "Ngày tạo": create_time_str, 
        "Status": "Thành công"
    }

# =============== APP CHÍNH ===============
class TikTokAppleProApp:
    def __init__(self, master):
        self.master = master
        master.withdraw() # GIẤU WINDOW
        
        os.makedirs(INPUT_DIR, exist_ok=True)
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        os.makedirs(LOG_DIR, exist_ok=True)

        self.themes = self._build_themes()
        self.current_theme = "Light"
        self.license_info = {
            "user": "Unknown", 
            "key": "None", 
            "expire_date": "Unknown", 
            "hwid": "Unknown"
        }
        
        self._init_variables()
        
        # --- LUỒNG KHỞI ĐỘNG NHANH CỰC ĐẠI ---
        saved_lic = self._load_saved_license()
        if saved_lic and "key" in saved_lic:
            self.license_info.update(saved_lic)
            self.license_info["hwid"] = get_hwid()
            
            # Khởi động Main App ngay lập tức
            self._init_main_app()
            
            # Bắn 1 luồng chạy ngầm để check API xem key còn sống không
            threading.Thread(target=self._background_auth_check, daemon=True).start()
        else:
            # Nếu chưa có Key thì hiện Form đăng nhập
            self._show_login_form()

    def _init_variables(self):
        self.user_file_path = None
        self.proxy_file_name = tk.StringVar(value="")
        self.output_file_name = tk.StringVar(value="tiktok_results")
        
        self.num_threads = tk.IntVar(value=12)
        self.max_retries = tk.IntVar(value=1)

        self.filter_follower_enabled = tk.BooleanVar(value=False)
        self.filter_follower_min = tk.StringVar()
        self.filter_follower_max = tk.StringVar()
        
        self.filter_heart_enabled = tk.BooleanVar(value=False)
        self.filter_heart_min = tk.StringVar()
        self.filter_heart_max = tk.StringVar()
        
        self.filter_video_enabled = tk.BooleanVar(value=False)
        self.filter_video_min = tk.StringVar()
        self.filter_video_max = tk.StringVar()

        self.export_file_enabled = tk.BooleanVar(value=True)
        self.delete_input_file = tk.BooleanVar(value=False)
        self.tips_var = tk.BooleanVar(value=True) 
        self.use_manual_input = tk.BooleanVar(value=False) 

        self.rotate_mode = tk.StringVar(value="per_attempt")
        self.shuffle_proxies = tk.BooleanVar(value=True)
        self.autoprune_bad_proxies = tk.BooleanVar(value=True)

        self.users_with_full_data = {}
        self.proxies = []
        self.results_list = []
        self.threads = []
        
        self.lock = threading.Lock()
        self.cancel_event = threading.Event()
        self.pause_event = threading.Event()
        self.testing_cancel_event = threading.Event()
        
        self.user_queue = None
        self.completed_count = 0
        self.total_users = 0
        self.success_count = tk.IntVar(value=0)
        self.error_count = tk.IntVar(value=0)
        
        self.start_time = None
        self.eta_var = tk.StringVar(value="—")
        self.current_index_var = tk.IntVar(value=0)
        self.current_user_var = tk.StringVar(value="—")
        
        self.testing_in_progress = False
        self.num_input_columns = 1
        self.all_available_fields = {}
        self._all_custom_bg = []
        self.bg = None

    # ---------- PHẦN ĐĂNG NHẬP / XÁC THỰC ----------
    def _load_saved_license(self):
        """Đọc Json Cache để mở Tool cực nhanh"""
        try:
            if os.path.exists(LICENSE_FILE):
                content = open(LICENSE_FILE, 'r', encoding='utf-8').read().strip()
                if content.startswith('{'):
                    return json.loads(content)
                elif content:
                    return {"key": content, "user": "Đang tải...", "expire_date": "Đang tải..."}
        except Exception: 
            pass
        return None

    def _show_login_form(self):
        self.login_window = tk.Toplevel(self.master)
        self.login_window.title("Xác Thực Bản Quyền")
        self.login_window.geometry("450x330")
        self.login_window.resizable(False, False)
        
        self.login_window.update_idletasks()
        w = 450
        h = 330
        x = (self.login_window.winfo_screenwidth() // 2) - (w // 2)
        y = (self.login_window.winfo_screenheight() // 2) - (h // 2)
        self.login_window.geometry(f'+{x}+{y}')
        
        self.login_window.configure(bg=self.themes[self.current_theme]["bg"])
        hwid = get_hwid()
        
        tk.Label(
            self.login_window, text="TIKTOK DASHBOARD PRO", 
            font=('Helvetica', 16, 'bold'), 
            bg=self.themes[self.current_theme]["bg"], 
            fg=self.themes[self.current_theme]["title_fg"]
        ).pack(pady=(20, 5))
        
        self.status_lbl = tk.Label(
            self.login_window, text="Vui lòng nhập Key kích hoạt để sử dụng", 
            font=('Helvetica', 10), bg=self.themes[self.current_theme]["bg"], 
            fg=self.themes[self.current_theme]["secondary"]
        )
        self.status_lbl.pack()

        frame_hwid = tk.Frame(self.login_window, bg=self.themes[self.current_theme]["bg"])
        frame_hwid.pack(fill="x", padx=40, pady=(15, 5))
        tk.Label(frame_hwid, text="Mã Máy (HWID):", bg=self.themes[self.current_theme]["bg"]).pack(anchor="w")
        hwid_entry = ttk.Entry(frame_hwid)
        hwid_entry.pack(fill="x")
        hwid_entry.insert(0, hwid)
        hwid_entry.configure(state='readonly')
        
        frame_key = tk.Frame(self.login_window, bg=self.themes[self.current_theme]["bg"])
        frame_key.pack(fill="x", padx=40, pady=(5, 15))
        tk.Label(frame_key, text="License Key:", bg=self.themes[self.current_theme]["bg"]).pack(anchor="w")
        self.key_entry = ttk.Entry(frame_key, font=('Helvetica', 11))
        self.key_entry.pack(fill="x")

        btn_frame = tk.Frame(self.login_window, bg=self.themes[self.current_theme]["bg"])
        btn_frame.pack(fill="x", padx=40)
        self.btn_login = ttk.Button(btn_frame, text="🔓 Kích Hoạt", command=lambda: self._check_license_thread(hwid))
        self.btn_login.pack(fill="x")
        
        ttk.Button(
            btn_frame, text="📋 Copy Mã Máy", 
            command=lambda: [self.master.clipboard_clear(), self.master.clipboard_append(hwid), messagebox.showinfo("Thành công", "Đã copy mã máy!")]
        ).pack(fill="x", pady=5)

        self.login_window.protocol("WM_DELETE_WINDOW", lambda: sys.exit())

    def _check_license_thread(self, hwid):
        key = self.key_entry.get().strip()
        if not key: 
            return messagebox.showwarning("Lỗi", "Vui lòng nhập License Key!")
            
        self.btn_login.config(state="disabled", text="Đang kiểm tra...")
        self.status_lbl.config(text="Đang kết nối máy chủ...", fg=self.themes[self.current_theme]["title_fg"])
        
        def run_auth():
            res = verify_license_api(key, hwid)
            self.master.after(0, lambda: self._handle_auth_result(res, key, hwid))
            
        threading.Thread(target=run_auth, daemon=True).start()

    def _handle_auth_result(self, res, key, hwid):
        if res.get("status") == "success":
            self.license_info.update({
                "user": res["user"], 
                "key": key, 
                "expire_date": res["expire_date"], 
                "hwid": hwid
            })
            try: 
                with open(LICENSE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(self.license_info, f)
            except Exception: 
                pass
            
            messagebox.showinfo("Thành công", f"Xin chào {res['user']}")
            self.login_window.destroy()
            self._init_main_app() 
        else:
            self.btn_login.config(state="normal", text="🔓 Kích Hoạt")
            self.status_lbl.config(text="Vui lòng nhập Key kích hoạt để sử dụng", fg=self.themes[self.current_theme]["secondary"])
            msg = res.get("message", "Key không hợp lệ!")
            if "hết hạn" in msg.lower():
                msg = "Key đã hết hạn vui lòng liên hệ admin tele @Admcv9"
            messagebox.showerror("Lỗi Kích Hoạt", msg)

    # --- CHẠY NGẦM KIỂM TRA BẢN QUYỀN KHI MỞ APP NHANH ---
    def _background_auth_check(self):
        hwid = self.license_info["hwid"]
        key = self.license_info["key"]
        res = verify_license_api(key, hwid)
        self.master.after(0, lambda: self._handle_bg_auth_result(res, key, hwid))

    def _handle_bg_auth_result(self, res, key, hwid):
        if res.get("status") == "success":
            # Cập nhật thông tin Cache mới nhất lỡ admin có đổi ngày
            self.license_info.update({
                "user": res["user"], 
                "key": key, 
                "expire_date": res["expire_date"], 
                "hwid": hwid
            })
            try: 
                with open(LICENSE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(self.license_info, f)
            except Exception: 
                pass
            self._update_license_ui()
        else:
            msg = res.get("message", "Key không hợp lệ!")
            if "hết hạn" in msg.lower():
                msg = "Key đã hết hạn vui lòng liên hệ admin tele @Admcv9"
            self._logout_with_msg(msg)

    def _update_license_ui(self):
        if hasattr(self, 'license_info_label'):
            d_key = self.license_info.get('key', '')
            if len(d_key) > 8: 
                d_key = f"{d_key[:4]}...{d_key[-4:]}"
            info_text = f"👤 Khách: {self.license_info.get('user', 'Unknown')}   |   🔑 Key: {d_key}   |   💻 Mã máy: {self.license_info.get('hwid', 'Unknown')}   |   ⏳ Hạn: {self.license_info.get('expire_date', 'Unknown')}"
            self.license_info_label.config(text=info_text)

    # ---------- PHẦN KIỂM TRA HẾT HẠN AUTO LOG-OUT ----------
    def _check_expiration(self):
        try:
            expire_str = self.license_info.get("expire_date", "")
            if expire_str and expire_str != "Unknown" and expire_str != "Đang tải...":
                expire_dt = datetime.strptime(expire_str, "%d/%m/%Y %H:%M")
                if datetime.now() > expire_dt:
                    self._logout_with_msg("Key đã hết hạn vui lòng liên hệ admin tele @Admcv9")
                    return
        except Exception: 
            pass
        self.master.after(60000, self._check_expiration)

    def _logout_with_msg(self, msg):
        if os.path.exists(LICENSE_FILE): 
            os.remove(LICENSE_FILE)
            
        self.cancel_event.set()
        self.testing_cancel_event.set()
        
        messagebox.showwarning("Cảnh báo Bản Quyền", msg)
        
        for widget in self.master.winfo_children(): 
            widget.destroy()
            
        self.__init__(self.master)

    # ---------- KHỞI TẠO APP CHÍNH TRÁNH TÀN ẢNH ----------
    def _init_main_app(self):
        self.master.title(APP_TITLE)
        self.master.geometry("1250x750")
        self.master.minsize(1050, 700)
        self.master.update_idletasks()
        
        # Center Window
        x = (self.master.winfo_screenwidth() // 2) - (self.master.winfo_width() // 2)
        y = (self.master.winfo_screenheight() // 2) - (self.master.winfo_height() // 2)
        self.master.geometry(f'+{x}+{y}')
        
        self.toast = AppleToast(self.master)
        self.toast.themes = self.themes 
        
        # VẼ TOÀN BỘ GIAO DIỆN KHI WINDOW ĐANG BỊ GIẤU (WITHDRAWN)
        self._build_ui()
        self.apply_theme(self.current_theme)
        self._start_brand_animation()
        
        self.master.bind("<Control-o>", lambda e: self.select_file())
        self.master.bind("<Control-r>", lambda e: self.start_processing())
        self.master.bind("<space>", lambda e: self.toggle_pause())
        self.master.bind("<Escape>", lambda e: self.cancel_processing())
        self.master.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # BẬT WINDOW LÊN SAU KHI MỌI THỨ ĐÃ SẴN SÀNG
        self.master.deiconify() 
        self.master.after(60000, self._check_expiration)

    def _build_themes(self):
        return {
            "Light": {
                "bg": "#f5f7fa", "fg": "#1d1d1f", "btn_bg": "#ffffff", "btn_fg": "#1d1d1f", 
                "input_bg": "#ffffff", "title_fg": "#007aff", "card_bg": "#ffffff", 
                "err_fg": "#ff3b30", "ok_fg": "#34c759", "border": "#c6c6c8", 
                "accent": "#007aff", "secondary": "#8e8e93"
            },
            "Dark": {
                "bg": "#000000", "fg": "#ffffff", "btn_bg": "#1c1c1e", "btn_fg": "#ffffff", 
                "input_bg": "#1c1c1e", "title_fg": "#0a84ff", "card_bg": "#1c1c1e", 
                "err_fg": "#ff453a", "ok_fg": "#32d74b", "border": "#38383a", 
                "accent": "#0a84ff", "secondary": "#8e8e93"
            }
        }

    def apply_theme(self, theme_name):
        self.current_theme = theme_name
        theme = self.themes[theme_name]
        self.master.configure(bg=theme["bg"])
        
        if hasattr(self, 'toast'): 
            self.toast.current_theme = theme_name 
            
        if not self.bg: 
            self.bg = AppleBackground(self.master)
            self.bg.place(x=0, y=0, relwidth=1, relheight=1)
            tk.Misc.lower(self.bg)
            
        if self.bg: 
            self.bg.set_theme(theme_name)
            
        style = ttk.Style()
        style.theme_use('clam')
        
        style.configure(".", background=theme["bg"], foreground=theme["fg"])
        style.configure("TFrame", background=theme["bg"])
        style.configure("Inner.TFrame", background=theme["card_bg"])
        
        style.configure(
            "TLabelframe", background=theme["card_bg"], foreground=theme["fg"], 
            bordercolor=theme["border"], relief="solid", borderwidth=1, padding=(10,10)
        )
        style.configure(
            "TLabelframe.Label", foreground=theme["title_fg"], 
            background=theme["card_bg"], font=('Helvetica', 14, 'bold')
        )
        
        style.configure("TLabel", background=theme["bg"], foreground=theme["fg"])
        style.configure("Inner.TLabel", background=theme["card_bg"], foreground=theme["fg"])
        style.configure("SubtleCard.TLabel", background=theme["card_bg"], foreground=theme["secondary"], font=('Helvetica', 11))
        
        style.configure(
            "TButton", background=theme["btn_bg"], foreground=theme["btn_fg"], 
            borderwidth=1, bordercolor=theme["border"], font=('Helvetica', 11), padding=(12, 8)
        )
        style.map("TButton", background=[('active', theme["accent"])], foreground=[('active', theme["btn_bg"])])
        
        style.configure(
            "Accent.TButton", background=theme["accent"], foreground=theme["btn_bg"], 
            font=('Helvetica', 12, 'bold'), padding=(14, 10), borderwidth=0
        )
        style.map("Accent.TButton", background=[('active', theme["title_fg"])])
        
        style.configure(
            "TEntry", fieldbackground=theme["input_bg"], foreground=theme["fg"], 
            borderwidth=1, bordercolor=theme["border"], insertcolor=theme["fg"], padding=(8, 6)
        )
        style.configure(
            "TSpinbox", fieldbackground=theme["input_bg"], foreground=theme["fg"], 
            borderwidth=1, bordercolor=theme["border"], padding=(8, 6)
        )
        
        style.configure("TCheckbutton", background=theme["bg"], foreground=theme["fg"], font=('Helvetica', 11))
        style.configure("TRadiobutton", background=theme["bg"], foreground=theme["fg"], font=('Helvetica', 11))
        style.configure("Inner.TCheckbutton", background=theme["card_bg"], foreground=theme["fg"], font=('Helvetica', 11))
        style.configure("Inner.TRadiobutton", background=theme["card_bg"], foreground=theme["fg"], font=('Helvetica', 11))
        
        style.configure("TNotebook", background=theme["bg"], borderwidth=0)
        style.configure(
            "TNotebook.Tab", background=theme["bg"], foreground=theme["secondary"], 
            font=('Helvetica', 13), padding=(12, 8), borderwidth=0
        )
        style.map("TNotebook.Tab", background=[('selected', theme["bg"])], foreground=[('selected', theme["accent"])])
        
        style.configure(
            "Green.Horizontal.TProgressbar", background=theme["ok_fg"], 
            troughcolor=theme["border"], bordercolor=theme["border"]
        )
        
        style.configure(
            "Treeview", background=theme["input_bg"], fieldbackground=theme["input_bg"], 
            foreground=theme["fg"], borderwidth=1, bordercolor=theme["border"], relief="solid"
        )
        style.configure(
            "Treeview.Heading", background=theme["card_bg"], foreground=theme["fg"], 
            font=('Helvetica', 11, 'bold'), relief="flat", borderwidth=0
        )
        
        style.configure(
            "Vertical.TScrollbar", troughcolor=theme["bg"], background=theme["border"], 
            bordercolor=theme["bg"], arrowcolor=theme["secondary"], relief='flat', width=8
        )
        style.map("Vertical.TScrollbar", background=[('active', theme["secondary"])])
        
        style.configure(
            "Horizontal.TScrollbar", troughcolor=theme["bg"], background=theme["border"], 
            bordercolor=theme["bg"], arrowcolor=theme["secondary"], relief='flat', height=8
        )
        style.map("Horizontal.TScrollbar", background=[('active', theme["secondary"])])
        
        for w in self._all_custom_bg:
            try: 
                w.config(
                    bg=theme["input_bg"], fg=theme["fg"], insertbackground=theme["fg"], 
                    selectbackground=theme["accent"], selectforeground=theme["btn_bg"], 
                    highlightcolor=theme["border"], highlightbackground=theme["border"]
                )
            except Exception: 
                pass
                
        try: 
            self.results_tree.tag_configure("error_row", foreground=theme["err_fg"])
            self.results_tree.tag_configure("success_row", foreground=theme["ok_fg"])
        except Exception: 
            pass
            
        try:
            self.tab_analytics.config(bg=theme["bg"])
            self.tab_settings.config(bg=theme["bg"])
            self.tab_logs.config(bg=theme["bg"])
        except Exception: 
            pass
            
        try: 
            self.brand_label.config(bg=theme["bg"], fg=theme["secondary"])
        except Exception: 
            pass
            
        self._brand_colors = (theme["secondary"], theme["accent"], theme["title_fg"])

    def _start_brand_animation(self):
        if not hasattr(self, "brand_label"): 
            return
        self._brand_full_text = "Admin Văn Linh"
        self._brand_pos = 0
        self._brand_mode = "typing"
        self._brand_pulse_i = 0
        self._brand_job = self.master.after(60, self._brand_anim_step)

    def _brand_anim_step(self):
        try:
            sec, acc, _ = getattr(
                self, "_brand_colors", 
                (self.themes[self.current_theme]["secondary"], 
                 self.themes[self.current_theme]["accent"], 
                 self.themes[self.current_theme]["title_fg"])
            )
            
            if self._brand_mode == "typing":
                txt = self._brand_full_text[: self._brand_pos]
                cursor = "▍" if self._brand_pos % 2 == 0 else ""
                self.brand_label.config(text=txt + cursor, fg=acc)
                self._brand_pos += 1
                if self._brand_pos <= len(self._brand_full_text): 
                    self._brand_job = self.master.after(70, self._brand_anim_step)
                else:
                    self.brand_label.config(text=self._brand_full_text, fg=sec)
                    self._brand_mode = "pulse"
                    self._brand_pulse_i = 0
                    self._brand_job = self.master.after(320, self._brand_anim_step)
                return
                
            self._brand_pulse_i += 1
            self.brand_label.config(text=self._brand_full_text, fg=acc if self._brand_pulse_i % 2 == 0 else sec)
            if self._brand_pulse_i < 10: 
                self._brand_job = self.master.after(320, self._brand_anim_step)
            else:
                self._brand_pos = 0
                self._brand_mode = "typing"
                self._brand_job = self.master.after(800, self._brand_anim_step)
        except Exception: 
            return

    def _build_ui(self):
        # --- 1. HEADER CHÍNH (TRÊN CÙNG) ---
        header = tk.Frame(self.master, bg=self.themes[self.current_theme]["bg"], height=80)
        header.pack(side=tk.TOP, fill="x", padx=0, pady=0)
        header.pack_propagate(False)
        
        header_inner = tk.Frame(header, bg=self.themes[self.current_theme]["bg"])
        header_inner.pack(fill="both", expand=True, padx=40, pady=0)
        
        title_frame = tk.Frame(header_inner, bg=self.themes[self.current_theme]["bg"])
        title_frame.pack(side=tk.LEFT, fill="y")
        
        self.title_label = tk.Label(
            title_frame, text="TikTok Analytics Pro", 
            font=('Helvetica', 24, 'bold'), 
            bg=self.themes[self.current_theme]["bg"], 
            fg=self.themes[self.current_theme]["title_fg"]
        )
        self.title_label.pack(side=tk.LEFT)
        
        self.brand_label = tk.Label(
            title_frame, text="", 
            font=('Helvetica', 12, 'bold'), 
            bg=self.themes[self.current_theme]["bg"], 
            fg=self.themes[self.current_theme]["secondary"]
        )
        self.brand_label.pack(side=tk.LEFT, padx=(14, 0), pady=(6, 0))
        
        right_header = tk.Frame(header_inner, bg=self.themes[self.current_theme]["bg"])
        right_header.pack(side=tk.RIGHT, fill="y")
        
        ttk.Checkbutton(right_header, text="Tip nổi", variable=self.tips_var).pack(side=tk.RIGHT, padx=(15, 0))
        
        for t in ("Light", "Dark"): 
            tk.Button(
                right_header, text=t, 
                command=lambda tn=t: self.apply_theme(tn), 
                font=('Helvetica', 11), 
                bg=self.themes[self.current_theme]["btn_bg"], 
                fg=self.themes[self.current_theme]["btn_fg"], 
                relief="flat", bd=1, padx=15, pady=8
            ).pack(side=tk.RIGHT, padx=(8, 0))

        # --- 2. FOOTER HIỂN THỊ BẢN QUYỀN (DƯỚI CÙNG) ---
        footer = tk.Frame(self.master, bg=self.themes[self.current_theme]["bg"])
        footer.pack(side=tk.BOTTOM, fill="x", padx=40, pady=(0, 20))
        
        license_frame = tk.Frame(
            footer, bg=self.themes[self.current_theme]["card_bg"], 
            highlightbackground=self.themes[self.current_theme]["border"], 
            highlightthickness=1, bd=0
        )
        license_frame.pack(fill="x", ipady=2)
        
        display_key = self.license_info.get('key', '')
        if len(display_key) > 8: 
            display_key = f"{display_key[:4]}...{display_key[-4:]}"
            
        hwid_str = self.license_info.get('hwid', 'Unknown')
        user_str = self.license_info.get('user', 'Unknown')
        expire_str = self.license_info.get('expire_date', 'Unknown')
        
        info_text = f"👤 Khách: {user_str}   |   🔑 Key: {display_key}   |   💻 Mã máy: {hwid_str}   |   ⏳ Hạn: {expire_str}"
        
        self.license_info_label = tk.Label(
            license_frame, text=info_text, 
            font=('Helvetica', 10, 'bold'), 
            bg=self.themes[self.current_theme]["card_bg"], 
            fg=self.themes[self.current_theme]["accent"], 
            pady=8
        )
        self.license_info_label.pack()

        # --- 3. MAIN CONTENT (GIỮA) ---
        main_content = tk.Frame(self.master, bg=self.themes[self.current_theme]["bg"])
        main_content.pack(side=tk.TOP, fill="both", expand=True, padx=40, pady=(25, 15))
        
        self._build_dashboard_cards(main_content)
        
        content_frame = tk.Frame(main_content, bg=self.themes[self.current_theme]["bg"])
        content_frame.pack(fill="both", expand=True, pady=(25, 0))
        
        self._build_main_tabs(content_frame)

    def _build_dashboard_cards(self, parent):
        cards_frame = tk.Frame(parent, bg=self.themes[self.current_theme]["bg"])
        cards_frame.pack(fill="x")
        
        self.card_total, self.total_value_label = self._make_apple_card(cards_frame, "TOTAL USERS", "0", "#007aff")
        self.card_success, self.success_value_label = self._make_apple_card(cards_frame, "SUCCESS", "0", "#34c759")
        self.card_error, self.error_value_label = self._make_apple_card(cards_frame, "ERRORS", "0", "#ff3b30")
        
        self.card_total.pack(side=tk.LEFT, fill="x", expand=True, padx=(0, 12))
        self.card_success.pack(side=tk.LEFT, fill="x", expand=True, padx=12)
        self.card_error.pack(side=tk.LEFT, fill="x", expand=True, padx=(12, 0))
        
        self.counter_total = SmoothCounter(self.total_value_label)
        self.counter_success = SmoothCounter(self.success_value_label)
        self.counter_error = SmoothCounter(self.error_value_label)

    def _make_apple_card(self, parent, title, value, color):
        theme = self.themes[self.current_theme]
        card = tk.Frame(
            parent, bg=theme["card_bg"], relief="flat", bd=1, 
            highlightbackground=theme["border"], highlightthickness=1
        )
        card.pack_propagate(False)
        card.configure(height=120)
        
        content = tk.Frame(card, bg=theme["card_bg"])
        content.pack(fill="both", expand=True, padx=25, pady=20)
        
        tk.Label(
            content, text=title, font=('Helvetica', 14), 
            bg=theme["card_bg"], fg=theme["secondary"]
        ).pack(anchor="w")
        
        value_label = tk.Label(
            content, text=value, font=('Helvetica', 32, 'bold'), 
            bg=theme["card_bg"], fg=color
        )
        value_label.pack(anchor="w", pady=(8, 0))
        
        return card, value_label

    def _build_main_tabs(self, parent):
        style = ttk.Style()
        style.configure("Custom.TNotebook", padding=[0, 10])
        
        self.main_notebook = ttk.Notebook(parent, style="Custom.TNotebook")
        self.main_notebook.pack(fill="both", expand=True)
        
        self.tab_analytics = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_analytics, text="📊 Analytics Dashboard")
        
        self.tab_logs = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_logs, text="📜 Event Log")
        
        self.tab_settings = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_settings, text="⚙️ Configuration")
        
        self._build_analytics_tab(self.tab_analytics)
        self._build_logs(self.tab_logs)
        self._build_settings_tab(self.tab_settings)

    def _build_analytics_tab(self, parent):
        parent.columnconfigure(0, weight=3)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(0, weight=1)
        
        left_frame = ttk.Frame(parent, padding=(0, 10, 0, 0))
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 15))
        
        right_frame = ttk.Frame(parent, padding=(0, 10, 0, 0))
        right_frame.grid(row=0, column=1, sticky="nsew")
        
        self._build_results_table(left_frame)
        self._build_control_panel(right_frame)

    def _build_results_table(self, parent):
        table_header = tk.Frame(parent, bg=self.themes[self.current_theme]["bg"])
        table_header.pack(fill="x", pady=(0, 15))
        
        tk.Label(
            table_header, text="Live Results", font=('Helvetica', 20, 'bold'), 
            bg=self.themes[self.current_theme]["bg"], fg=self.themes[self.current_theme]["fg"]
        ).pack(side=tk.LEFT)
        
        search_frame = tk.Frame(table_header, bg=self.themes[self.current_theme]["bg"])
        search_frame.pack(side=tk.RIGHT)
        
        self.search_var = tk.StringVar()
        ttk.Entry(search_frame, textvariable=self.search_var, width=25, font=('Helvetica', 11)).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(search_frame, text="Search", command=self.search_users).pack(side=tk.LEFT)
        ttk.Button(search_frame, text="📋 Copy User", command=self.copy_selected_users_to_clipboard).pack(side=tk.LEFT, padx=(8, 0))
        
        theme = self.themes[self.current_theme]
        table_container = tk.Frame(
            parent, bg=theme["card_bg"], relief="flat", bd=1, 
            highlightbackground=theme["border"], highlightthickness=1
        )
        table_container.pack(fill="both", expand=True)
        
        cols = ('User', 'Display Name', 'Followers', 'Likes', 'Videos', 'Country', 'Create Time', 'Status')
        self.results_tree = ttk.Treeview(table_container, columns=cols, show='headings', height=20)
        
        col_widths = [130, 160, 100, 100, 80, 140, 160, 140]
        for col_name, width in zip(cols, col_widths):
            self.results_tree.heading(col_name, text=col_name)
            self.results_tree.column(col_name, width=width)
            
        ysb = ttk.Scrollbar(table_container, orient="vertical", command=self.results_tree.yview, style="Vertical.TScrollbar")
        xsb = ttk.Scrollbar(table_container, orient="horizontal", command=self.results_tree.xview, style="Horizontal.TScrollbar")
        self.results_tree.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        
        ysb.pack(side="right", fill="y")
        xsb.pack(side="bottom", fill="x")
        self.results_tree.pack(side="left", fill="both", expand=True)
        
        self.results_tree.bind("<Control-c>", lambda e: self.copy_selected_users_to_clipboard())
        self.results_tree.bind("<Button-3>", self._show_results_context_menu)

    def _build_control_panel(self, parent):
        theme = self.themes[self.current_theme]
        control_card = tk.Frame(
            parent, bg=theme["card_bg"], relief="flat", bd=1, 
            highlightbackground=theme["border"], highlightthickness=1
        )
        control_card.pack(fill="both", expand=True)
        
        content = tk.Frame(control_card, bg=theme["card_bg"])
        content.pack(fill="both", expand=True, padx=15, pady=10)
        
        tk.Label(
            content, text="Control Center", font=('Helvetica', 16, 'bold'), 
            bg=theme["card_bg"], fg=theme["fg"]
        ).pack(anchor="w", pady=(0, 10))
        
        file_section = tk.Frame(content, bg=theme["card_bg"])
        file_section.pack(fill="x", pady=(0, 10))
        
        tk.Label(
            file_section, text="Input File", font=('Helvetica', 12, 'bold'), 
            bg=theme["card_bg"], fg=theme["fg"]
        ).pack(anchor="w")
        
        ttk.Button(file_section, text="📁 Select File (Ctrl+O)", command=self.select_file, style="Accent.TButton").pack(fill="x", pady=(5, 2))
        
        self.file_status = tk.Label(
            file_section, text="No file selected", font=('Helvetica', 10), 
            bg=theme["card_bg"], fg=theme["secondary"]
        )
        self.file_status.pack(anchor="w", pady=(2, 0))

        manual_section = tk.Frame(content, bg=theme["card_bg"])
        manual_section.pack(fill="x", pady=(0, 10))
        
        manual_top = tk.Frame(manual_section, bg=theme["card_bg"])
        manual_top.pack(fill="x")
        
        tk.Label(
            manual_top, text="Input trực tiếp", font=('Helvetica', 12, 'bold'), 
            bg=theme["card_bg"], fg=theme["fg"]
        ).pack(side=tk.LEFT)
        
        ttk.Checkbutton(manual_top, text="Dùng input trực tiếp", variable=self.use_manual_input).pack(side=tk.RIGHT)
        
        txt_wrap = tk.Frame(manual_section, bg=theme["card_bg"])
        txt_wrap.pack(fill="both", expand=False, pady=(5,0))
        
        self.user_input_text = tk.Text(txt_wrap, height=2, font=("Helvetica", 11), relief="solid", bd=1)
        self.user_input_text.pack(side=tk.LEFT, fill="both", expand=True)
        self._all_custom_bg.append(self.user_input_text)
        
        sb_in = ttk.Scrollbar(txt_wrap, command=self.user_input_text.yview, orient="vertical", style="Vertical.TScrollbar")
        sb_in.pack(side=tk.RIGHT, fill="y")
        self.user_input_text.config(yscrollcommand=sb_in.set)

        progress_section = tk.Frame(content, bg=theme["card_bg"])
        progress_section.pack(fill="x", pady=(0, 10))
        
        tk.Label(
            progress_section, text="Progress", font=('Helvetica', 12, 'bold'), 
            bg=theme["card_bg"], fg=theme["fg"]
        ).pack(anchor="w")
        
        self.progress_var = tk.IntVar(value=0)
        self.progress_bar = ttk.Progressbar(progress_section, variable=self.progress_var, maximum=100, style="Green.Horizontal.TProgressbar")
        self.progress_bar.pack(fill="x", pady=(5, 4))
        
        self.progress_text = tk.Label(
            progress_section, text="Ready to start", font=('Helvetica', 10), 
            bg=theme["card_bg"], fg=theme["secondary"]
        )
        self.progress_text.pack(anchor="w")
        
        btn_section = tk.Frame(content, bg=theme["card_bg"])
        btn_section.pack(fill="x", pady=(0, 10))
        
        self.start_btn = ttk.Button(btn_section, text="🚀 Start Analysis (Ctrl+R)", command=self.start_processing, style="Accent.TButton")
        self.start_btn.pack(fill="x", pady=(0, 5))
        
        btn_row = tk.Frame(btn_section, bg=theme["card_bg"])
        btn_row.pack(fill="x")
        
        self.pause_btn = ttk.Button(btn_row, text="⏸️ Pause (Space)", command=self.toggle_pause, state=tk.DISABLED)
        self.pause_btn.pack(side=tk.LEFT, fill="x", expand=True, padx=(0, 4))
        
        self.cancel_btn = ttk.Button(btn_row, text="🛑 Cancel (Esc)", command=self.cancel_processing, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, fill="x", expand=True, padx=(4, 0))
        
        stats_section = tk.Frame(content, bg=theme["card_bg"])
        stats_section.pack(fill="x", pady=(0, 10))
        
        tk.Label(
            stats_section, text="Current Stats", font=('Helvetica', 12, 'bold'), 
            bg=theme["card_bg"], fg=theme["fg"]
        ).pack(anchor="w")
        
        self.stats_text = tk.Label(
            stats_section, text="Total: 0 | Success: 0 | Errors: 0", font=('Helvetica', 10), 
            bg=theme["card_bg"], fg=theme["secondary"]
        )
        self.stats_text.pack(anchor="w", pady=(2, 0))
        
        export_section = tk.Frame(content, bg=theme["card_bg"])
        export_section.pack(fill="x", pady=(5, 0))
        
        btn_row2 = tk.Frame(export_section, bg=theme["card_bg"])
        btn_row2.pack(fill="x", pady=(0, 0))
        
        ttk.Button(btn_row2, text="📂 Output Folder", command=self.open_output_folder).pack(side=tk.LEFT, fill="x", expand=True, padx=(0, 4))
        
        self.save_log_btn = ttk.Button(btn_row2, text="🧾 Save Log", command=self.save_log, state=tk.DISABLED)
        self.save_log_btn.pack(side=tk.LEFT, fill="x", expand=True, padx=(4, 0))

    def _build_logs(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        theme = self.themes[self.current_theme]
        
        log_container = tk.Frame(
            parent, bg=theme["card_bg"], relief="flat", bd=1, 
            highlightbackground=theme["border"], highlightthickness=1
        )
        log_container.pack(fill="both", expand=True, padx=20, pady=15)
        
        top = ttk.Frame(log_container, padding=(15, 15, 15, 10))
        top.pack(fill="x")
        ttk.Button(top, text="📋 Copy danh sách LỖI", command=self.copy_errors_to_clipboard).pack(side=tk.LEFT)
        
        text_frame = ttk.Frame(log_container, padding=(15, 0, 15, 15))
        text_frame.pack(fill="both", expand=True)
        
        self.log_text = tk.Text(text_frame, height=16, wrap=tk.WORD, font=("Helvetica", 11), relief="flat", bd=0)
        self.log_text.pack(side=tk.LEFT, fill="both", expand=True)
        self._all_custom_bg.append(self.log_text)
        
        sb = ttk.Scrollbar(text_frame, command=self.log_text.yview, orient="vertical", style="Vertical.TScrollbar")
        sb.pack(side=tk.RIGHT, fill="y")
        self.log_text.config(yscrollcommand=sb.set, state=tk.DISABLED)

    def _build_settings_tab(self, parent):
        self.sidebar_canvas = tk.Canvas(parent, highlightthickness=0, bd=0, bg=self.themes[self.current_theme]["bg"])
        vsb = ttk.Scrollbar(parent, orient="vertical", command=self.sidebar_canvas.yview, style="Vertical.TScrollbar")
        
        left_content_frame = ttk.Frame(self.sidebar_canvas) 
        self.sidebar_frame_id = self.sidebar_canvas.create_window((0,0), window=left_content_frame, anchor="nw")
        
        def _configure_canvas(e):
            self.sidebar_canvas.itemconfig(self.sidebar_frame_id, width=e.width)
            self.sidebar_canvas.configure(scrollregion=self.sidebar_canvas.bbox("all"))
            
        self.sidebar_canvas.bind("<Configure>", _configure_canvas)
        self.sidebar_canvas.configure(yscrollcommand=vsb.set)
        
        self.sidebar_canvas.pack(side="left", fill="both", expand=True, padx=(20,0), pady=(15,15))
        vsb.pack(side="right", fill="y", padx=(0,20), pady=(15,15))
        
        content_parent = left_content_frame 
        content_parent.columnconfigure(0, weight=1, minsize=400)
        content_parent.columnconfigure(1, weight=1, minsize=400)
        content_parent.rowconfigure(0, weight=1)
        content_parent.rowconfigure(1, weight=1)

        # Lọc & Cài đặt
        g_filter = ttk.Labelframe(content_parent, text="Lọc & Cài đặt")
        g_filter.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=(0, 10))
        gf = ttk.Frame(g_filter, style="Inner.TFrame", padding=(8, 8))
        gf.pack(fill="both", expand=True, padx=5, pady=5)
        
        top = ttk.Frame(gf, style="Inner.TFrame")
        top.pack(fill="x", padx=8, pady=(5, 10))
        ttk.Label(top, text="Số Luồng:", style="SubtleCard.TLabel", font=('Helvetica', 12)).pack(side=tk.LEFT)
        ttk.Spinbox(top, from_=1, to=100, textvariable=self.num_threads, width=6).pack(side=tk.LEFT, padx=(6,12))
        ttk.Label(top, text="Thử lại (lỗi):", style="SubtleCard.TLabel", font=('Helvetica', 12)).pack(side=tk.LEFT)
        ttk.Spinbox(top, from_=0, to=5, textvariable=self.max_retries, width=4).pack(side=tk.LEFT, padx=(6,0))

        def _build_filter_row(parent_frame, chk_var, text, min_var, max_var):
            f_main = ttk.Frame(parent_frame, style="Inner.TFrame")
            f_main.pack(fill="x", padx=8, pady=(10, 2))
            f_chk = ttk.Frame(f_main, style="Inner.TFrame")
            f_chk.pack(fill="x")
            ttk.Checkbutton(f_chk, text=f"Lọc {text}", variable=chk_var, style="Inner.TCheckbutton").pack(side=tk.LEFT)
            f_entries = ttk.Frame(f_main, style="Inner.TFrame")
            f_entries.pack(fill="x", padx=(18, 0), pady=(4,0))
            ttk.Label(f_entries, text="Từ (Min):", style="SubtleCard.TLabel").pack(side=tk.LEFT, padx=(0, 4))
            ttk.Entry(f_entries, textvariable=min_var, width=10).pack(side=tk.LEFT, fill="x", expand=True, padx=(0, 6))
            ttk.Label(f_entries, text="Đến (Max):", style="SubtleCard.TLabel").pack(side=tk.LEFT, padx=(4, 4))
            ttk.Entry(f_entries, textvariable=max_var, width=10).pack(side=tk.LEFT, fill="x", expand=True)
            
        _build_filter_row(gf, self.filter_follower_enabled, "Follower", self.filter_follower_min, self.filter_follower_max)
        _build_filter_row(gf, self.filter_heart_enabled, "Tổng Tim", self.filter_heart_min, self.filter_heart_max)
        _build_filter_row(gf, self.filter_video_enabled, "Số Video", self.filter_video_min, self.filter_video_max)

        # Proxy
        g_input = ttk.Labelframe(content_parent, text="Input & Quản lý Proxy")
        g_input.grid(row=0, column=1, sticky="nsew", padx=(10, 15), pady=(0, 10)) 
        gp = ttk.Frame(g_input, style="Inner.TFrame", padding=(8, 8))
        gp.pack(fill="both", expand=True, padx=5, pady=5)
        
        ttk.Label(gp, text="Nhập Proxy (ip:port:user:pass)", style="SubtleCard.TLabel").pack(anchor="w", padx=8, pady=(5,2))
        ftxt = ttk.Frame(gp, style="Inner.TFrame")
        ftxt.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        
        self.proxy_text = tk.Text(ftxt, height=6, width=40, font=("Helvetica", 11))
        self.proxy_text.pack(side=tk.LEFT, fill="both", expand=True)
        self._all_custom_bg.append(self.proxy_text)
        
        sb = ttk.Scrollbar(ftxt, command=self.proxy_text.yview, orient="vertical", style="Vertical.TScrollbar")
        sb.pack(side=tk.RIGHT, fill="y")
        self.proxy_text.config(yscrollcommand=sb.set)
        
        fline = ttk.Frame(gp, style="Inner.TFrame")
        fline.pack(fill="x", padx=8, pady=4)
        ttk.Entry(fline, textvariable=self.proxy_file_name, width=25).pack(side=tk.LEFT, fill="x", expand=True, padx=(0,6))
        ttk.Button(fline, text="Nạp từ file", command=self.load_proxies_from_file_button).pack(side=tk.LEFT)
        
        opt = ttk.Frame(gp, style="Inner.TFrame")
        opt.pack(fill="x", padx=8, pady=4)
        ttk.Label(opt, text="Luân phiên:", style="SubtleCard.TLabel").pack(side=tk.LEFT)
        ttk.Radiobutton(opt, text="User", variable=self.rotate_mode, value="per_user", style="Inner.TRadiobutton").pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(opt, text="Lần thử", variable=self.rotate_mode, value="per_attempt", style="Inner.TRadiobutton").pack(side=tk.LEFT, padx=4)
        
        opt2 = ttk.Frame(gp, style="Inner.TFrame")
        opt2.pack(fill="x", padx=8, pady=4)
        self.btn_test_one = ttk.Button(opt2, text="🔎 Test 1", command=self.test_one_proxy)
        self.btn_test_all = ttk.Button(opt2, text="🧪 Quét All", command=self.test_all_proxies)
        self.btn_test_one.pack(side=tk.LEFT, fill="x", expand=True, padx=(0,4))
        self.btn_test_all.pack(side=tk.LEFT, fill="x", expand=True, padx=(4,0))
        
        opt3 = ttk.Frame(gp, style="Inner.TFrame")
        opt3.pack(fill="x", padx=8, pady=(2,5))
        ttk.Checkbutton(opt3, text="Trộn ngẫu nhiên proxy", variable=self.shuffle_proxies, style="Inner.TCheckbutton").pack(side=tk.LEFT)
        ttk.Checkbutton(opt3, text="Tự loại proxy lỗi", variable=self.autoprune_bad_proxies, style="Inner.TCheckbutton").pack(side=tk.RIGHT)

        # File Export Cột
        g_output = ttk.Labelframe(content_parent, text="Cấu Hình Xuất File & Cột")
        g_output.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=(0, 15), pady=(10, 0)) 
        gout = ttk.Frame(g_output, style="Inner.TFrame", padding=(8, 8))
        gout.pack(fill="both", expand=True, padx=5, pady=5)
        
        fname_line = ttk.Frame(gout, style="Inner.TFrame")
        fname_line.pack(fill="x", padx=8, pady=(5, 6))
        ttk.Label(fname_line, text="Tên file Output:", style="SubtleCard.TLabel").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Entry(fname_line, textvariable=self.output_file_name).pack(side=tk.LEFT, fill='x', expand=True, padx=0)
        
        ttk.Checkbutton(gout, text="Xuất kết quả ra file Text (.txt)", variable=self.export_file_enabled, style="Inner.TCheckbutton").pack(anchor="w", padx=8, pady=(8,2))
        ttk.Checkbutton(gout, text="Tự xóa file Input sau khi hoàn tất", variable=self.delete_input_file, style="Inner.TCheckbutton").pack(anchor="w", padx=8, pady=(2,8))

        ttk.Separator(gout, orient='horizontal').pack(fill='x', padx=8, pady=8)
        ttk.Label(gout, text="Cột Sẽ Xuất:", style="SubtleCard.TLabel").pack(anchor='w', padx=8, pady=(0,4))
        
        self.output_column_frame = ttk.Frame(gout, style="Inner.TFrame")
        self.output_column_frame.pack(fill="both", expand=True, padx=0, pady=0)
        self.update_column_selection()
        
        ttk.Label(
            content_parent, text="Bản quyền thuộc về Admin Văn Linh", 
            style="SubtleCard.TLabel", justify=tk.CENTER, font=('Helvetica', 10)
        ).grid(row=2, column=0, columnspan=2, pady=(15, 10))

    # ---------- THAO TÁC CƠ BẢN ----------
    def log(self, msg):
        if not hasattr(self, 'log_text') or self.log_text is None:
            try:
                self._log_buffer.append(msg)
            except Exception:
                self._log_buffer = [msg]
            return
            
        try:
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        except Exception: 
            pass
            
        if self.tips_var.get() and ("✅" in msg or "❌" in msg or "⛔" in msg): 
            self.toast.show(msg, timeout=1800, bg="#111827", fg="#bbf7d0" if "✅" in msg else "#fecaca")

    def copy_errors_to_clipboard(self):
        errors = [r for r in self.results_list if r.get('Status') != 'Thành công']
        text_copy = "\n".join(f"{r.get('User','')}|{r.get('Status','')}" for r in errors) if errors else "(Không có lỗi)"
        self.master.clipboard_clear()
        self.master.clipboard_append(text_copy)
        self.log(f"✅ Đã copy {len(errors)} dòng lỗi vào clipboard.")

    def copy_selected_users_to_clipboard(self):
        sel = self.results_tree.selection()
        if not sel:
            focus = self.results_tree.focus()
            if focus: 
                sel = (focus,)
                
        users = []
        for iid in sel:
            if iid:
                vals = self.results_tree.item(iid, 'values')
                if vals:
                    users.append(str(vals[0]))
                    
        if not users: 
            return self.log("ℹ️ Chưa chọn dòng nào để copy.")
            
        self.master.clipboard_clear()
        self.master.clipboard_append("\n".join(users))
        self.log(f"✅ Đã copy {len(users)} username.")

    def _show_results_context_menu(self, event):
        iid = self.results_tree.identify_row(event.y)
        if iid and iid not in self.results_tree.selection(): 
            self.results_tree.selection_set(iid)
            self.results_tree.focus(iid)
            
        if not hasattr(self, "_results_menu"):
            self._results_menu = tk.Menu(self.master, tearoff=0)
            self._results_menu.add_command(label="📋 Copy Username", command=self.copy_selected_users_to_clipboard)
            self._results_menu.add_separator()
            self._results_menu.add_command(label="📋 Copy cả dòng", command=self._copy_selected_rows_to_clipboard)
            
        self._results_menu.tk_popup(event.x_root, event.y_root)

    def _copy_selected_rows_to_clipboard(self):
        sel = self.results_tree.selection()
        if not sel:
            focus = self.results_tree.focus()
            if focus: 
                sel = (focus,)
                
        lines = []
        for iid in sel:
            if iid:
                vals = self.results_tree.item(iid, 'values')
                if vals:
                    lines.append("\t".join(map(str, vals)))
                    
        if not lines: 
            return self.log("ℹ️ Chưa chọn dòng nào.")
            
        self.master.clipboard_clear()
        self.master.clipboard_append("\n".join(lines))
        self.log(f"✅ Đã copy {len(lines)} dòng.")

    def select_file(self):
        p = filedialog.askopenfilename(
            defaultextension=".txt", 
            filetypes=[("TXT/CSV", "*.txt *.csv"), ("All", "*.*")], 
            initialdir=INPUT_DIR
        )
        if p:
            self.user_file_path = p
            self.file_status.config(text=os.path.basename(p), foreground=self.themes[self.current_theme]["ok_fg"])
            self.log(f"📄 Đã chọn file user: {os.path.basename(p)}")
            self.num_input_columns = self._analyze_input_columns(p)
            self.update_column_selection()

    def _analyze_input_columns(self, file_path):
        max_cols = 1
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for _ in range(5):
                    line = f.readline().strip()
                    if line: 
                        max_cols = max(max_cols, line.count('|') + 1)
            return min(max_cols, 20)
        except Exception: 
            return 1

    def _analyze_input_columns_from_text(self, raw_text):
        max_cols = 1
        try:
            lines = [ln.strip() for ln in (raw_text or "").splitlines() if ln.strip()]
            for line in lines[:5]: 
                max_cols = max(max_cols, line.count('|') + 1)
            return min(max_cols, 20)
        except Exception: 
            return 1

    def open_output_folder(self):
        path = os.path.abspath(OUTPUT_DIR)
        os.makedirs(path, exist_ok=True)
        webbrowser.open(f"file://{path}")

    def save_log(self):
        try:
            p = os.path.join(LOG_DIR, f"log_{datetime.now().strftime('%Y%M%d_%H%M%S')}.log")
            with open(p, "w", encoding="utf-8") as f: 
                f.write(self.log_text.get("1.0", tk.END))
            self.log(f"✅ Đã lưu log tại: {p}")
        except Exception as e: 
            self.log(f"❌ Lỗi lưu log: {e}")

    def update_column_selection(self):
        for w in self.output_column_frame.winfo_children(): 
            w.destroy()
            
        new_fields = {}
        for i in range(self.num_input_columns):
            new_fields[f'Input_Cột {i+1}'] = f'Dữ liệu Gốc (Cột {i+1})'
            
        self.all_available_fields = {**new_fields, **STATIC_FIELDS}
        self.column_vars = {}

        col_canvas = tk.Canvas(self.output_column_frame, height=200, highlightthickness=0, bd=0, bg=self.themes[self.current_theme]["card_bg"]) 
        col_scroll = ttk.Scrollbar(self.output_column_frame, orient="vertical", command=col_canvas.yview, style="Vertical.TScrollbar")
        col_frame = ttk.Frame(col_canvas, style="Inner.TFrame")
        
        col_frame.bind("<Configure>", lambda e: col_canvas.configure(scrollregion=col_canvas.bbox("all")))
        col_canvas.create_window((0,0), window=col_frame, anchor="nw")
        col_canvas.configure(yscrollcommand=col_scroll.set)
        
        col_canvas.pack(side="left", fill="x", expand=True, padx=(8,0), pady=(0, 8))
        col_scroll.pack(side="right", fill="y", padx=(0,8), pady=(0, 8))

        for key, name in self.all_available_fields.items():
            var = tk.BooleanVar(value=True if key.startswith('Input_Cột') or key in ['Follower'] else False)
            self.column_vars[key] = var
            ttk.Checkbutton(col_frame, text=name, variable=var, style="Inner.TCheckbutton").pack(anchor="w", padx=12, pady=2)
            
        if self.num_input_columns > 1:
            self.log(f"✅ Đã nhận diện {self.num_input_columns} cột Input.")
        else:
            self.log("ℹ️ Chỉ tìm thấy 1 cột Input (User).")

    def _format_proxy(self, raw):
        raw = raw.strip()
        if not raw: 
            return None
        parts = raw.split(':')
        if len(parts) == 2: 
            return f"http://{raw}"
        elif len(parts) == 4: 
            return f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
        return None

    def _load_proxies_file(self, fp):
        proxies = []
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                for line in f:
                    p = self._format_proxy(line)
                    if p: 
                        proxies.append(p)
                    else: 
                        self.log(f"⚠️ Bỏ qua proxy không hợp lệ: {line.strip()}")
            self.log(f"✅ Tải {len(proxies)} proxy từ {os.path.basename(fp)}")
            return proxies
        except FileNotFoundError: 
            return []
        except Exception as e: 
            self.log(f"❌ Lỗi khi đọc proxy: {e}")
            return []

    def load_proxies_from_controls(self):
        self.proxies = []
        direct = self.proxy_text.get("1.0", tk.END).strip()
        if direct:
            for ln in direct.splitlines():
                if ln.strip():
                    p = self._format_proxy(ln)
                    if p: 
                        self.proxies.append(p)
                    else: 
                        self.log(f"⚠️ Proxy trực tiếp không hợp lệ: {ln}")
                        
        if not self.proxies and self.proxy_file_name.get().strip():
            fp = os.path.join(INPUT_DIR, self.proxy_file_name.get().strip())
            self.proxies = self._load_proxies_file(fp)

    def load_proxies_from_file_button(self):
        if not self.proxy_file_name.get().strip(): 
            return messagebox.showinfo("Thiếu tên file", "Nhập tên file proxy trong thư mục /input/")
            
        fp = os.path.join(INPUT_DIR, self.proxy_file_name.get().strip())
        lst = self._load_proxies_file(fp)
        
        if lst:
            self.proxies = lst[:]
            self.proxy_text.delete("1.0", tk.END)
            self.proxy_text.insert("1.0", "\n".join([p.replace("http://","").replace("@",":") for p in lst]))
            self.log(f"📥 Đã nạp {len(lst)} proxy từ file.")

    def test_one_proxy(self):
        def worker(prx):
            try:
                r = requests.get("https://www.tiktok.com/", headers={"User-Agent": UA_STRING}, proxies={"http": prx, "https": prx}, timeout=8)
                self.master.after(0, lambda: self.log(f"✅ Proxy OK — HTTP {r.status_code}"))
            except Exception as e: 
                self.master.after(0, lambda: self.log(f"❌ Proxy lỗi: {e}"))
                
        proxy = None
        direct = self.proxy_text.get("1.0", tk.END).strip().splitlines()
        
        if direct and direct[0].strip(): 
            proxy = self._format_proxy(direct[0])
            
        if not proxy and self.proxy_file_name.get().strip():
            fp = os.path.join(INPUT_DIR, self.proxy_file_name.get().strip())
            lst = self._load_proxies_file(fp)
            if lst: 
                proxy = lst[0]
                
        if not proxy: 
            return self.log("ℹ️ Không có proxy để test.")
            
        self.log(f"🔎 Đang thử proxy: {proxy}")
        threading.Thread(target=worker, args=(proxy,), daemon=True).start()

    def test_all_proxies(self):
        if self.testing_in_progress:
            self.testing_cancel_event.set()
            return self.log("⛔ Yêu cầu dừng quét proxy...")
            
        self.load_proxies_from_controls()
        proxies = list(dict.fromkeys(self.proxies))
        
        if not proxies: 
            return self.log("ℹ️ Không có proxy để quét.")

        self.testing_in_progress = True
        self.testing_cancel_event.clear()
        
        self.btn_test_all.config(text="🛑 Dừng quét", state=tk.NORMAL)
        self.btn_test_one.config(state=tk.DISABLED)
        self.log(f"🧪 Bắt đầu quét {len(proxies)} proxy...")
        
        threading.Thread(target=self._scan_proxies_worker, args=(proxies,), daemon=True).start()

    def _scan_proxies_worker(self, proxies):
        max_workers = min(20, len(proxies))
        good = []
        bad = []
        q = Queue()
        for p in proxies: 
            q.put(p)

        def tester():
            while not self.testing_cancel_event.is_set():
                try: 
                    proxy = q.get_nowait()
                except Empty: 
                    break
                try:
                    r = requests.get("https://www.tiktok.com/", headers={"User-Agent": UA_STRING}, proxies={"http": proxy, "https": proxy}, timeout=6)
                    if r.status_code < 500: 
                        good.append(proxy)
                        self.master.after(0, lambda px=proxy: self.log(f"✅ LIVE: {px}"))
                    else: 
                        bad.append(proxy)
                        self.master.after(0, lambda px=proxy: self.log(f"❌ BAD ({r.status_code}): {px}"))
                except Exception: 
                    bad.append(proxy)
                    self.master.after(0, lambda px=proxy: self.log(f"❌ BAD (exception): {px}"))
                finally: 
                    q.task_done()

        threads = []
        for _ in range(max_workers):
            t = threading.Thread(target=tester, daemon=True)
            t.start()
            threads.append(t)

        while any(t.is_alive() for t in threads):
            if self.testing_cancel_event.is_set(): 
                break
            time.sleep(0.1)

        while not q.empty():
            try: 
                q.get_nowait()
                q.task_done()
            except Empty: 
                break

        for t in threads: 
            t.join(timeout=0.2)

        self.master.after(0, lambda: self.log(f"🧪 Quét xong: {len(good)} live / {len(bad)} die."))
        if self.autoprune_bad_proxies.get() and not self.testing_cancel_event.is_set():
            self.proxies = good[:]
            self.master.after(0, lambda: self.log(f"✂️ Giữ lại {len(self.proxies)} proxy live."))
            
        self.testing_in_progress = False
        self.master.after(0, lambda: self.btn_test_all.config(text="🧪 Quét All", state=tk.NORMAL))
        self.master.after(0, lambda: self.btn_test_one.config(state=tk.NORMAL))

    def _assign_proxy(self, user_index, attempt):
        if not self.proxies: 
            return None
        n = len(self.proxies)
        if self.rotate_mode.get() == "per_user": 
            return self.proxies[user_index % n]
        return self.proxies[(user_index + attempt) % n]

    # ---------- LUỒNG CHẠY CHÍNH ----------
    def start_processing(self):
        manual_text = self.user_input_text.get("1.0", tk.END).strip()
        use_manual = bool(manual_text) and (self.use_manual_input.get() or not self.user_file_path)
        
        if self.use_manual_input.get() and not manual_text: 
            return messagebox.showerror("Lỗi", "Chưa dán user vào ô nhập trực tiếp!")
            
        if not use_manual and not self.user_file_path: 
            return messagebox.showerror("Lỗi", "Vui lòng chọn Tệp User hoặc dán vào ô nhập trực tiếp!")

        self.input_mode = "manual" if use_manual else "file"
        self._manual_users_cache = manual_text if use_manual else ""
        
        self.cancel_event.clear()
        self.pause_event.clear()
        self.completed_count = 0
        self.total_users = 0
        self.success_count.set(0)
        self.error_count.set(0)
        
        self.start_time = datetime.now()
        self.eta_var.set("—")
        self.progress_text.config(text="Đang check (0/0): —")
        self.progress_var.set(0)
        
        self.results_tree.delete(*self.results_tree.get_children())
        self._reset_ordered_insertion()
        
        self._enable_controls(False)
        self.main_notebook.select(self.tab_analytics) 
        
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)

        threading.Thread(target=self._processor, daemon=True).start()

    def _enable_controls(self, enabled):
        if enabled:
            self.start_btn.config(state=tk.NORMAL, text="🚀 Start Analysis (Ctrl+R)")
            self.cancel_btn.config(state=tk.DISABLED, text="🛑 Cancel (Esc)")
            self.pause_btn.config(state=tk.DISABLED)
            self.save_log_btn.config(state=tk.NORMAL)
        else:
            self.start_btn.config(state=tk.DISABLED, text="ĐANG XỬ LÝ...")
            self.cancel_btn.config(state=tk.NORMAL, text="🛑 Cancel (Esc)")
            self.pause_btn.config(state=tk.NORMAL, text="⏸️ Pause (Space)")
            self.save_log_btn.config(state=tk.DISABLED)

    def _processor(self):
        try:
            if self.input_mode == "manual":
                self.users_with_full_data = self._load_users_from_text(self._manual_users_cache)
                self.num_input_columns = self._analyze_input_columns_from_text(self._manual_users_cache)
            else:
                self.users_with_full_data = self._load_users(self.user_file_path)
                self.num_input_columns = self._analyze_input_columns(self.user_file_path)

            self.master.after(0, self.update_column_selection)
            users = list(self.users_with_full_data.keys())
            self.total_users = len(users)
            
            if not users: 
                return self.log("❌ Không có user nào.")

            self._init_progress(self.total_users)
            self._update_progress()
            
            self.load_proxies_from_controls()
            if self.shuffle_proxies.get() and self.proxies: 
                random.shuffle(self.proxies)
                
            if self.proxies:
                self.log(f"🌐 Dùng {len(self.proxies)} proxy.")
            else:
                self.log("ℹ️ Không dùng Proxy.")

            self.results_list = []
            self.user_queue = Queue()
            for i, u in enumerate(users): 
                self.user_queue.put((u, i))

            try: 
                num_threads = self.num_threads.get() if self.num_threads.get() > 0 else 8
            except tk.TclError: 
                num_threads = 8
                
            try: 
                max_retries = self.max_retries.get()
            except tk.TclError: 
                max_retries = 1

            self.log(f"🚀 Khởi động {num_threads} luồng cho {self.total_users} user.")
            self.threads = []
            for _ in range(num_threads):
                t = threading.Thread(target=self._worker, args=(self.user_queue, max_retries), daemon=True)
                t.start()
                self.threads.append(t)

            while True:
                if self.cancel_event.is_set(): 
                    self._drain_queue(self.user_queue)
                    break
                if self.user_queue.unfinished_tasks == 0: 
                    break
                self._compute_eta()
                self.master.after(0, self._update_progress)
                time.sleep(0.25)

            for t in self.threads: 
                t.join(timeout=0.8)
                
            if self.cancel_event.is_set(): 
                return self.log("--- ⛔️ ĐÃ HỦY. KHÔNG LƯU FILE ---")

            self.log("--- ✅ HOÀN TẤT ---")
            
            combined = []
            for res in sorted(self.results_list, key=lambda r: r.get('_idx', 10**9)):
                original = self.users_with_full_data.get(res.get('User'), "| " * (self.num_input_columns - 1))
                parts = original.split('|')
                row = {}
                for i in range(self.num_input_columns):
                    row[f'Input_Cột {i+1}'] = parts[i] if i < len(parts) else ""
                row.update(res)
                combined.append(row)

            final = self._apply_filter(combined)
            
            successes = [r for r in final if r.get('Status') == 'Thành công']
            errors = [r for r in final if r.get('Status') != 'Thành công']
            self.log(f"📦 Kết quả: {len(successes)} thành công, {len(errors)} lỗi.")

            # CHỈ LƯU FILE NẾU CHECKBOX ĐƯỢC BẬT
            if self.export_file_enabled.get():
                headers = self._get_selected_headers()
                ts = datetime.now().strftime('%Y%M%d_%H%M%S')
                base_name = self.output_file_name.get().strip() or "tiktok_results"
                
                self._save_results(successes, headers, os.path.join(OUTPUT_DIR, f"{base_name}_{ts}"))
                if errors: 
                    self._save_errors(errors, os.path.join(OUTPUT_DIR, f"{base_name}_errors_{ts}"))
            else:
                self.log("ℹ️ Tùy chọn xuất file đang tắt, không lưu kết quả ra ổ đĩa.")

            if self.delete_input_file.get() and getattr(self, "input_mode", "file") == "file" and self.user_file_path:
                self._delete_user_file(self.user_file_path)

        except Exception as e: 
            self.log(f"❌ Lỗi chung: {e}")
            self.log(traceback.format_exc())
        finally:
            self.master.after(0, lambda: self._enable_controls(True))
            self.master.after(0, self._update_progress)

    def _worker(self, q: Queue, max_retries):
        while True:
            if self.cancel_event.is_set(): 
                break
            try: 
                user, idx = q.get(timeout=0.5)
            except Empty: 
                break

            try:
                while self.pause_event.is_set() and not self.cancel_event.is_set(): 
                    time.sleep(0.1)

                self.master.after(0, lambda i=idx+1, tot=self.total_users, u=user: self._set_current(i, tot, u))

                attempt = 0
                stats = None
                while attempt <= max_retries and not self.cancel_event.is_set():
                    proxy = self._assign_proxy(idx, attempt)
                    stats = get_tiktok_stats(user, proxy)
                    if stats.get("Status") in ("Lỗi: Timeout", "Lỗi: Kết nối"): 
                        attempt += 1
                        time.sleep(0.35)
                        continue
                    break

                try:
                    if isinstance(stats, dict): 
                        stats['_idx'] = idx
                except Exception: 
                    pass

                with self.lock:
                    self.results_list.append(stats)
                    if stats.get('Status') == 'Thành công':
                        self.success_count.set(self.success_count.get() + 1)
                        tag = ("success_row",)
                    else:
                        self.error_count.set(self.error_count.get() + 1)
                        tag = ("error_row",)

                    v_fol = f"{int(stats.get('Follower',0)):,}" if isinstance(stats.get('Follower',0), int) else stats.get('Follower','')
                    v_hrt = f"{int(stats.get('Tổng Tim',0)):,}" if isinstance(stats.get('Tổng Tim',0), int) else stats.get('Tổng Tim','')

                    values = (
                        stats.get('User', 'N/A'),
                        stats.get('Tên hiển thị', ''),
                        v_fol,
                        v_hrt,
                        str(stats.get('Số Video', '')),
                        stats.get('Quốc gia (Tên)', 'N/A'),
                        stats.get('Ngày tạo', 'Unknown'),
                        stats.get('Status', '')
                    )
                    self.master.after(0, lambda i=idx, v=values, t=tag: self._enqueue_ordered_row(i, v, t))

                status_msg = stats.get('Status')
                if status_msg == 'Thành công':
                    self.master.after(0, lambda u=user, f=values[2]: self.log(f"✅ @{u}: Follower={f}"))
                elif status_msg != "Lỗi: Không tìm thấy (HTML)": 
                    self.master.after(0, lambda u=user, s=status_msg: self.log(f"❌ @{u}: {s}"))

                self._step_progress()
                self._compute_eta()
                self.master.after(0, self._update_progress)

            except Exception as e:
                self.master.after(0, lambda u=user: self.log(f"❌ Lỗi worker @{u}: {e}"))
            finally:
                try: 
                    q.task_done()
                except Exception: 
                    pass

    # ---------- PHỤ TRỢ TIẾN TRÌNH ----------
    def _init_progress(self, total):
        self.progress_bar.configure(maximum=max(total, 1))
        self.progress_var.set(0)
        self.stats_text.config(text="Total: 0 | Success: 0 | Errors: 0")
        try: 
            self.progress_text.config(text="0% - 0/0")
        except Exception: 
            pass
        self.counter_total.set(total)
        self.counter_success.set(0) 
        self.counter_error.set(0) 

    def _step_progress(self):
        self.completed_count += 1
        self.progress_var.set(self.completed_count)

    def _compute_eta(self):
        if self.completed_count == 0: 
            return self.eta_var.set("—")
        elapsed = (datetime.now() - self.start_time).total_seconds()
        rate = self.completed_count / elapsed if elapsed > 0 else 0
        remaining = max(self.total_users - self.completed_count, 0)
        eta_secs = int(remaining / rate) if rate > 0 else 0
        self.eta_var.set(str(timedelta(seconds=eta_secs)))
        
    def _update_progress(self):
        total = self.total_users
        success = self.success_count.get()
        errors = self.error_count.get()
        
        self.stats_text.config(text=f"Total: {total} | Success: {success} | Errors: {errors}")
        
        pct = 0 if total == 0 else int(self.completed_count * 100 / max(total, 1))
        eta_str = f" | ETA: {self.eta_var.get()}" if self.completed_count > 0 else ""
        
        try: 
            self.progress_text.config(text=f"{pct}% - {self.completed_count}/{total}{eta_str}")
        except Exception: 
            pass
            
        self.counter_success.set(success)
        self.counter_error.set(errors)

    def _set_current(self, idx, total, user):
        try: 
            self.progress_text.config(text=f"Đang check ({idx}/{total}): @{user}")
        except Exception: 
            pass
        self.current_index_var.set(idx)
        self.current_user_var.set(user)

    def _insert_row(self, values, tags):
        try:
            iid = self.results_tree.insert('', 'end', values=values, tags=tags)
            self.results_tree.see(iid)
        except Exception: 
            pass

    def _reset_ordered_insertion(self):
        self._ordered_rows = {}
        self._next_row_to_show = 0

    def _enqueue_ordered_row(self, idx, values, tags):
        self._ordered_rows[idx] = (values, tags)
        self._flush_ordered_rows()

    def _flush_ordered_rows(self):
        while self._next_row_to_show in self._ordered_rows:
            values, tags = self._ordered_rows.pop(self._next_row_to_show)
            self._insert_row(values, tags)
            self._next_row_to_show += 1

    def _apply_filter(self, results):
        def _parse_num(s_val):
            try:
                s_val_cleaned = s_val.strip().replace(",", "")
                if not s_val_cleaned: 
                    return None
                return int(s_val_cleaned)
            except Exception: 
                return None

        f_fol = self.filter_follower_enabled.get()
        fol_min = _parse_num(self.filter_follower_min.get())
        fol_max = _parse_num(self.filter_follower_max.get())
        
        f_hrt = self.filter_heart_enabled.get()
        hrt_min = _parse_num(self.filter_heart_min.get())
        hrt_max = _parse_num(self.filter_heart_max.get())
        
        f_vdo = self.filter_video_enabled.get()
        vdo_min = _parse_num(self.filter_video_min.get())
        vdo_max = _parse_num(self.filter_video_max.get())

        act = []
        if f_fol:
            if fol_min is not None and fol_max is not None: act.append(f"Follower ({fol_min:,} - {fol_max:,})")
            elif fol_min is not None: act.append(f"Follower ≥ {fol_min:,}")
            elif fol_max is not None: act.append(f"Follower ≤ {fol_max:,}")
        if f_hrt:
            if hrt_min is not None and hrt_max is not None: act.append(f"Tổng Tim ({hrt_min:,} - {hrt_max:,})")
            elif hrt_min is not None: act.append(f"Tổng Tim ≥ {hrt_min:,}")
            elif hrt_max is not None: act.append(f"Tổng Tim ≤ {hrt_max:,}")
        if f_vdo:
            if vdo_min is not None and vdo_max is not None: act.append(f"Số Video ({vdo_min:,} - {vdo_max:,})")
            elif vdo_min is not None: act.append(f"Số Video ≥ {vdo_min:,}")
            elif vdo_max is not None: act.append(f"Số Video ≤ {vdo_max:,}")

        if not act:
            self.log("ℹ️ Không áp dụng lọc ngưỡng.")
            return results

        self.log(f"🔎 Áp dụng {len(act)} bộ lọc: " + " VÀ ".join(act))
        
        out = []
        for r in results:
            if r.get('Status') != 'Thành công':
                out.append(r)
                continue
            
            ok = True
            try:
                if f_fol:
                    val_fol = int(r.get('Follower', 0))
                    if fol_min is not None and val_fol < fol_min: ok = False
                    if ok and fol_max is not None and val_fol > fol_max: ok = False
                if ok and f_hrt:
                    val_hrt = int(r.get('Tổng Tim', 0))
                    if hrt_min is not None and val_hrt < hrt_min: ok = False
                    if ok and hrt_max is not None and val_hrt > hrt_max: ok = False
                if ok and f_vdo:
                    val_vdo = int(r.get('Số Video', 0))
                    if vdo_min is not None and val_vdo < vdo_min: ok = False
                    if ok and vdo_max is not None and val_vdo > vdo_max: ok = False
            except Exception:
                ok = False
            
            if ok: 
                out.append(r)
            
        self.log(f"✅ Lọc xong: {len(out)}/{len(results)} hàng.")
        return out

    def _get_selected_headers(self):
        selected = [k for k,v in self.column_vars.items() if v.get()]
        inputs = [k for k in selected if k.startswith('Input_Cột')]
        inputs.sort(key=lambda x: int(x.split(' ')[1]))
        
        sorted_headers = inputs + [k for k in STATIC_FIELDS.keys() if k in selected]
        
        if not sorted_headers:
            self.log("⚠️ Không có cột nào được chọn. Xuất tất cả.")
            return list(self.all_available_fields.keys())
        return sorted_headers

    def _save_results(self, rows, headers, base):
        if not rows:
            return self.log("ℹ️ Không có kết quả 'Thành công' để lưu.")
        try:
            final = []
            for r in rows:
                obj = {h: r.get(h, '') for h in headers}
                final.append(obj)
                
            h = [x for x in headers if x in final[0]]
            
            with open(base + ".txt", 'w', encoding='utf-8') as f:
                f.write("|".join(h) + "\n")
                f.write("-" * (sum(len(x) for x in h) + len(h) - 1) + "\n")
                for row in final:
                    f.write("|".join(str(row.get(x, '')) for x in h) + "\n")
                    
            self.log(f"✅ Lưu TXT: {base + '.txt'}")
        except Exception as e:
            self.log(f"❌ Lỗi lưu file: {e}")

    def _save_errors(self, errors, base):
        try:
            with open(base + ".txt", 'w', encoding='utf-8') as f:
                heads = ["User", "Lý do (Status)"]
                f.write("|".join(heads) + "\n")
                f.write("-" * (sum(len(x) for x in heads) + len(heads) - 1) + "\n")
                for r in errors: 
                    f.write(f"{r.get('User', '')}|{r.get('Status', '')}\n")
            self.log(f"🧩 Lưu Lỗi TXT: {base + '.txt'}")
        except Exception as e:
            self.log(f"❌ Không thể lưu lỗi: {e}")

    def _delete_user_file(self, fp):
        try: 
            os.remove(fp)
            self.log(f"🗑️ Đã xóa file đầu vào: {os.path.basename(fp)}")
        except OSError as e: 
            self.log(f"❌ Lỗi khi xóa file {os.path.basename(fp)}: {e}")

    def _drain_queue(self, q: Queue):
        drained = 0
        while True:
            try: 
                q.get_nowait()
                q.task_done()
                drained += 1
            except Empty: 
                break
        if drained: 
            self.log(f"🧹 Dọn {drained} tác vụ khỏi hàng đợi.")

    def search_users(self):
        pat = self.search_var.get().strip()
        if not pat or pat == "Search users...":
            pat = "" 
            self.search_var.set("")
            
        try:
            for iid in self.results_tree.get_children():
                self.results_tree.delete(iid)
        except Exception: 
            pass
            
        try:
            for r in sorted(self.results_list, key=lambda x: x.get('_idx', 10**9)):
                row = [
                    r.get('User', ''), 
                    r.get('Tên hiển thị', ''), 
                    str(r.get('Follower', '')),
                    str(r.get('Tổng Tim', '')), 
                    str(r.get('Số Video', '')), 
                    r.get('Quốc gia (Tên)', ''), 
                    r.get('Ngày tạo', ''), 
                    r.get('Status', '')
                ]
                txt = "|".join(row)
                
                if not pat or re.search(pat, txt, flags=re.IGNORECASE):
                    v_fol = f"{int(r.get('Follower',0)):,}" if isinstance(r.get('Follower',0), int) else r.get('Follower','')
                    v_hrt = f"{int(r.get('Tổng Tim',0)):,}" if isinstance(r.get('Tổng Tim',0), int) else r.get('Tổng Tim','')
                    
                    values = (
                        row[0], row[1], v_fol, v_hrt, row[4], row[5], row[6], row[7]
                    )
                    tags = ("success_row",) if r.get('Status') == 'Thành công' else ("error_row",)
                    self.results_tree.insert('', 'end', values=values, tags=tags)
        except Exception: 
            pass

    def toggle_pause(self):
        if self.pause_btn['state'] == tk.DISABLED: 
            return
            
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.pause_btn.config(text="⏸️ Pause (Space)")
            self.log("▶️ Tiếp tục xử lý...")
        else:
            self.pause_event.set()
            self.pause_btn.config(text="▶️ Resume (Space)")
            self.log("⏸️ Đã tạm dừng các luồng...")

    def cancel_processing(self):
        if self.cancel_btn['state'] == tk.DISABLED: 
            return
            
        self.log("🛑 ĐÃ YÊU CẦU HỦY BỎ. Đang dừng các luồng...")
        self.cancel_event.set()
        self.pause_event.clear()
        self.cancel_btn.config(state=tk.DISABLED, text="ĐANG HỦY...")
        
        if self.user_queue is not None: 
            self._drain_queue(self.user_queue)

    def _load_users_from_text(self, raw_text: str):
        mp = {}
        try:
            lines = [ln.strip() for ln in (raw_text or "").splitlines() if ln.strip()]
            for full in lines:
                parts = full.split('|')
                user = parts[0].strip().lstrip('@')
                if user: 
                    mp[user] = full
            self.log(f"✅ Tải {len(mp)} user từ Input trực tiếp")
            return mp
        except Exception as e:
            self.log(f"❌ Lỗi khi đọc user từ Input trực tiếp: {e}")
            return {}

    def _load_users(self, fp):
        mp = {}
        try:
            with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    full = line.strip()
                    if not full: 
                        continue
                    parts = full.split('|')
                    user = parts[0].strip().lstrip('@')
                    if user: 
                        mp[user] = full
            self.log(f"✅ Tải {len(mp)} user từ {os.path.basename(fp)}")
            return mp
        except FileNotFoundError:
            self.log(f"❌ Không tìm thấy file '{fp}'")
            return {}
        except Exception as e:
            self.log(f"❌ Lỗi khi đọc user: {e}")
            return {}

    def _on_close(self):
        try:
            if hasattr(self, 'bg') and self.bg: 
                self.bg.destroy()
        except Exception: 
            pass
            
        self.cancel_event.set()
        self.testing_cancel_event.set()
        self.master.destroy()

def main():
    root = tk.Tk()
    app = TikTokAppleProApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
