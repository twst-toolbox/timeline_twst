import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import cv2
import numpy as np
import srt
import datetime
import threading
import os
from PIL import Image, ImageTk

class TwstApp:
    def __init__(self, root):
        self.root = root
        self.root.title("TWST 字幕提取器 V8 (防连读增强版)")
        self.root.geometry("1200x850")
        
        # TWST 默认参数 (1080P/720P通用预估)
        self.rect_d = [320, 465, 630, 100] # 绿: 对话
        self.rect_c = [430, 170, 450, 90]  # 蓝: 选项
        self.rect_b = [100, 100, 150, 150] # 红: 背景参考
        
        # 核心阈值
        self.diff_threshold = 3.0 # 默认灵敏度 3.0% (越小越敏感)
        
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
        tk.Button(frame_top, text="▶️ 开始提取", command=self.start_thread, bg="#ddffdd", font=("Arial", 12, "bold")).pack(side=tk.RIGHT, padx=10)

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
        
        # 3. 灵敏度控制 (V8 新增)
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
        
        # 更新滑块最大值
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
        threading.Thread(target=self.run_logic, daemon=True).start()

    def run_logic(self):
        out_srt = os.path.splitext(self.video_path)[0] + ".srt"
        cap = cv2.VideoCapture(self.video_path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        subs = []
        
        # TWST 米白色定义
        LOWER_COLOR = np.array([0, 0, 130]) 
        UPPER_COLOR = np.array([180, 100, 255])
        kernel = np.ones((3,3), np.uint8)
        
        # 状态变量
        d_speaking = False
        d_start = 0
        d_peak = 0.0
        c_active = False
        c_start = 0
        sub_index = 1
        
        # 记录上一帧的文字形状 (用于突变检测)
        last_dilated_d = None
        diff_limit = self.diff_threshold / 100.0
        
        idx = 0
        while True:
            ret, frame = cap.read()
            if not ret: break
            
            if idx % 100 == 0:
                self.root.after(0, lambda v=(idx/total)*100: self.progress.config(value=v))
            
            hsv_full = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            
            # --- 区域分析 ---
            # 绿框 (对话)
            xd, yd, wd, hd = self.rect_d
            roi_d_hsv = hsv_full[yd:yd+hd, xd:xd+wd]
            ratio_d = cv2.countNonZero(cv2.inRange(roi_d_hsv, LOWER_COLOR, UPPER_COLOR)) / (wd * hd)
            
            # 蓝框 (选项)
            xc, yc, wc, hc = self.rect_c
            roi_c_hsv = hsv_full[yc:yc+hc, xc:xc+wc]
            ratio_c = cv2.countNonZero(cv2.inRange(roi_c_hsv, LOWER_COLOR, UPPER_COLOR)) / (wc * hc)
            
            # 红框 (背景)
            xb, yb, wb, hb = self.rect_b
            roi_b_hsv = hsv_full[yb:yb+hb, xb:xb+wb]
            ratio_b = cv2.countNonZero(cv2.inRange(roi_b_hsv, LOWER_COLOR, UPPER_COLOR)) / (wb * hb)
            
            # --- 对话逻辑 (V8 增强版) ---
            density_d = 0.0
            diff_score = 0.0
            
            # 只有当绿框是米白色时才检测文字
            if ratio_d > 0.4:
                roi_gray = cv2.cvtColor(frame[yd:yd+hd, xd:xd+wd], cv2.COLOR_BGR2GRAY)
                # 找黑字
                _, bin_d = cv2.threshold(roi_gray, 150, 255, cv2.THRESH_BINARY_INV)
                dil_d = cv2.dilate(bin_d, kernel, iterations=1)
                density_d = cv2.countNonZero(dil_d) / (wd * hd)
                
                # 计算形状突变
                if last_dilated_d is not None:
                    diff_img = cv2.absdiff(dil_d, last_dilated_d)
                    diff_score = cv2.countNonZero(diff_img) / (wd * hd)
                last_dilated_d = dil_d.copy()
            else:
                last_dilated_d = None # 对话框消失，重置历史
            
            if not d_speaking:
                if density_d > 0.005:
                    d_speaking = True
                    d_start = idx
                    d_peak = density_d
            else:
                if density_d > d_peak: d_peak = density_d
                
                should_cut = False
                cut_reason = ""
                
                # 条件1: 没字了
                if density_d < 0.003: 
                    should_cut = True
                    cut_reason = "empty"
                # 条件2: 字突然变少 (峰值回落)
                elif density_d < (d_peak * 0.4) and d_peak > 0.02: 
                    should_cut = True
                    cut_reason = "drop"
                # 条件3: 字的形状突变 (V8核心: 防连读)
                # 只有当这句话持续了一会儿(>0.2s)才检测，防止打字过程中的误判
                elif diff_score > diff_limit and (idx - d_start)/self.fps > 0.2:
                    should_cut = True
                    cut_reason = "diff"
                
                if should_cut:
                    dur = (idx - d_start) / self.fps
                    if dur > 0.2: # 过滤杂讯
                        st = datetime.timedelta(seconds=d_start/self.fps)
                        et = datetime.timedelta(seconds=idx/self.fps)
                        subs.append(srt.Subtitle(index=sub_index, start=st, end=et, content=f"Line {sub_index}"))
                        sub_index += 1
                    
                    if density_d > 0.005: # 如果还有字，说明是连读，立刻开始下一句
                        d_speaking = True
                        d_start = idx
                        d_peak = density_d
                    else:
                        d_speaking = False
                        d_peak = 0.0

            # --- 选项逻辑 (V7逻辑: 必须对比背景) ---
            is_choice = (ratio_c > 0.6) and (ratio_c > ratio_b + 0.3)
            if not c_active:
                if is_choice:
                    c_active = True
                    c_start = idx
            else:
                if not is_choice:
                    c_active = False
                    if (idx - c_start) / self.fps > 0.5:
                        st = datetime.timedelta(seconds=c_start/self.fps)
                        et = datetime.timedelta(seconds=idx/self.fps)
                        subs.append(srt.Subtitle(index=sub_index, start=st, end=et, content=f"[Choice] Line {sub_index}"))
                        sub_index += 1
            
            idx += 1
            
        cap.release()
        subs.sort(key=lambda x: x.start)
        for i, sub in enumerate(subs): sub.index = i + 1
        
        with open(out_srt, "w", encoding="utf-8") as f: f.write(srt.compose(subs))
        
        self.is_processing = False
        self.root.after(0, lambda: messagebox.showinfo("完成", f"字幕已生成:\n{out_srt}"))

if __name__ == "__main__":
    root = tk.Tk()
    app = TwstApp(root)
    root.mainloop()
