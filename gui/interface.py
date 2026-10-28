# -*- coding: utf-8 -*-
"""
gui/interface.py
================
Cobalt MCM Tablo - Professional ECU & MCM Configurator Interface

Chevrolet Cobalt asboblar paneli (tablo) fotosuratiga aniq moslab chizilgan:
  * chapda yonilg'i ko'rsatkichi, RPM (0-8 x1000, qizil zona, qizil strelka)
  * o'rtada spidometr 0-180 (ko'k C-yoy, qizil strelka)
  * o'ngda CHEVROLET LCD displey (7-segmentli P va kilometraj)
  * tormoz (qizil) va faralar (yashil) ogohlantirish lampalari

Faqat standart tkinter ishlatiladi.
MCMCobaltApp(master, callbacks), run(), mainloop(), log(), status_lbl, vin_value, selected_adapter, ...
Yangi: MCMCobaltApp(backend=obj) - uds.py / j2534.py / recovery.py ni fon oqimida ulash.
"""

import inspect
import logging
import math
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, font as tkfont
from typing import Optional

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ ranglar
BG = "#070a12"
PANEL = "#0d1322"
CARD = "#101830"
HOVER = "#16213c"
LINE = "#1c2a46"
TXT = "#e2e8f0"
MUTED = "#64748b"
SOFT = "#94a3b8"
ACCENT = "#38bdf8"
OK = "#22c55e"
WARN = "#f59e0b"
ERR = "#ef4444"
VIOLET = "#a78bfa"


def _map_kw(kw: dict) -> dict:
    if "text_color" in kw:
        kw["fg"] = kw.pop("text_color")
    if "fg_color" in kw:
        kw["bg"] = kw.pop("fg_color")
    for k in ("hover_color", "corner_radius", "border_width", "border_color"):
        kw.pop(k, None)
    return kw


class Lbl(tk.Label):
    """tk.Label, lekin configure(text_color=...) ni ham tushunadi."""

    def configure(self, cnf=None, **kw):
        return super().configure(cnf, **_map_kw(kw))

    config = configure


def pick_font(root, names, default="Segoe UI"):
    try:
        fams = set(tkfont.families(root))
    except Exception:
        return default
    for n in names:
        if n in fams:
            return n
    return default


