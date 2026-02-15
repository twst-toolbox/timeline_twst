import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import cv2
import numpy as np
import srt
import datetime
import threading
import os
import traceback
from PIL import Image, ImageTk

class TwstApp:
    def __init__(self, root):
        self.root = root
        self.root.title("TWST 字幕提取器 V8.1 (防崩溃修复版)")
        self.root.geometry("1200x850")
        
        # TWST 默认参数
        self.rect_d = [320, 465, 630, 100] 
        self.rect_c = [430, 170, 450, 90]  
        self.rect_b = [100, 100, 150, 150] 
        
        self.diff_threshold = 3.0
        
        self.video_path = ""
        self.cap = None
        self.total_frames = 0
        self.fps = 30
        self.is_processing = False
        
        self._init_ui()
        
    def _init_ui(self):
        # 1. 顶部
        frame_top = tk.Frame(self.root, pady=5)
        frame_top.pack(side=tk.TOP, fill=tk.X)
        tk.Button(frame_top, text="📂 加载视频", command=self.load_video, font=("Arial", 12)).pack(side=tk.LEFT, padx=10)
        self.lbl_status = tk.Label(frame_top, text="准备就绪", fg="gray")
        self.lbl_status.pack(side=tk.LEFT)
        self.btn_start = tk.Button(frame_top, text="▶️ 开始提取", command=self.start_thread, bg="#ddffdd", font=("Arial", 12, "bold"))
        self.btn_start.pack(side=tk.RIGHT, padx=10)

        # 2. 中间预览
        frame_main = tk.Frame(self.root)
        frame_main.pack(fill=tk.BOTH, expand=True, padx=10)
        
        self.canvas_frame = tk.Frame(frame_main, bg="black")
        self.canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(self.canvas_frame, bg="#222")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # 右侧控制面板
        frame_ctrl = tk.Frame(frame_main, width=320)
        frame_ctrl.pack(side=tk.RIGHT, fill=tk.Y, padx=10)
        
        # 3. 灵敏度控制
        lf_diff = tk.LabelFrame(frame_ctrl, text="⚡️ 切分灵敏度 (突变检测)", padx=5, pady=5)
        lf_diff.pack(fill=tk.X, pady=10)
        tk.Label(lf_diff, text="防连读专用：数值越小越敏感", fg="gray", font=("Arial", 8)).pack()
        self.scale_diff = tk.Scale(lf_diff, from_=0.5, to=10.0, resolution=0.1, orient=tk.HORIZONTAL, command=self.on_diff_change)
        self.scale_diff.set(self.diff_threshold)
        self.scale_diff.pack(fill=tk.X)
        self.lbl_diff_val = tk.Label(lf_diff, text=f"当前: {self.diff_threshold}%")
        self.lbl_diff_val.pack()

        # 4. 区域调整 (Tab页)
        self.notebook = ttk.Notebook(frame_ctrl)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=10)
        
        self.create_control_tab("🟢 对话框", self.rect_d, 0)
        self.create_control_tab("🔵 选项框", self.rect_c, 1)
        self.create_control_tab("🔴 背景参考", self.rect_b, 2)

        # 5. 底部
        frame_bottom = tk.Frame(self.root, pady=5)
        frame_bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=10)
        self.scale_time = tk.Scale(frame_bottom, from_=0, to=100, orient=tk.HORIZONTAL, command=self.on_time_change, showvalue=0)
        self.scale_time.pack(fill=tk.X)
        frame_info = tk.Frame(frame_bottom)
        frame_info.pack(fill=tk.X)
        self.lbl_time_val = tk.Label(frame_info, text="00:00")
        self.lbl_time_val.pack(side=tk.LEFT)
        self.progress = ttk.Progressbar(frame_info, orient=tk.HORIZONTAL, mode='determinate')
        self.progress.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=5)

    def create_control_tab(self, title, rect_var, tab_id):
        frame = tk.Frame(self.notebook)
        self.notebook.add(frame, text=title)
        labels = ["X", "Y", "W", "H"]
        self.sliders = getattr(self, "sliders", {})
        if tab_id not in self.sliders: self.sliders[tab_id] = []
        
        for i in range(4):
            tk.Label(frame, text=labels[i], anchor="w").pack(fill=tk.X)
            scale = tk.Scale(frame, from_=0, to=2000, orient=tk.HORIZONTAL, resolution=1)
            scale.set(rect_var[i])
            scale.pack(fill=tk.X)
            scale.config(command=lambda v, idx=i, rid=tab_id: self.on_rect_change(v, idx, rid))
            self.sliders[tab_id].append(scale)

    def on_rect_change(self, val, idx, tab_id):
        val = int(float(val))
        if tab_id == 0: self.rect_d[idx] = val
        elif tab_id == 1: self.rect_c[idx] = val
        elif tab_id == 2: self.rect_b[idx] = val
        self.update_preview()

    def on_diff_change(self, val):
        self.diff_threshold = float(val)
        self.lbl_diff_val.config(text=f"当前: {self.diff_threshold}%")

    def load_video(self):
        path = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mkv *.avi")])
        if not path: return
        self.video_path = path
        self.cap = cv2.VideoCapture(path)
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        self.scale_time.config(to=self.total_frames)
        self.lbl_status.config(text=f"已加载: {os.path.basename(path)}")
        
        for tab_id in self.sliders:
            for s in self.sliders[tab_id]: s.config(to=max(w, h))
        self.update_preview()

    def on_time_change(self, val):
        if not self.cap: return
        self.lbl_time_val.config(text=str(datetime.timedelta(seconds=int(int(val)/self.fps))))
        self.update_preview()

    def update_preview(self):
        if not self.cap or self.is_processing: return
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, int(self.scale_time.get()))
        ret, frame = self.cap.read()
        if ret:
            x, y, w, h = self.rect_d
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
            x, y, w, h = self.rect_c
            cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 255, 0), 2)
            x, y, w, h = self.rect_b
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 0, 255), 2)
            
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame)
            cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
            if cw > 1: img.thumbnail((cw, ch))
            self.photo = ImageTk.PhotoImage(img)
            self.canvas.create_image(cw//2, ch//2, image=self.photo, anchor=tk.CENTER)

    def start_thread(self):
        if not self.video_path: return
        self.is_processing = True
        self.btn_start.config(state=tk.DISABLED, text="提取中...")
        threading.Thread(target=self.run_logic, daemon=True).start()

    def run_logic(self):
        try:
            # === 【修复点 1】参数快照 ===
            # 在开始瞬间把参数复制一份，防止用户中途拖动滑块导致崩溃
            use_rect_d = list(self.rect_d)
            use_rect_c = list(self.rect_c)
            use_rect_b = list(self.rect_b)
            use_diff_thresh = self.diff_threshold
            
            out_srt = os.path.splitext(self.video_path)[0] + ".srt"
            cap = cv2.VideoCapture(self.video_path)
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            subs = []
            
            if total == 0: raise Exception("无法读取视频总帧数，可能文件已损坏")
            
            LOWER_COLOR = np.array([0, 0, 130]) 
            UPPER_COLOR = np.array([180, 100, 255])
            kernel = np.ones((3,3), np.uint8)
            
            d_speaking = False
            d_start = 0
            d_peak = 0.0
            c_active = False
            c_start = 0
            sub_index = 1
            
            last_dilated_d = None
            diff_limit = use_diff_thresh / 100.0
            
            idx = 0
            while True:
                ret, frame = cap.read()
                if not ret: break
                
                if idx % 100 == 0:
                    self.root.after(0, lambda v=(idx/total)*100: self.progress.config(value=v))
                
                hsv_full = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                
                # --- 区域分析 (使用快照参数) ---
                xd, yd, wd, hd = use_rect_d
                # 【修复点 2】安全除法，防止宽度高度为0
                if wd == 0 or hd == 0: 
                    idx += 1
                    continue
                    
                roi_d_hsv = hsv_full[yd:yd+hd, xd:xd+wd]
                ratio_d = cv2.countNonZero(cv2.inRange(roi_d_hsv, LOWER_COLOR, UPPER_COLOR)) / (wd * hd)
                
                xc, yc, wc, hc = use_rect_c
                if wc > 0 and hc > 0:
                    roi_c_hsv = hsv_full[yc:yc+hc, xc:xc+wc]
                    ratio_c = cv2.countNonZero(cv2.inRange(roi_c_hsv, LOWER_COLOR, UPPER_COLOR)) / (wc * hc)
                else:
                    ratio_c = 0
                
                xb, yb, wb, hb = use_rect_b
                if wb > 0 and hb > 0:
                    roi_b_hsv = hsv_full[yb:yb+hb, xb:xb+wb]
                    ratio_b = cv2.countNonZero(cv2.inRange(roi_b_hsv, LOWER_COLOR, UPPER_COLOR)) / (wb * hb)
                else:
                    ratio_b = 0
                
                # --- 对话逻辑 ---
                density_d = 0.0
                diff_score = 0.0
                
                if ratio_d > 0.4:
                    roi_gray = cv2.cvtColor(frame[yd:yd+hd, xd:xd+wd], cv2.COLOR_BGR2GRAY)
                    _, bin_d = cv2.threshold(roi_gray, 150, 255, cv2.THRESH_BINARY_INV)
                    dil_d = cv2.dilate(bin_d, kernel, iterations=1)
                    density_d = cv2.countNonZero(dil_d) / (wd * hd)
                    
                    if last_dilated_d is not None:
                        diff_img = cv2.absdiff(dil_d, last_dilated_d)
                        diff_score = cv2.countNonZero(diff_img) / (wd * hd)
                    last_dilated_d = dil_d.copy()
                else:
                    last_dilated_d = None
                
                if not d_speaking:
                    if density_d > 0.005:
                        d_speaking = True
                        d_start = idx
                        d_peak = density_d
                else:
                    if density_d > d_peak: d_peak = density_d
                    
                    should_cut = False
                    
                    if density_d < 0.003: should_cut = True
                    elif density_d < (d_peak * 0.4) and d_peak > 0.02: should_cut = True
                    # 突变检测 (使用快照的阈值)
                    elif diff_score > diff_limit and (idx - d_start)/self.fps > 0.2: should_cut = True
                    
                    if should_cut:
                        dur = (idx - d_start) / self.fps
                        if dur > 0.2:
                            st = datetime.timedelta(seconds=d_start/self.fps)
                            et = datetime.timedelta(seconds=idx/self.fps)
                            subs.append(srt.Subtitle(index=sub_index, start=st, end=et, content=f"Line {sub_index}"))
                            sub_index += 1
                        
                        if density_d > 0.005:
                            d_speaking = True
                            d_start = idx
                            d_peak = density_d
                        else:
                            d_speaking =
