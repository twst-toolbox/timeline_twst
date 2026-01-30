import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import cv2
import numpy as np
import srt
import datetime
import threading
import os
from PIL import Image, ImageTk # 需要安装 pip install pillow

class SubtitleApp:
    def __init__(self, root):
        self.root = root
        self.root.title("TWST 字幕提取器 V8 (本地版)")
        self.root.geometry("1000x750")
        
        # 核心参数 (默认值)
        self.rect_d = [320, 465, 630, 100] # 绿框
        self.rect_c = [430, 170, 450, 90]  # 蓝框
        self.rect_b = [100, 100, 150, 150] # 红框
        
        self.video_path = ""
        self.cap = None
        self.total_frames = 0
        self.fps = 30
        self.is_processing = False
        
        self._init_ui()
        
    def _init_ui(self):
        # 1. 顶部控制区
        frame_top = tk.Frame(self.root, pady=5)
        frame_top.pack(side=tk.TOP, fill=tk.X)
        
        tk.Button(frame_top, text="📂 选择视频", command=self.load_video, font=("Arial", 12)).pack(side=tk.LEFT, padx=10)
        self.lbl_status = tk.Label(frame_top, text="请先加载视频", fg="gray")
        self.lbl_status.pack(side=tk.LEFT)
        
        tk.Button(frame_top, text="▶️ 开始提取字幕", command=self.start_thread, bg="#ddffdd", font=("Arial", 12, "bold")).pack(side=tk.RIGHT, padx=10)

        # 2. 中间预览区
        self.canvas_frame = tk.Frame(self.root, bg="black")
        self.canvas_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.canvas = tk.Canvas(self.canvas_frame, bg="#222")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # 3. 时间轴滑块
        frame_time = tk.Frame(self.root)
        frame_time.pack(fill=tk.X, padx=10, pady=5)
        tk.Label(frame_time, text="时间预览:").pack(side=tk.LEFT)
        self.scale_time = tk.Scale(frame_time, from_=0, to=100, orient=tk.HORIZONTAL, command=self.on_time_change, showvalue=0)
        self.scale_time.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.lbl_time_val = tk.Label(frame_time, text="00:00")
        self.lbl_time_val.pack(side=tk.RIGHT)

        # 4. 底部参数调整区 (使用 Notebook 分页)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.X, padx=10, pady=10)
        
        self.create_control_tab("🟢 对话框 (绿)", self.rect_d, 0)
        self.create_control_tab("🔵 选项框 (蓝)", self.rect_c, 1)
        self.create_control_tab("🔴 背景参考 (红)", self.rect_b, 2)
        
        # 5. 进度条
        self.progress = ttk.Progressbar(self.root, orient=tk.HORIZONTAL, length=100, mode='determinate')
        self.progress.pack(fill=tk.X, padx=10, pady=5)

    def create_control_tab(self, title, rect_var, tab_id):
        frame = tk.Frame(self.notebook)
        self.notebook.add(frame, text=title)
        
        # X, Y, W, H 滑块
        labels = ["X (左边距)", "Y (上边距)", "W (宽度)", "H (高度)"]
        ranges = [1280, 720, 1280, 720] # 假设最大值，加载视频后会更新
        
        self.sliders = getattr(self, "sliders", {})
        if tab_id not in self.sliders: self.sliders[tab_id] = []
        
        for i in range(4):
            row = tk.Frame(frame)
            row.pack(fill=tk.X, padx=5, pady=2)
            tk.Label(row, text=labels[i], width=10).pack(side=tk.LEFT)
            scale = tk.Scale(row, from_=0, to=ranges[i], orient=tk.HORIZONTAL, resolution=1)
            scale.set(rect_var[i])
            scale.pack(side=tk.LEFT, fill=tk.X, expand=True)
            # 绑定事件：滑块变动 -> 更新 rect_var -> 刷新画面
            scale.config(command=lambda v, idx=i, rid=tab_id: self.on_rect_change(v, idx, rid))
            self.sliders[tab_id].append(scale)

    def on_rect_change(self, val, idx, tab_id):
        # 更新对应的坐标数组
        val = int(float(val))
        if tab_id == 0: self.rect_d[idx] = val
        elif tab_id == 1: self.rect_c[idx] = val
        elif tab_id == 2: self.rect_b[idx] = val
        self.update_preview()

    def load_video(self):
        path = filedialog.askopenfilename(filetypes=[("Video files", "*.mp4 *.mkv *.avi")])
        if not path: return
        
        self.video_path = path
        self.cap = cv2.VideoCapture(path)
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        self.scale_time.config(to=self.total_frames)
        self.lbl_status.config(text=f"已加载: {os.path.basename(path)} ({width}x{height})")
        
        # 更新滑块最大值
        for tab_id in self.sliders:
            self.sliders[tab_id][0].config(to=width)
            self.sliders[tab_id][1].config(to=height)
            self.sliders[tab_id][2].config(to=width)
            self.sliders[tab_id][3].config(to=height)
            
        self.update_preview()

    def on_time_change(self, val):
        if not self.cap: return
        frame_idx = int(val)
        seconds = frame_idx / self.fps
        self.lbl_time_val.config(text=str(datetime.timedelta(seconds=int(seconds))))
        self.update_preview()

    def update_preview(self):
        if not self.cap or self.is_processing: return
        
        # 获取当前滑块位置的帧
        frame_idx = int(self.scale_time.get())
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = self.cap.read()
        
        if ret:
            # 画框
            # 绿框 (对话)
            x, y, w, h = self.rect_d
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
            # 蓝框 (选项)
            x, y, w, h = self.rect_c
            cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 255, 0), 2)
            # 红框 (背景)
            x, y, w, h = self.rect_b
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 0, 255), 2)
            
            # 转换颜色 BGR -> RGB
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame)
            
            # 缩放以适应窗口
            canvas_w = self.canvas.winfo_width()
            canvas_h = self.canvas.winfo_height()
            if canvas_w > 1 and canvas_h > 1:
                img.thumbnail((canvas_w, canvas_h))
                
            self.photo = ImageTk.PhotoImage(img)
            self.canvas.create_image(canvas_w//2, canvas_h//2, image=self.photo, anchor=tk.CENTER)

    def start_thread(self):
        if not self.video_path: return
        self.is_processing = True
        threading.Thread(target=self.run_extraction, daemon=True).start()

    def run_extraction(self):
        # === V7 核心逻辑 ===
        output_srt = os.path.splitext(self.video_path)[0] + ".srt"
        self.lbl_status.config(text="正在提取中... 请勿关闭")
        
        cap = cv2.VideoCapture(self.video_path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        subs = []
        
        LOWER_COLOR = np.array([0, 0, 130]) 
        UPPER_COLOR = np.array([180, 100, 255])
        kernel = np.ones((3,3), np.uint8)
        
        d_speaking = False
        d_start = 0
        d_peak = 0.0
        c_active = False
        c_start = 0
        sub_index = 1
        
        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret: break
            
            # 更新进度条 (每100帧更新一次UI，防止卡顿)
            if frame_idx % 100 == 0:
                progress = (frame_idx / total) * 100
                self.root.after(0, lambda p=progress: self.progress.config(value=p))
            
            hsv_full = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            
            # 1. 区域分析
            xd, yd, wd, hd = self.rect_d
            roi_d_hsv = hsv_full[yd:yd+hd, xd:xd+wd]
            ratio_d = cv2.countNonZero(cv2.inRange(roi_d_hsv, LOWER_COLOR, UPPER_COLOR)) / (wd * hd)
            
            xc, yc, wc, hc = self.rect_c
            roi_c_hsv = hsv_full[yc:yc+hc, xc:xc+wc]
            ratio_c = cv2.countNonZero(cv2.inRange(roi_c_hsv, LOWER_COLOR, UPPER_COLOR)) / (wc * hc)
            
            xb, yb, wb, hb = self.rect_b
            roi_b_hsv = hsv_full[yb:yb+hb, xb:xb+wb]
            ratio_b = cv2.countNonZero(cv2.inRange(roi_b_hsv, LOWER_COLOR, UPPER_COLOR)) / (wb * hb)
            
            # 2. 对话逻辑 (V7)
            density_d = 0.0
            if ratio_d > 0.4:
                roi_gray = cv2.cvtColor(frame[yd:yd+hd, xd:xd+wd], cv2.COLOR_BGR2GRAY)
                _, bin_d = cv2.threshold(roi_gray, 150, 255, cv2.THRESH_BINARY_INV)
                dil_d = cv2.dilate(bin_d, kernel, iterations=1)
                density_d = cv2.countNonZero(dil_d) / (wd * hd)
            
            if not d_speaking:
                if density_d > 0.005:
                    d_speaking = True
                    d_start = frame_idx
                    d_peak = density_d
            else:
                if density_d > d_peak: d_peak = density_d
                should_cut = False
                if density_d < 0.003: should_cut = True
                elif density_d < (d_peak * 0.4) and d_peak > 0.02: should_cut = True
                
                if should_cut:
                    if (frame_idx - d_start) / fps > 0.2:
                        st = datetime.timedelta(seconds=d_start/fps)
                        et = datetime.timedelta(seconds=frame_idx/fps)
                        subs.append(srt.Subtitle(index=sub_index, start=st, end=et, content=f"Line {sub_index}"))
                        sub_index += 1
                    if density_d > 0.005:
                        d_speaking = True
                        d_start = frame_idx
                        d_peak = density_d
                    else:
                        d_speaking = False
                        d_peak = 0.0
            
            # 3. 选项逻辑 (V7)
            is_choice = (ratio_c > 0.6) and (ratio_c > ratio_b + 0.3)
            if not c_active:
                if is_choice:
                    c_active = True
                    c_start = frame_idx
            else:
                if not is_choice:
                    c_active = False
                    if (frame_idx - c_start) / fps > 0.5:
                        st = datetime.timedelta(seconds=c_start/fps)
                        et = datetime.timedelta(seconds=frame_idx/fps)
                        subs.append(srt.Subtitle(index=sub_index, start=st, end=et, content=f"[Choice] Line {sub_index}"))
                        sub_index += 1
            
            frame_idx += 1
            
        cap.release()
        
        # 保存
        subs.sort(key=lambda x: x.start)
        for i, sub in enumerate(subs): sub.index = i + 1
        with open(output_srt, "w", encoding="utf-8") as f:
            f.write(srt.compose(subs))
            
        self.root.after(0, lambda: messagebox.showinfo("完成", f"字幕已保存到视频同目录：\n{output_srt}"))
        self.is_processing = False
        self.root.after(0, lambda: self.lbl_status.config(text="提取完成！"))

if __name__ == "__main__":
    root = tk.Tk()
    app = SubtitleApp(root)
    root.mainloop()