# ================================================================== TABLO
class Cluster(tk.Canvas):
    """Chevrolet Cobalt raqamli asboblar paneli (dizayn: 960x540)."""

    DW, DH = 960, 540
    LAV = "#b9a9ee"      # LCD rangi
    SEG = {
        "0": "abcdef", "1": "bc", "2": "abdeg", "3": "abcdg", "4": "bcfg",
        "5": "acdfg", "6": "acdefg", "7": "abc", "8": "abcdefg", "9": "abcdfg",
        "P": "abefg", "R": "eg", "N": "ceg", "D": "bcdeg",
    }

    def __init__(self, parent, family="Segoe UI", **kw):
        super().__init__(parent, bg="#000000", highlightthickness=0, **kw)
        self.family = family
        self.speed = 0.0
        self.rpm = 0.0
        self.gear = "P"
        self.odo = 27
        self.brake = True
        self.lights = True
        self.bind("<Configure>", lambda e: self.redraw())

    @staticmethod
    def sp_angle(v):
        v = max(0.0, min(180.0, v))
        return 270 - 1.5 * v if v <= 120 else 90 - 0.75 * (v - 120)

    @staticmethod
    def rp_angle(v):
        return 270 - 20.4 * max(0.0, min(8.0, v))

    def redraw(self):
        self.delete("all")
        W, H = self.winfo_width(), self.winfo_height()
        if W < 80 or H < 60:
            return
        s = min(W / self.DW, H / self.DH)
        ox, oy = (W - self.DW * s) / 2, (H - self.DH * s) / 2

        def X(v): return ox + v * s
        def Y(v): return oy + v * s

        def P(cx, cy, r, a):
            rad = math.radians(a)
            return (cx + r * math.cos(rad), cy - r * math.sin(rad))

        def flat(points):
            out = []
            for x, y in points:
                out += [X(x), Y(y)]
            return out

        def poly(points, **k):
            self.create_polygon(flat(points), **k)

        def line(points, w=1, **k):
            self.create_line(flat(points), width=max(1, w * s), **k)

        def oval(cx, cy, r, **k):
            if "width" in k:
                k["width"] = max(1, k["width"] * s)
            self.create_oval(X(cx - r), Y(cy - r), X(cx + r), Y(cy + r), **k)

        def arc(cx, cy, r, start, extent, w=1, **k):
            self.create_arc(X(cx - r), Y(cy - r), X(cx + r), Y(cy + r),
                            start=start, extent=extent, style="arc",
                            width=max(1, wd * s) if 'wd' in locals() else max(1, w * s), **k)

        def text(x, y, t, px, fill, bold=True, anchor="center", **k):
            self.create_text(X(x), Y(y), text=t, fill=fill, anchor=anchor,
                             font=(self.family, -max(6, int(px * s)),
                                   "bold" if bold else "normal"), **k)

        def rrect(x1, y1, x2, y2, r, **k):
            pts = [(x1 + r, y1), (x2 - r, y1), (x2, y1), (x2, y1 + r), (x2, y2 - r),
                   (x2, y2), (x2 - r, y2), (x1 + r, y2), (x1, y2), (x1, y2 - r),
                   (x1, y1 + r), (x1, y1)]
            self.create_polygon(flat(pts), smooth=True, **k)

        # Fon
        self.create_rectangle(0, 0, W, H, fill="#000000", outline="")
        for i in range(12):
            c = int(2 + i * 1.1)
            inset = i * 14
            rrect(inset, inset * 0.6, 960 - inset, 540 - inset * 0.6, 70,
                  fill="#%02x%02x%02x" % (c, c, c + 1), outline="")

        for col, wd, off in (("#26262a", 7, 0), ("#4c4c52", 1.6, -4)):
            self.create_arc(X(-40), Y(-390 + off), X(1000), Y(500 + off),
                            start=225, extent=90, style="arc", outline=col,
                            width=max(1, wd * s))

        # Yonilg'i
        fcx, fcy, fr = 300, 303, 225
        arc(fcx, fcy, fr, 152, 56, w=1.4, outline="#8c8c92")
        for i in range(0, 15):
            a = 153 + i * 3.8
            line([P(fcx, fcy, fr, a), P(fcx, fcy, fr - (11 if i % 7 == 0 else 7), a)],
                 w=1.6, fill="#e6e6ea")
        oval(112, 203, 6, fill="#7e7e84", outline="#3a3a3e", width=1)
        line([P(fcx, fcy, fr + 2, 203), P(fcx, fcy, fr - 16, 203)], w=3, fill="#d02020")
        line([P(fcx, fcy, fr - 16, 203), P(fcx, fcy, fr - 16, 197)], w=2, fill="#d02020")
        oval(100, 408, 6, outline="#c8c8cc", width=1.8)
        rrect(90, 292, 106, 314, 3, fill="#dcdce0", outline="")
        poly([(93, 295), (103, 295), (103, 302), (93, 302)], fill="#0c0c0e")
        line([(106, 299), (111, 299), (111, 309)], w=2, fill="#dcdce0")

        # RPM
        rc = (255, 305)
        oval(*rc, 148, fill="#09090b", outline="#18181b", width=2)
        a8 = self.rp_angle(8.2)
        arc(*rc, 137, a8, 270 - a8, w=1.2, outline="#b4b4ba")
        arc(*rc, 96, 124, 146, w=1.2, outline="#3a3a3e")
        arc(*rc, 99, 84, 40, w=2.6, outline="#d81f1f")
        v = 0.0
        while v <= 8.001:
            a = self.rp_angle(v)
            major = abs(v - round(v)) < 0.01
            red = v >= 7
            line([P(*rc, 137, a), P(*rc, 137 - (16 if major else 9), a)],
                 w=2.8 if major else 1.4, fill="#ff3030" if red else "#f0f0f4")
            if major:
                lx, ly = P(*rc, 108, a)
                text(lx, ly, str(int(round(v))), 21, "#f4f4f8")
            v += 0.5
        text(279, 427, "RPM", 9, "#d8d8de")
        text(279, 439, "x1000", 8, "#d8d8de", bold=False)

        # Spidometr
        sc = (480, 300)
        arc(*sc, 190, 44, 226, w=1.2, outline="#4a4a50")
        for wd, col in ((11, "#07202f"), (6, "#0c5580"), (2.6, "#2ab8f2")):
            arc(480, 298, 102, 47, 238, w=wd, outline=col)
        for vv in range(0, 181, 5):
            a = self.sp_angle(vv)
            if vv % 20 == 0:
                ln, wd = 13, 2.8
            elif vv % 10 == 0:
                ln, wd = 9, 1.9
            else:
                ln, wd = 5, 1.2
            line([P(*sc, 182, a), P(*sc, 182 - ln, a)], w=wd, fill="#f0f0f4")
            if vv % 20 == 0:
                lr = 147 + min(12, max(0, vv - 40) * 0.15)
                lx, ly = P(*sc, lr, a)
                text(lx, ly, str(vv), 19, "#f4f4f8")
        text(503, 470, "km/h", 11, "#d8d8de")
        for i in range(3):
            line([(440 + i * 7, 466), (440 + i * 7, 474)], w=1.4, fill="#c4c4ca")

        # LCD (CHEVROLET COBALT)
        lx1, ly1, lx2, ly2 = 596, 232, 870, 432
        poly([(626, 232), (644, 207), (850, 207), (868, 222), (868, 232)],
             fill="#121214", outline="#2c2c30")
        text(712, 219, "CHEVROLET COBALT", 11, "#8e8e94")
        for i in range(6):
            line([(792 + i * 2, 210 + i * 3.4), (862, 210 + i * 3.4)], w=1, fill="#2a2a2e")
        rrect(lx1, ly1, lx2, ly2, 5, fill="#0d0d0f", outline="#303034", width=2)
        rrect(lx1 + 6, ly1 + 6, lx2 - 6, ly2 - 6, 3, fill="#101013", outline="#141417")
        for i in range(7):
            yy = 438 + i * 4
            line([(612 + i * 9, yy), (868, yy)], w=1.5, fill="#3a3a40")

        def seg7(x, y, w, h, t, ch, on, off, k=0.13):
            d, g = t / 2, 1.6

            def sh(px, py):
                return (px + (y + h - py) * k, py)

            def hs(x0, x1, ym):
                return [sh(*p) for p in [(x0, ym), (x0 + d, ym - d), (x1 - d, ym - d),
                                         (x1, ym), (x1 - d, ym + d), (x0 + d, ym + d)]]

            def vs(xm, y0, y1):
                return [sh(*p) for p in [(xm, y0), (xm + d, y0 + d), (xm + d, y1 - d),
                                         (xm, y1), (xm - d, y1 - d), (xm - d, y0 + d)]]

            x0, x1 = x + d + g, x + w - d - g
            segs = {
                "a": hs(x0, x1, y + d), "g": hs(x0, x1, y + h / 2), "d": hs(x0, x1, y + h - d),
                "f": vs(x + d, y + d + g, y + h / 2 - g), "b": vs(x + w - d, y + d + g, y + h / 2 - g),
                "e": vs(x + d, y + h / 2 + g, y + h - d - g), "c": vs(x + w - d, y + h / 2 + g, y + h - d - g),
            }
            lit = self.SEG.get(ch, "")
            for n, pts in segs.items():
                poly(pts, fill=on if n in lit else off, outline="")

        g = (self.gear or "P")[:1].upper()
        seg7(714, 238, 26, 40, 6, g, self.LAV, "#17171c")
        cx0 = 752
        for ch in str(int(self.odo))[-6:]:
            seg7(cx0, 386, 19, 33, 4.4, ch, self.LAV, "#17171c")
            cx0 += 19 + 11
        text(cx0 + 4, 410, "km", 15, self.LAV, bold=False, anchor="w")

        # Ogohlantirish lampalari
        if self.brake:
            oval(808, 182, 13, outline="#ff2a2a", width=2.4)
            text(808, 183, "!", 18, "#ff2a2a")
            arc(808, 182, 20, 125, 110, w=2.4, outline="#ff2a2a")
            arc(808, 182, 20, -55, 110, w=2.4, outline="#ff2a2a")
        if self.lights:
            arc(926, 216, 10, 270, 180, w=2.6, outline="#22e04a")
            line([(926, 206), (926, 226)], w=2.6, fill="#22e04a")
            for i, dy in enumerate((-8, 0, 8)):
                line([(918, 216 + dy), (903, 216 + dy + (i - 1) * 3)], w=2.2, fill="#22e04a")

        def needle(c, ang, length, hw):
            rad = math.radians(ang)
            u = (math.cos(rad), -math.sin(rad))
            pv = (-u[1], u[0])

            def pp(a, b):
                return (c[0] + u[0] * a + pv[0] * b, c[1] + u[1] * a + pv[1] * b)

            body = [pp(-52, -9), pp(-44, -17), pp(-20, -hw), pp(14, -hw), pp(60, -hw * 0.6),
                    pp(length * 0.75, -hw * 0.3), pp(length, 0), pp(length * 0.75, hw * 0.3),
                    pp(60, hw * 0.6), pp(14, hw), pp(-20, hw), pp(-44, 17), pp(-52, 9)]
            poly(body, fill="#121216", outline="#2c2c32", width=1)
            line([pp(-46, -10), pp(-18, -hw + 3), pp(40, -hw * 0.55)], w=1.2, fill="#3d3d46")
            blade = [pp(-26, -6.5), pp(10, -9), pp(length * 0.6, -3.2), pp(length - 4, 0),
                     pp(length * 0.6, 3.2), pp(10, 9), pp(-26, 6.5)]
            poly(blade, fill="#e61414", outline="")
            line([pp(10, -9), pp(length * 0.6, -3.2)], w=1, fill="#ff6a5a")
            line([pp(-8, 0), pp(length * 0.55, 0)], w=1.6, fill="#4a0a0a")
            oval(c[0], c[1], 5, fill="#07070a", outline="#2a2a30", width=1)

        needle(rc, self.rp_angle(self.rpm), 115, 18)
        needle(sc, self.sp_angle(self.speed), 146, 21)


class ActionButton(tk.Frame):
    """Ikki qatorli tugma."""

    def __init__(self, parent, icon, title, subtitle, accent, command, family="Segoe UI"):
        super().__init__(parent, bg=CARD, cursor="hand2",
                         highlightthickness=1, highlightbackground=LINE)
        self.command, self.accent, self._enabled = command, accent, True
        self.strip = tk.Frame(self, bg=accent, width=4)
        self.strip.pack(side="left", fill="y")
        self.icon = tk.Label(self, text=icon, bg=CARD, fg=accent,
                             font=("Segoe UI Symbol", 15), width=3)
        self.icon.pack(side="left")
        self.box = tk.Frame(self, bg=CARD)
        self.box.pack(side="left", fill="x", expand=True, pady=6)
        self.t = tk.Label(self.box, text=title, bg=CARD, fg=TXT,
                          font=(family, 10, "bold"), anchor="w")
        self.t.pack(fill="x")
        self.sub = tk.Label(self.box, text=subtitle, bg=CARD, fg=MUTED,
                            font=(family, 8), anchor="w")
        self.sub.pack(fill="x")
        for w in (self, self.icon, self.box, self.t, self.sub):
            w.bind("<Enter>", lambda e: self._paint(HOVER, self.accent))
            w.bind("<Leave>", lambda e: self._paint(CARD, LINE))
            w.bind("<Button-1>", self._click)

    def _paint(self, bg, border):
        if not self._enabled:
            return
        for w in (self, self.icon, self.box, self.t, self.sub):
            w.configure(bg=bg)
        self.configure(highlightbackground=border)

    def _click(self, _e=None):
        if self._enabled and self.command:
            self.command()

    def set_enabled(self, state: bool):
        self._enabled = state
        self.t.configure(fg=TXT if state else MUTED)
        self.configure(cursor="hand2" if state else "arrow")


class MCMCobaltApp:
    """Cobalt MCM Tablo GUI - asosiy ilova klassi."""

    def __init__(self, master: Optional[tk.Misc] = None, callbacks: Optional[dict] = None,
                 backend=None):
        self.root = master or tk.Tk()
        self._owns_root = master is None
        if hasattr(self.root, "title"):
            self.root.title("Cobalt MCM Tablo - Professional ECU & MCM Configurator")
            self.root.geometry("1280x800")
            self.root.minsize(1180, 720)
        self.root.configure(bg=BG)

        self._main_thread = threading.current_thread()
        self._uiq = queue.Queue()
        self.callbacks = dict(callbacks or {})
        self.backend = backend
        self._connected = False
        self._busy = False
        self._live_stop = threading.Event()
        self._live_thread = None
        self.stock_path = ""

        self.ui_font = pick_font(self.root, ["Segoe UI", "Inter", "Helvetica Neue", "DejaVu Sans"])
        self.num_font = pick_font(self.root, ["Bahnschrift", "Eurostile", "Segoe UI", "DejaVu Sans"])
        self.ui, self.num = self.ui_font, self.num_font

        self.selected_adapter = tk.StringVar(value="Scanmatik SM2 USB (J2534)")
        self.selected_car = tk.StringVar(value="Cobalt MCM 2025-2026")
        self.vin_value = tk.StringVar(value="")
        self.mcm_recovery_enabled = tk.BooleanVar(value=False)
        self.progress_var = tk.StringVar(value="")

        self._style()
        self._build_ui()
        self._tick_clock()
        self._pump()
        if self._owns_root and hasattr(self.root, "protocol"):
            self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.log("Tizim ishga tushdi. J2534 adapterini tanlang va ulaning.", "info")
        self.root.after(500, self.sweep)
        logger.info("Cobalt MCM Tablo GUI initialized successfully.")

    def set_callbacks(self, **callbacks):
        self.callbacks.update({k: v for k, v in callbacks.items() if v})

    def set_backend(self, backend):
        self.backend = backend

    def _style(self):
        st = ttk.Style(self.root)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure("Dark.TCombobox", fieldbackground=CARD, background=CARD, foreground=TXT,
                     arrowcolor=ACCENT, bordercolor=LINE, lightcolor=CARD, darkcolor=CARD,
                     selectbackground=CARD, selectforeground=TXT, padding=6)
        st.map("Dark.TCombobox", fieldbackground=[("readonly", CARD)],
               foreground=[("readonly", TXT)], bordercolor=[("focus", ACCENT)])
        self.root.option_add("*TCombobox*Listbox.background", CARD)
        self.root.option_add("*TCombobox*Listbox.foreground", TXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#000000")

    def _section(self, parent, title):
        wrap = tk.Frame(parent, bg=PANEL)
        wrap.pack(fill="x", padx=14, pady=(10, 0))
        tk.Label(wrap, text=title, bg=PANEL, fg=ACCENT, font=(self.ui, 8, "bold"),
                 anchor="w").pack(fill="x", pady=(0, 4))
        return wrap

    def _build_ui(self):
        root = self.root
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(1, weight=1)

        header = tk.Frame(root, bg="#0a0f1d", height=62, highlightthickness=1,
                          highlightbackground=LINE)
        header.grid(row=0, column=0, sticky="ew")
        header.pack_propagate(False)
        tk.Label(header, text="◆", bg="#0a0f1d", fg=ACCENT,
                 font=(self.ui, 20, "bold")).pack(side="left", padx=(18, 8))
        tbox = tk.Frame(header, bg="#0a0f1d")
        tbox.pack(side="left")
        tk.Label(tbox, text="COBALT MCM TABLO", bg="#0a0f1d", fg="#ffffff",
                 font=(self.ui, 14, "bold")).pack(anchor="w")
        tk.Label(tbox, text="Professional ECU & MCM Configurator  •  Chevrolet Cobalt MCM",
                 bg="#0a0f1d", fg=MUTED, font=(self.ui, 8)).pack(anchor="w")

        self.status_lbl = Lbl(header, text="● ALOQA YO'Q", bg="#140c12", fg=ERR,
                              font=(self.ui, 10, "bold"), padx=16, pady=6,
                              highlightthickness=1, highlightbackground="#3b1219")
        self.status_lbl.pack(side="right", padx=18)
        self.clock = tk.Label(header, text="", bg="#0a0f1d", fg=SOFT, font=(self.num, 12, "bold"))
        self.clock.pack(side="right", padx=8)

        body = tk.Frame(root, bg=BG)
        body.grid(row=1, column=0, sticky="nsew", padx=12, pady=10)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        side = tk.Frame(body, bg=PANEL, width=330, highlightthickness=1, highlightbackground=LINE)
        side.grid(row=0, column=0, sticky="ns", padx=(0, 12))
        side.pack_propagate(False)

        tk.Label(side, text="BOSHQARUV PANELI", bg=PANEL, fg=TXT,
                 font=(self.ui, 12, "bold"), anchor="w").pack(fill="x", padx=14, pady=(14, 0))

        sec = self._section(side, "J2534 ADAPTER")
        self.adapter_box = ttk.Combobox(sec, textvariable=self.selected_adapter, state="readonly",
                                        style="Dark.TCombobox", font=(self.ui, 9),
                                        values=["Scanmatik SM2 USB (J2534)", "OpenPort 2.0 J2534"])
        self.adapter_box.pack(fill="x")
        self.connect_btn = tk.Button(sec, text="⏻    ULANISH", command=self._on_connect,
                                     bg="#0369a1", fg="#ffffff", activebackground="#0284c7",
                                     activeforeground="#ffffff", relief="flat", bd=0, cursor="hand2",
                                     font=(self.ui, 10, "bold"), pady=9)
        self.connect_btn.pack(fill="x", pady=(8, 0))

        sec = self._section(side, "AVTOMOBIL")
        self.car_box = ttk.Combobox(sec, textvariable=self.selected_car, state="readonly",
                                    style="Dark.TCombobox", font=(self.ui, 9),
                                    values=["Cobalt MCM 2025-2026", "Cobalt MCM Standard"])
        self.car_box.pack(fill="x")

        sec = self._section(side, "VIN KOD")
        self.vin_entry = tk.Entry(sec, textvariable=self.vin_value, bg=CARD, fg=TXT,
                                  insertbackground=ACCENT, relief="flat", font=(self.num, 11, "bold"),
                                  highlightthickness=1, highlightbackground=LINE, highlightcolor=ACCENT)
        self.vin_entry.pack(fill="x", ipady=6)
        tk.Label(sec, text="17 xonali VIN raqami", bg=PANEL, fg=MUTED,
                 font=(self.ui, 8), anchor="w").pack(fill="x", pady=(3, 0))

        rec = tk.Frame(side, bg="#1a1308", highlightthickness=1, highlightbackground="#3d2c0b")
        rec.pack(fill="x", padx=14, pady=(12, 0))
        self.recovery_check = tk.Checkbutton(
            rec, text="  MCM Recovery Rejimi", variable=self.mcm_recovery_enabled,
            bg="#1a1308", fg=WARN, selectcolor="#1a1308", activebackground="#1a1308",
            activeforeground=WARN, font=(self.ui, 9, "bold"), anchor="w",
            bd=0, highlightthickness=0)
        self.recovery_check.pack(fill="x", padx=8, pady=7)

        sec = self._section(side, "ASOSIY AMALLAR")
        self.btns = {}
        for key, icon, title, sub, color, cmd in [
            ("vin", "⌕", "VIN / Pasport O'qish", "Avtomobil ma'lumotlarini o'qish", OK, self._on_read_vin),
            ("stock", "▤", "Stock Faylni Yuklash", "Zavod faylini tanlash", SOFT, self._on_stock_file),
            ("rec", "⟲", "MCM Recovery Bajarish", "Modulni qayta tiklash", ERR, self._on_mcm_recovery),
            ("ipc", "⇩", "IPC ga Yozish (Write IPC)", "Asboblar paneliga yozish", ACCENT, self._on_write_ipc),
            ("wake", "◉", "Tablo Uyg'otish", "Aloqani faollashtirish (TesterPresent)", OK, self._on_wake),
        ]:
            b = ActionButton(sec, icon, title, sub, color, cmd, self.ui)
            b.pack(fill="x", pady=3)
            self.btns[key] = b

        right = tk.Frame(body, bg=BG)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)

        tk.Label(right, text="RAQAMLI TABLO  —  CHEVROLET COBALT MCM", bg=BG, fg=SOFT,
                 font=(self.ui, 9, "bold"), anchor="w").grid(row=0, column=0, sticky="ew", pady=(0, 6))

        bezel = tk.Frame(right, bg="#000000", highlightthickness=2, highlightbackground="#1c2a46")
        bezel.grid(row=1, column=0, sticky="nsew")
        self.cluster = Cluster(bezel, family=self.num)
        self.cluster.pack(fill="both", expand=True, padx=2, pady=2)
        self.cluster_canvas = self.cluster

        strip = tk.Frame(right, bg=BG)
        strip.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self.tiles = {}
        for i, (key, name) in enumerate([("speed", "TEZLIK"), ("rpm", "AYLANISH"), ("gear", "UZATMA"),
                                         ("odo", "KILOMETRAJ"), ("coolant", "SUV HARORATI"),
                                         ("batt", "AKB")]):
            strip.grid_columnconfigure(i, weight=1, uniform="t")
            tile = tk.Frame(strip, bg=PANEL, highlightthickness=1, highlightbackground=LINE)
            tile.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 6, 0))
            tk.Label(tile, text=name, bg=PANEL, fg=MUTED, font=(self.ui, 8, "bold")).pack(pady=(6, 0))
            val = tk.Label(tile, text="—", bg=PANEL, fg=ACCENT, font=(self.num, 15, "bold"))
            val.pack(pady=(0, 6))
            self.tiles[key] = val

        logf = tk.Frame(right, bg="#070b14", highlightthickness=1, highlightbackground=LINE, height=150)
        logf.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        logf.pack_propagate(False)
        lh = tk.Frame(logf, bg="#070b14")
        lh.pack(fill="x", padx=10, pady=(6, 2))
        tk.Label(lh, text="■ DIAGNOSTIKA JURNALI (LOG)", bg="#070b14", fg=MUTED,
                 font=(self.ui, 8, "bold")).pack(side="left")
        clear = tk.Label(lh, text="TOZALASH", bg="#070b14", fg=SOFT, cursor="hand2",
                         font=(self.ui, 8, "bold"))
        clear.pack(side="right")
        clear.bind("<Button-1>", lambda e: self._clear_log())
        self.log_text = tk.Text(logf, height=5, bg="#04060a", fg=ACCENT, bd=0, relief="flat",
                                font=("Consolas", 9), state="disabled", highlightthickness=0,
                                padx=8, pady=4, wrap="word")
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        for tag, col in (("info", ACCENT), ("ok", OK), ("warn", WARN), ("err", ERR),
                         ("tx", VIOLET), ("time", MUTED)):
            self.log_text.tag_configure(tag, foreground=col)

        foot = tk.Frame(root, bg="#0a0f1d", height=26, highlightthickness=1, highlightbackground=LINE)
        foot.grid(row=2, column=0, sticky="ew")
        foot.pack_propagate(False)
        tk.Label(foot, textvariable=self.selected_adapter, bg="#0a0f1d", fg=MUTED,
                 font=(self.ui, 8)).pack(side="left", padx=14)
        tk.Label(foot, text="Cobalt MCM Tablo  •  ECU & MCM Configurator", bg="#0a0f1d", fg=MUTED,
                 font=(self.ui, 8)).pack(side="right", padx=14)
        tk.Label(foot, textvariable=self.progress_var, bg="#0a0f1d", fg=ACCENT,
                 font=(self.ui, 8, "bold")).pack(side="right", padx=14)

        self.update_cluster()

    def _in_main(self) -> bool:
        return threading.current_thread() is self._main_thread

    def run_ui(self, fn, *args, **kwargs):
        self._uiq.put((fn, args, kwargs))

    def _pump(self):
        try:
            while True:
                fn, a, k = self._uiq.get_nowait()
                try:
                    fn(*a, **k)
                except Exception:
                    logger.exception("GUI chaqiruvi xato berdi")
        except queue.Empty:
            pass
        try:
            self.root.after(40, self._pump)
        except tk.TclError:
            pass

    def update_cluster(self, speed=None, rpm=None, gear=None, odo=None, brake=None, lights=None, coolant=None):
        if not self._in_main():
            self.run_ui(self.update_cluster, speed, rpm, gear, odo, brake, lights, coolant)
            return
        c = self.cluster
        if speed is not None:
            c.speed = max(0.0, min(180.0, float(speed)))
        if rpm is not None:
            c.rpm = max(0.0, min(8.0, float(rpm)))
        if gear is not None:
            c.gear = str(gear)
        if odo is not None:
            c.odo = int(odo)
        if brake is not None:
            c.brake = bool(brake)
        if lights is not None:
            c.lights = bool(lights)
        c.redraw()
        self.tiles["speed"].configure(text=f"{int(c.speed)} km/h")
        self.tiles["rpm"].configure(text=f"{int(c.rpm * 1000)}")
        self.tiles["gear"].configure(text=c.gear)
        self.tiles["odo"].configure(text=f"{c.odo} km")
        self.tiles["batt"].configure(text="12.6 V" if self._connected else "— V")
        if coolant is not None:
            self.tiles["coolant"].configure(text=f"{int(coolant)} °C")

    def redraw(self):
        self.cluster.redraw()

    def _draw_cluster(self, event=None):
        self.redraw()

    def sweep(self, duration_ms=1700):
        t0 = time.time()

        def step():
            p = (time.time() - t0) * 1000.0 / duration_ms
            if p >= 1:
                self.update_cluster(speed=0, rpm=0)
                return
            k = math.sin(p * math.pi)
            self.update_cluster(speed=180 * k, rpm=8 * k)
            self.root.after(24, step)

        step()

    def _tick_clock(self):
        try:
            self.clock.configure(text=time.strftime("%H:%M:%S"))
            self.root.after(1000, self._tick_clock)
        except tk.TclError:
            pass

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def log(self, message: str, level: str = "info"):
        if not self._in_main():
            self.run_ui(self.log, message, level)
            return
        tag = level if level in ("info", "ok", "warn", "err", "tx") else "info"
        label = {"info": "INFO", "ok": " OK ", "warn": "WARN", "err": "XATO", "tx": " TX "}[tag]
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{time.strftime('%H:%M:%S')}] ", "time")
        self.log_text.insert("end", f"[{label}] {message}\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def set_progress(self, percent: float, text: Optional[str] = None):
        if not self._in_main():
            self.run_ui(self.set_progress, percent, text)
            return
        if percent is None or percent >= 100:
            self.progress_var.set("")
        else:
            self.progress_var.set(f"{text or 'Jarayon'}: {float(percent):.0f}%")

    def set_connected(self, state: bool):
        if not self._in_main():
            self.run_ui(self.set_connected, state)
            return
        self._connected = bool(state)
        if state:
            self.status_lbl.configure(text="● ULANGAN", text_color=OK, bg="#0b1a12")
            self.status_lbl.configure(highlightbackground="#14532d")
            self.connect_btn.configure(text="⏻    UZISH", bg="#b91c1c", activebackground="#dc2626")
        else:
            self.status_lbl.configure(text="● ALOQA YO'Q", text_color=ERR, bg="#140c12")
            self.status_lbl.configure(highlightbackground="#3b1219")
            self.connect_btn.configure(text="⏻    ULANISH", bg="#0369a1", activebackground="#0284c7")
        self.update_cluster()

    def _set_busy(self, busy: bool):
        self._busy = busy
        for b in self.btns.values():
            b.set_enabled(not busy)
        self.connect_btn.configure(state="disabled" if busy else "normal")
        if not busy:
            self.progress_var.set("")

    def _resolve(self, *names):
        for n in names:
            cb = self.callbacks.get(n)
            if callable(cb):
                return "callback", cb
        if self.backend is not None:
            for n in names:
                fn = getattr(self.backend, n, None)
                if callable(fn):
                    return "backend", fn
        return None, None

    def _context(self, **extra):
        ctx = dict(app=self,
                   adapter=self.selected_adapter.get(),
                   car=self.selected_car.get(),
                   vin=(self.vin_value.get() or "").strip(),
                   stock_file=self.stock_path or None,
                   log=self.log,
                   progress=self.set_progress)
        ctx.update(extra)
        return ctx

    def _invoke(self, fn, ctx):
        try:
            params = inspect.signature(fn).parameters
        except (TypeError, ValueError):
            return fn()
        if any(p.kind == p.VAR_KEYWORD for p in params.values()):
            return fn(**ctx)
        return fn(**{k: v for k, v in ctx.items() if k in params})

    def _legacy(self, cb):
        try:
            cb(self)
        except Exception as e:
            logger.exception("Callback xatosi")
            self.log(f"Callback xatosi: {e}", "err")

    def _run_task(self, title, fn, on_done=None, **extra):
        if self._busy:
            self.log("Boshqa amal bajarilmoqda, kuting...", "warn")
            return
        self._set_busy(True)
        ctx = self._context(**extra)  # Tk o'zgaruvchilarini faqat asosiy oqimda o'qiymiz

        def worker():
            res, err = None, None
            try:
                res = self._invoke(fn, ctx)
            except Exception as e:
                logger.exception("%s xatosi", title)
                err = e
            self.run_ui(self._finish_task, title, res, err, on_done)

        threading.Thread(target=worker, daemon=True, name=f"task-{title}").start()

    def _finish_task(self, title, res, err, on_done):
        self._set_busy(False)
        if err is not None:
            self.log(f"{title}: xato — {err}", "err")
            return
        if on_done:
            try:
                on_done(res)
            except Exception as e:
                logger.exception("%s yakunlashda xato", title)
                self.log(f"{title}: natijani qayta ishlashda xato — {e}", "err")

    def _need_connection(self) -> bool:
        if self._connected:
            return True
        self.log("Avval adapterga ulaning (ULANISH tugmasi).", "warn")
        return False

    def _start_live(self):
        fn = getattr(self.backend, "live_data", None) if self.backend is not None else None
        if not callable(fn) or (self._live_thread and self._live_thread.is_alive()):
            return
        self._live_stop.clear()

        def worker():
            while not self._live_stop.is_set():
                try:
                    data = fn()
                except Exception:
                    data = None
                if isinstance(data, dict):
                    allowed = ("speed", "rpm", "gear", "odo", "brake", "lights", "coolant")
                    self.run_ui(self.update_cluster, **{k: v for k, v in data.items() if k in allowed})
                self._live_stop.wait(0.3)

        self._live_thread = threading.Thread(target=worker, daemon=True, name="live-data")
        self._live_thread.start()

    def _stop_live(self):
        self._live_stop.set()

    def _on_connect(self):
        kind, fn = self._resolve("connect")
        if kind == "callback":
            self._legacy(fn)
            return
        if self._busy:
            self.log("Boshqa amal bajarilmoqda, kuting...", "warn")
            return
        if self._connected:
            self._do_disconnect()
            return
        if kind == "backend":
            self.log(f"{self.selected_adapter.get()} ga ulanilmoqda...", "tx")
            self._run_task("Ulanish", fn, on_done=self._after_connect)
            return
        self.set_connected(True)
        self.log("J2534 adapteriga ulandi (DEMO).", "ok")
        self.sweep()

    def _after_connect(self, res):
        if res is False:
            self.log("Ulanish muvaffaqiyatsiz tugadi.", "err")
            return
        self.set_connected(True)
        self.log("J2534 adapteriga ulandi.", "ok")
        self.sweep()
        self._start_live()

    def _do_disconnect(self):
        self._stop_live()
        kind, fn = self._resolve("disconnect")
        if kind == "callback":
            self._legacy(fn)
            return
        if kind == "backend":
            self._run_task("Uzish", fn, on_done=lambda _r: self._after_disconnect())
            return
        self._after_disconnect()

    def _after_disconnect(self):
        self.set_connected(False)
        self.log("Aloqa uzildi.", "warn")

    def _on_read_vin(self):
        kind, fn = self._resolve("read_vin")
        if kind == "callback":
            self._legacy(fn)
            return
        if kind == "backend":
            if not self._need_connection():
                return
            self.log("VIN o'qish so'rovi yuborildi...", "tx")
            self._run_task("VIN o'qish", fn, on_done=self._after_read_vin)
            return
        self.log("VIN o'qish so'rovi yuborildi (DEMO).", "tx")
        self.vin_value.set("3G1234567890ABCDE")

    def _on_wake(self):
        kind, fn = self._resolve("wake", "tester_present")
        if kind == "callback":
            self._legacy(fn)
            return
        if kind == "backend":
            if not self._need_connection():
                return
            self.log("Tablo uyg'otish so'rovi yuborildi...", "tx")
            self._run_task("Tablo uyg'otish", fn, on_done=self._after_wake)
            return
        self.log("Tablo uyg'otish so'rovi yuborildi (DEMO).", "tx")

    def _after_wake(self, res):
        ok = bool(res[0]) if isinstance(res, tuple) else bool(res)
        self.log("Tablo javob berdi." if ok else "Tablo javob bermadi.", "ok" if ok else "warn")

    def _after_read_vin(self, res):
        vin = str(res or "").strip().upper()
        if not vin:
            self.log("VIN o'qilmadi (bo'sh javob).", "err")
            return
        self.vin_value.set(vin)
        if len(vin) == 17:
            self.log(f"VIN: {vin}", "ok")
        else:
            self.log(f"VIN o'qildi, lekin uzunligi {len(vin)} (17 bo'lishi kerak): {vin}", "warn")

    def _on_stock_file(self):
        kind, fn = self._resolve("stock_file", "load_stock")
        if kind == "callback":
            self._legacy(fn)
            return
        path = filedialog.askopenfilename(
            title="Stock (zavod) faylni tanlang",
            filetypes=[("Firmware", "*.bin *.hex *.s19 *.srec *.rom"), ("Barcha fayllar", "*.*")])
        if not path:
            self.log("Stock fayl tanlanmadi.", "warn")
            return
        self.stock_path = path
        self.log(f"Stock fayl tanlandi: {path}", "info")
        if kind == "backend":
            self._run_task("Stock fayl", fn,
                           on_done=lambda _r: self.log("Stock fayl yuklandi.", "ok"))

    def _on_mcm_recovery(self):
        if not self.mcm_recovery_enabled.get():
            messagebox.showwarning("Ogohlantirish",
                                   "Avval 'MCM Recovery Rejimi' katakchasini belgilang!")
            return
        if not messagebox.askyesno("Tasdiqlash",
                                   "MCM Recovery jarayoni modulga yoziladi.\nDavom etasizmi?"):
            self.log("MCM Recovery bekor qilindi.", "warn")
            return
        kind, fn = self._resolve("mcm_recovery")
        if kind == "callback":
            self._legacy(fn)
            return
        if kind == "backend":
            if not self._need_connection():
                return
            if not self.stock_path:
                self.log("Diqqat: stock fayl tanlanmagan.", "warn")
            self.log("MCM Recovery jarayoni boshlandi...", "warn")
            self._run_task("MCM Recovery", fn,
                           on_done=lambda _r: self.log("MCM Recovery yakunlandi.", "ok"))
            return
        self.log("MCM Recovery jarayoni boshlandi (DEMO).", "warn")

    def _on_write_ipc(self):
        kind, fn = self._resolve("write_ipc")
        if kind == "callback":
            self._legacy(fn)
            return
        if kind == "backend":
            if not self._need_connection():
                return
            if not messagebox.askyesno("Tasdiqlash",
                                       "IPC (asboblar paneli) ga ma'lumot yoziladi.\nDavom etasizmi?"):
                self.log("IPC ga yozish bekor qilindi.", "warn")
                return
            self.log("IPC ga ma'lumotlar yozish boshlandi...", "tx")
            self._run_task("IPC yozish", fn,
                           on_done=lambda _r: self.log("IPC ga yozish yakunlandi.", "ok"))
            return
        self.log("IPC ga ma'lumotlar yozish boshlandi (DEMO).", "tx")

    def _on_close(self):
        self._stop_live()
        if self._connected:
            fn = getattr(self.backend, "disconnect", None) if self.backend is not None else None
            if callable(fn):
                try:
                    self._invoke(fn, self._context())
                except Exception:
                    logger.exception("Yopishda disconnect xatosi")
        self.root.destroy()

    def mainloop(self):
        self.root.mainloop()

    def run(self):
        self.mainloop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app = MCMCobaltApp()
    app.run()