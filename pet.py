"""
奶娃桌宠 - 桌面宠物应用
基于 Python tkinter + Pillow + imageio + pygame 实现

功能：
- 桌面悬浮（无边框、置顶、隐藏任务栏、真透明背景）
- 多个形象（pet1~pet3），右键菜单切换，每 20 分钟自动切换
- 左键拖拽移动；快速松手 → 物理甩动（重力 + 边缘反弹 + 挤压形变）
- 大笑视频：绿幕色键抠图 → 透明播放，切换无痕
- 陪伴时长跨会话持久化，启动时显示问候气泡
- 对话功能：OpenAI 兼容 API，桌面气泡显示奶蛙回复
- 主菜单：API 配置窗口（Base URL / Key / 模型）
- 右键菜单：陪伴时长(信息)、切换形象、对话、大笑、主菜单、退出
"""

import json
import urllib.request
import urllib.error
import tkinter as tk
from PIL import Image, ImageTk
import random
import math
import os
import sys
import time
import queue
import threading
import subprocess
import tempfile
import hashlib
from collections import deque

import numpy as np
import imageio
import imageio_ffmpeg
import pygame

# 切换到程序所在目录（打包为 exe 后为 exe 所在目录，素材文件与 exe 同目录）
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

# 用户数据目录：API 配置和陪伴时长存到这里，与程序位置无关
# （避免 exe 换位置/重装后配置丢失的"目录不一致"问题）
DATA_DIR = os.path.join(os.environ.get("APPDATA", BASE_DIR), "naiwa-pet")
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except Exception:
    DATA_DIR = BASE_DIR

# ========== 配置 ==========
PET_IMAGES = ["pet1.png", "pet2.png", "pet3.png"]   # 桌宠形象列表
PET_DISPLAY_WIDTH = 200                             # 形象显示宽度（等比缩放）
PET_SWITCH_INTERVAL = 20 * 60 * 1000                # 形象自动切换间隔：20 分钟（毫秒）
VIDEO_FILE = "奶龙大笑【原版】-nobg.mp4"             # 大笑视频（已扣绿幕，无音轨）
AUDIO_FILE = "单集_音频1785667030.m4a"               # 大笑音频（独立文件）
VIDEO_PLAY_WIDTH = 600                              # 视频播放时窗口宽度（px，原始400×1.5放大）
FLOAT_AMPLITUDE = 6                                 # 飘浮幅度（像素）
FLOAT_SPEED = 2.0                                   # 飘浮速度
PET_ALPHA_THRESHOLD = 30                            # 图片 alpha 低于此值视为背景（透掉）
TIME_FILE = os.path.join(DATA_DIR, "naiwa_time.txt")   # 陪伴时长持久化文件（用户数据目录）
API_CONFIG_FILE = os.path.join(DATA_DIR, "api_config.json")  # API 配置持久化文件（用户数据目录）

# 绿幕色键参数
CHROMA_G_MIN = 100      # 绿色通道最低值（排除暗部）
CHROMA_G_R = 1.2        # G > R × 此系数
CHROMA_G_B = 1.1        # G > B × 此系数

# 物理甩动参数（速度单位：像素/帧，60fps）
PHYS_GRAVITY    = 0.32   # 重力加速度（×0.8，弹更久）
PHYS_AIR_DRAG   = 0.98   # 空气阻力衰减系数
PHYS_BOUNCE_K   = 0.70   # 边缘反弹能量保留比例
PHYS_STOP_SPEED = 0.5    # 速度低于此值停止
PHYS_LAUNCH_MIN = 150    # 甩动判定：晚段速度阈值（px/s）
PHYS_TREND_MIN  = 30     # 甩动判定：晚段-早段速度差阈值（px/s）
PHYS_DISP_MIN   = 80     # 甩动判定：总位移阈值（px）

# 透明色（Windows 上该颜色像素会显示为透明）
MAGENTA = (255, 0, 255)
MAGENTA_HEX = "#ff00ff"


# ============================================================
# Squish —— 碰撞挤压形变动画
# 撞到屏幕边缘时：先压缩（100ms），再复原（150ms）。
# 通过返回 (scaleX, scaleY) 缩放系数，由外部应用到宠物图片。
# ============================================================
class Squish:
    PHASE_NONE, PHASE_COMPRESS, PHASE_RESTORE = 0, 1, 2

    def __init__(self):
        self.phase = self.PHASE_NONE
        self.phase_start_ms = 0
        self.vertical = False   # True=撞上下边缘，False=撞左右边缘
        self.amount = 0.3       # 形变幅度（压缩到 0.7，拉伸到 1.3）

    def reset(self):
        self.phase = self.PHASE_NONE

    def is_active(self):
        return self.phase != self.PHASE_NONE

    def trigger(self, vertical, now_ms):
        """触发一次挤压动画"""
        self.phase = self.PHASE_COMPRESS
        self.phase_start_ms = now_ms
        self.vertical = vertical

    def get_scale(self, now_ms):
        """返回当前应施加的缩放系数 (scaleX, scaleY)"""
        if self.phase == self.PHASE_NONE:
            return (1.0, 1.0)

        elapsed = (now_ms - self.phase_start_ms) / 1000.0

        if self.phase == self.PHASE_COMPRESS:
            # 压缩阶段 100ms
            t = min(elapsed / 0.10, 1.0)
            sq = 1.0 - self.amount * t
            ex = 1.0 + self.amount * t
            if t >= 1.0:
                self.phase = self.PHASE_RESTORE
                self.phase_start_ms = now_ms
            # 无论是否刚切换，都返回当前压缩值
            return (ex, sq) if self.vertical else (sq, ex)
        else:  # PHASE_RESTORE
            # 复原阶段 150ms
            t = min(elapsed / 0.15, 1.0)
            sq = (1.0 - self.amount) + self.amount * t
            ex = (1.0 + self.amount) - self.amount * t
            if t >= 1.0:
                self.phase = self.PHASE_NONE
                return (1.0, 1.0)
            return (ex, sq) if self.vertical else (sq, ex)


# ============================================================
# Physics —— 物理飞行系统
# 奶蛙被快速甩出后进入飞行状态，每帧模拟重力、空气阻力、边缘反弹。
# ============================================================
class Physics:
    def __init__(self):
        self.vx = 0.0
        self.vy = 0.0
        self.active = False
        self.squish = Squish()

    def launch(self, vx, vy):
        """以给定初速度启动飞行（像素/帧）"""
        self.vx = vx
        self.vy = vy
        self.active = True
        self.squish.reset()

    def stop(self):
        """强制停止飞行（用户点击抓住）"""
        self.active = False
        self.vx = 0.0
        self.vy = 0.0
        self.squish.reset()

    def update(self, owner, now_ms):
        """每帧推进物理：移动窗口、处理边缘碰撞、触发挤压"""
        # 重力 + 空气阻力
        self.vy += PHYS_GRAVITY
        self.vx *= PHYS_AIR_DRAG
        self.vy *= PHYS_AIR_DRAG

        x = owner.window.winfo_x() + int(self.vx)
        y = owner.window.winfo_y() + int(self.vy)
        sw = owner.window.winfo_screenwidth()
        sh = owner.window.winfo_screenheight()
        w, h = owner.pet_width, owner.pet_height

        # 边缘反弹（以窗口边界为基准）；速度很低时不再反弹，直接归零
        if x < 0:
            x = 0
            self.vx = abs(self.vx) * PHYS_BOUNCE_K if abs(self.vx) >= 3 else 0.0
            self.squish.trigger(False, now_ms)
        elif x > sw - w:
            x = sw - w
            self.vx = -abs(self.vx) * PHYS_BOUNCE_K if abs(self.vx) >= 3 else 0.0
            self.squish.trigger(False, now_ms)
        if y < 0:
            y = 0
            self.vy = abs(self.vy) * PHYS_BOUNCE_K if abs(self.vy) >= 3 else 0.0
            self.squish.trigger(True, now_ms)
        elif y > sh - h:
            y = sh - h
            self.vy = -abs(self.vy) * PHYS_BOUNCE_K if abs(self.vy) >= 3 else 0.0
            self.squish.trigger(True, now_ms)

        owner.window.geometry(f"+{x}+{y}")

        # 底部兜底：贴近屏幕底部且速度极低时强制停止，防止悬停误判
        near_bottom = y >= sh - h - 5
        if math.hypot(self.vx, self.vy) < 1.0 and near_bottom:
            self.vx = 0.0
            self.vy = 0.0

        # 停止条件：速度归零
        if abs(self.vx) < PHYS_STOP_SPEED and abs(self.vy) < PHYS_STOP_SPEED:
            self.vx = 0.0
            self.vy = 0.0
            self.active = False


class DesktopPet:
    def __init__(self):
        # 创建主窗口
        self.window = tk.Tk()
        self.window.title("奶娃桌宠")

        # 窗口属性设置
        self.window.overrideredirect(True)            # 无边框
        self.window.wm_attributes("-topmost", True)   # 始终置顶
        self.window.wm_attributes("-toolwindow", True)  # 隐藏任务栏图标
        self.window.configure(bg=MAGENTA_HEX)
        # 真透明背景（Windows）：magenta 色像素变为透明
        try:
            self.window.wm_attributes("-transparentcolor", MAGENTA_HEX)
        except Exception:
            pass

        # ========== 加载多个形象 ==========
        self.pet_files = [f for f in PET_IMAGES if os.path.exists(f)]
        if not self.pet_files:
            self.pet_files = ["pet1.png"]
        self.pet_pil = self.load_pet_images()      # 预处理后的 PIL 图片列表
        self.current_pet_index = 0
        self.original_image = self.pet_pil[0]
        self.tk_image = ImageTk.PhotoImage(self.original_image)
        self.pet_width = self.tk_image.width()
        self.pet_height = self.tk_image.height()

        # 创建标签显示图片（place 居中，便于挤压形变时保持窗口居中显示）
        self.label = tk.Label(
            self.window,
            image=self.tk_image,
            bd=0,
            bg=MAGENTA_HEX,
            cursor="hand2",
        )
        self.label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        # 设置窗口大小和初始位置
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        start_x = screen_width - self.pet_width - 50
        start_y = screen_height - self.pet_height - 100
        self.window.geometry(
            f"{self.pet_width}x{self.pet_height}+{start_x}+{start_y}"
        )

        # ========== 状态变量 ==========
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.mouse_down_x = 0
        self.mouse_down_y = 0
        self.is_dragging = False
        self.is_animating = False

        # 物理甩动状态
        self.physics = Physics()
        self._physics_job = None
        self._pos_history = deque()   # 拖拽轨迹：deque of (x, y, time_s)
        self._drag_press_screen = None  # 拖拽按下时的屏幕坐标
        self._squish_photo = None       # 挤压形变用的 PhotoImage 引用

        # 飘浮动画状态
        self.float_phase = random.uniform(0, 2 * math.pi)
        self.base_x = start_x
        self.base_y = start_y
        self.float_paused = False
        self.last_float_y = 0

        # 陪伴时长
        self.base_minutes = self.load_total_minutes()
        self.start_time = time.time()

        # 问候气泡 / 对话气泡
        self.greet_bubble = None
        self.greet_job = None

        # 主菜单窗口
        self._main_menu_win = None

        # 定时任务
        self.float_job_id = None
        self.pet_switch_job = None
        self._api_poll_job = None

        # 视频播放状态
        self.video_playing = False
        self._video_queue = None
        self._video_reader = None
        self._video_thread = None
        self._video_frame_job = None
        self._video_frame_delay = 33
        self._pet_geo = None
        self.video_photo = None

        # 初始化音频（失败则只放画面无声音）
        self.audio_ok = False
        try:
            pygame.mixer.init()
            self.audio_ok = True
        except Exception:
            self.audio_ok = False

        # API 对话结果队列（后台线程 → 主线程轮询）
        self._api_result_queue = queue.Queue()

        # 自动修正旧配置的 model 名大小写
        try:
            cfg = self.load_api_config()
            if cfg.get("model") and cfg["model"] != cfg["model"].lower():
                cfg["model"] = cfg["model"].lower()
                self.save_api_config(cfg)
        except Exception:
            pass

        # ========== 绑定事件 ==========
        self.label.bind("<Button-1>", self.on_mouse_down)        # 左键按下
        self.label.bind("<B1-Motion>", self.on_mouse_move)       # 左键拖动
        self.label.bind("<ButtonRelease-1>", self.on_mouse_up)   # 左键释放
        self.label.bind("<Button-3>", self.on_right_click)       # 右键
        # 防止窗口失去焦点时飘走
        self.window.bind("<FocusOut>", lambda e: None)

        # ========== 启动 ==========
        self.start_float_animation()
        self.schedule_pet_switch()
        self._physics_tick()
        self._api_poll()
        self.show_greet_bubble()
        self.window.mainloop()

    # ========== 形象加载与切换 ==========

    def load_pet_images(self):
        """加载所有形象：等比缩放到固定宽度，背景透明化，主体实心化。

        素材图几乎整张都是半透明像素（柔和光效渲染）。处理策略：
        - alpha 低于阈值的像素 = 背景/光晕 → 设为纯透明色（窗口透掉）
        - alpha 高于阈值的像素 = 主体 → 保留原色并置为不透明
        这样主体完整显示，且半透明像素不再与透明色混合产生紫边。
        """
        images = []
        for f in self.pet_files:
            img = Image.open(f).convert("RGBA")
            h = int(img.height * PET_DISPLAY_WIDTH / img.width)
            img = img.resize((PET_DISPLAY_WIDTH, h), Image.LANCZOS)
            arr = np.array(img)  # (H, W, 4) RGBA
            a = arr[..., 3].astype(np.uint8)
            bg = a < PET_ALPHA_THRESHOLD
            arr[..., 3] = 255  # 所有像素先变为不透明
            arr[bg] = [255, 0, 255, 255]  # 背景像素 → 透明色
            images.append(Image.fromarray(arr).convert("RGB"))
        return images

    def _apply_pet_image(self, index):
        """切换到指定索引的形象（不改变窗口位置）"""
        self.current_pet_index = index % len(self.pet_pil)
        self.original_image = self.pet_pil[self.current_pet_index]
        self.tk_image = ImageTk.PhotoImage(self.original_image)
        self.pet_width = self.tk_image.width()
        self.pet_height = self.tk_image.height()
        self.label.configure(image=self.tk_image)

    def switch_pet(self, delta=1):
        """切换形象：保持窗口中心不动"""
        if self.video_playing or self.is_dragging:
            return
        # 记录当前窗口中心
        cx = self.window.winfo_x() + self.pet_width // 2
        cy = self.window.winfo_y() + self.pet_height // 2

        self._apply_pet_image(self.current_pet_index + delta)

        # 更新窗口尺寸，保持中心
        new_x = max(0, cx - self.pet_width // 2)
        new_y = max(0, cy - self.pet_height // 2)
        self.window.geometry(f"{self.pet_width}x{self.pet_height}+{new_x}+{new_y}")
        self.base_x = new_x
        self.base_y = new_y

    def schedule_pet_switch(self):
        """定时自动切换形象（20 分钟）"""
        self.pet_switch_job = self.window.after(
            PET_SWITCH_INTERVAL, self.auto_switch_pet
        )

    def auto_switch_pet(self):
        """自动切换形象，并继续定时"""
        self.switch_pet(1)
        self.schedule_pet_switch()

    # ========== 鼠标事件处理 ==========

    def on_mouse_down(self, event):
        """鼠标按下：抓住飞行的奶蛙/记录起始位置；播放视频时左键=中断"""
        if self.video_playing:
            self.stop_video_playback()
            return

        # 抓住正在飞行的奶蛙
        if self.physics.active:
            self.physics.stop()
            self._restore_physics_appearance()

        self.drag_start_x = event.x
        self.drag_start_y = event.y
        self.mouse_down_x = event.x_root
        self.mouse_down_y = event.y_root
        self.is_dragging = False
        self.float_paused = True
        self._pos_history.clear()
        self._drag_press_screen = (event.x_root, event.y_root)
        # 按下缩放效果
        self.label.configure(image=self.get_scaled_image(0.92))

    def on_mouse_move(self, event):
        """鼠标移动：处理拖拽，并记录轨迹供甩动判定"""
        if self.video_playing:
            return

        delta_x = abs(event.x_root - self.mouse_down_x)
        delta_y = abs(event.y_root - self.mouse_down_y)

        if delta_x > 3 or delta_y > 3:
            self.is_dragging = True

        if self.is_dragging:
            x = event.x_root - self.drag_start_x
            y = event.y_root - self.drag_start_y
            self.window.geometry(f"+{x}+{y}")
            # 更新基准位置
            self.base_x = x
            self.base_y = y
            self.label.configure(image=self.tk_image)  # 恢复原始大小
            # 记录当前位置和时间（保留最近 200ms 轨迹）
            now = time.monotonic()
            self._pos_history.append((event.x_root, event.y_root, now))
            while len(self._pos_history) > 1:
                if now - self._pos_history[0][2] > 0.20:
                    self._pos_history.popleft()
                else:
                    break

    def on_mouse_up(self, event):
        """鼠标释放：判断点击 vs 拖拽；快速松手时判定物理甩动"""
        if self.video_playing:
            return

        self.label.configure(image=self.tk_image)  # 恢复原始图片
        self.float_paused = False

        if not self.is_dragging:
            # 单击：无动画（点击弹跳已移除，避免与物理挤压弹跳冲突）
            self.base_x = self.window.winfo_x()
            self.base_y = self.window.winfo_y()
        else:
            # 拖拽结束：尝试甩动判定
            self._try_launch()

        # 拖拽结束：重置拖拽状态（否则右键切换形象会被 guard 拦截）
        self.is_dragging = False
        self._pos_history.clear()
        self._drag_press_screen = None
        # 更新基准位置
        self.base_x = self.window.winfo_x()
        self.base_y = self.window.winfo_y()

    def _try_launch(self):
        """根据拖拽轨迹判定是否快速甩出（参考 nailong-pet 的速度趋势算法）"""
        if len(self._pos_history) < 2 or not self._drag_press_screen:
            return

        press_x, press_y = self._drag_press_screen
        last = self._pos_history[-1]
        ref_time = last[2]

        # 总位移：按下点到松手点
        total_disp = math.hypot(last[0] - press_x, last[1] - press_y)
        if total_disp < PHYS_DISP_MIN:
            return

        # 分早段(200~100ms前)和晚段(0~100ms)计算平均速度
        late_first = late_last = None
        early_first = early_last = None
        late_first_t = late_last_t = 0.0
        early_first_t = early_last_t = 0.0

        for x, y, t in self._pos_history:
            age = ref_time - t
            if 0.10 < age <= 0.20:
                if early_first is None:
                    early_first = (x, y); early_first_t = t
                early_last = (x, y); early_last_t = t
            elif 0.0 <= age <= 0.10:
                if late_first is None:
                    late_first = (x, y); late_first_t = t
                late_last = (x, y); late_last_t = t

        def avg_vel(first, last, dt):
            if first is None or last is None or dt <= 0.001:
                return (0.0, 0.0)
            return ((last[0] - first[0]) / dt, (last[1] - first[1]) / dt)

        vel_late = avg_vel(late_first, late_last, late_last_t - late_first_t)
        vel_early = avg_vel(early_first, early_last, early_last_t - early_first_t)

        speed_late = math.hypot(*vel_late)
        speed_early = math.hypot(*vel_early)
        trend = speed_late - speed_early

        # 松手前明确加速（晚段比早段快）且晚段速度足够大 → 甩动
        if trend > PHYS_TREND_MIN and speed_late > PHYS_LAUNCH_MIN:
            # 初速度：px/s → px/帧（÷60fps）
            self.physics.launch(vel_late[0] / 60.0, vel_late[1] / 60.0)
            self.float_paused = True

    def on_right_click(self, event):
        """右键：弹出菜单"""
        menu = tk.Menu(self.window, tearoff=0)
        # 信息行（灰色不可点）
        menu.add_command(
            label=f"陪伴时长：{self.get_total_minutes()} 分钟",
            state="disabled",
        )
        menu.add_separator()
        menu.add_command(label="切换形象", command=self.switch_pet_next)
        menu.add_command(label="对话", command=self.chat_with_naiwa)
        menu.add_command(label="大笑", command=self.play_laugh_video)
        menu.add_separator()
        menu.add_command(label="主菜单", command=self.open_main_menu)
        menu.add_separator()
        menu.add_command(label="退出", command=self.quit)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def switch_pet_next(self):
        """右键菜单：切换到下一个形象"""
        self.switch_pet(1)

    # ========== 视频播放（大笑） ==========

    def play_laugh_video(self):
        """在桌宠窗口内嵌播放大笑视频"""
        if self.video_playing:
            self.stop_video_playback()
        # 停止物理飞行（若有）
        if self.physics.active:
            self.physics.stop()
            self._restore_physics_appearance()
        if not os.path.exists(VIDEO_FILE):
            return

        # 暂停宠物空闲活动
        self.float_paused = True
        self.is_animating = True

        # 记录宠物窗口原始几何（尺寸+位置）
        self._pet_geo = (
            self.pet_width,
            self.pet_height,
            self.window.winfo_x(),
            self.window.winfo_y(),
        )

        # 透明色保持开启：绿幕帧会替换为 magenta 自动透明，切换无黑底闪现

        # 打开视频 reader
        try:
            self._video_reader = imageio.get_reader(VIDEO_FILE)
        except Exception:
            self._restore_pet_ui()
            return

        meta = self._video_reader.get_meta_data()
        fps = meta.get("fps", 30)
        vw, vh = meta.get("size", (1920, 1080))
        self._video_frame_delay = max(16, int(1000 / fps))

        # 计算显示尺寸（保持视频宽高比）
        display_w = VIDEO_PLAY_WIDTH
        display_h = int(display_w * vh / vw)
        scr_w = self.window.winfo_screenwidth()
        scr_h = self.window.winfo_screenheight()
        if display_w > scr_w - 40:
            display_w = scr_w - 40
            display_h = int(display_w * vh / vw)
        if display_h > scr_h - 40:
            display_h = scr_h - 40
            display_w = int(display_h * vw / vh)

        # 调整窗口到视频尺寸，保持宠物中心位置不动
        _, _, pet_x, pet_y = self._pet_geo
        cx = pet_x + self.pet_width // 2
        cy = pet_y + self.pet_height // 2
        new_x = max(0, cx - display_w // 2)
        new_y = max(0, cy - display_h // 2)
        self.window.geometry(f"{display_w}x{display_h}+{new_x}+{new_y}")

        # 准备音频文件（首次提取后缓存到临时目录）
        wav_path = self._ensure_audio_wav()

        # 启动后台解码线程（逐帧缩放后放入队列）
        self.video_playing = True
        self._video_queue = queue.Queue(maxsize=6)
        self._video_thread = threading.Thread(
            target=self._decode_video_thread,
            args=(display_w, display_h),
            daemon=True,
        )
        self._video_thread.start()

        # 等队列缓冲几帧后开始播放（音画同步）
        self.window.after(50, lambda: self._start_video_playback(wav_path))

    def _ensure_audio_wav(self):
        """准备音频 wav（缓存到临时目录）。

        优先使用文件夹中的独立音频文件（新视频已无音轨）；
        没有独立音频时才从视频中提取。
        """
        src = AUDIO_FILE if os.path.exists(AUDIO_FILE) else VIDEO_FILE
        h = hashlib.md5(os.path.abspath(src).encode()).hexdigest()[:10]
        wav = os.path.join(tempfile.gettempdir(), f"naiwa_audio_{h}.wav")
        if not os.path.exists(wav):
            try:
                ff = imageio_ffmpeg.get_ffmpeg_exe()
                cmd = [ff, "-y", "-i", src, "-vn",
                       "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2", wav]
                subprocess.run(cmd, capture_output=True, check=True)
            except Exception:
                pass
        return wav

    def _chroma_key_frame(self, arr):
        """绿幕色键：将绿色背景像素替换为透明色（magenta），主体保留原色。

        在缩小后的帧上执行（像素少，速度快）。检测 G 通道显著高于 R、B
        的像素即为绿幕，替换为透明色；边缘轻微溢色做抑制，避免绿边光晕。
        """
        a = np.asarray(arr, dtype=np.int16)
        r, g, b = a[..., 0], a[..., 1], a[..., 2]

        # 绿幕判定：G 高且明显强于 R、B
        green_mask = (g > CHROMA_G_MIN) & (g > r * CHROMA_G_R) & (g > b * CHROMA_G_B)

        # 溢色抑制：对边缘过渡区（绿但不强）压绿，去掉绿边
        spill = (g > 80) & (g > r * 1.05) & (g > b * 1.05) & (~green_mask)
        if spill.any():
            spill_amount = np.maximum(g[spill] - np.maximum(r[spill], b[spill]), 0)
            r[spill] += (spill_amount * 0.4).astype(np.int16)
            b[spill] += (spill_amount * 0.4).astype(np.int16)
            g[spill] -= (spill_amount * 0.8).astype(np.int16)

        # 绿幕像素 → 纯 magenta（透明色），窗口透掉
        a[green_mask] = (255, 0, 255)

        return np.clip(a, 0, 255).astype(np.uint8)

    def _decode_video_thread(self, w, h):
        """后台线程：逐帧解码视频 → NEAREST 缩小 → 缩小图色键 → 放入队列。

        NEAREST 缩小不产生插值混合（避免主体边缘与透明色混合出紫边），
        色键在缩小后的小图上执行，速度快（不再拖慢视频播放）。
        """
        try:
            for frame in self._video_reader:
                if not self.video_playing:
                    break
                # NEAREST 缩小（无插值，避免紫边）
                img = Image.fromarray(frame).resize((w, h), Image.NEAREST)
                # 缩小图上做绿幕色键（小数组，快）
                proc = self._chroma_key_frame(np.array(img))
                img = Image.fromarray(proc)
                # 队列满时等待（阻塞期间若停止则退出）
                while self.video_playing:
                    try:
                        self._video_queue.put(img, timeout=0.1)
                        break
                    except queue.Full:
                        continue
        except Exception:
            pass
        finally:
            try:
                self._video_reader.close()
            except Exception:
                pass
            try:
                self._video_queue.put(None)  # 发送结束标记
            except Exception:
                pass

    def _start_video_playback(self, wav_path):
        """缓冲几帧后开始播放音频 + 画面"""
        if not self.video_playing:
            return
        # 等待队列至少有 2 帧再播放
        if self._video_queue.qsize() < 2:
            self.window.after(50, lambda: self._start_video_playback(wav_path))
            return

        # 开始播放音频
        if self.audio_ok:
            try:
                pygame.mixer.music.load(wav_path)
                pygame.mixer.music.play()
            except Exception:
                pass

        # 开始逐帧显示
        self._show_next_frame()

    def _show_next_frame(self):
        """主线程：从队列取帧显示（定时循环）"""
        if not self.video_playing:
            return
        try:
            img = self._video_queue.get_nowait()
        except queue.Empty:
            self._video_frame_job = self.window.after(20, self._show_next_frame)
            return

        if img is None:
            # 视频播完，自动恢复宠物
            self.stop_video_playback()
            return

        self.video_photo = ImageTk.PhotoImage(img)
        self.label.configure(image=self.video_photo)
        self._video_frame_job = self.window.after(
            self._video_frame_delay, self._show_next_frame
        )

    def stop_video_playback(self):
        """中断/结束视频播放，恢复宠物显示"""
        self.video_playing = False
        if self._video_frame_job:
            try:
                self.window.after_cancel(self._video_frame_job)
            except Exception:
                pass
            self._video_frame_job = None

        if self.audio_ok:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass

        self._restore_pet_ui()

    def _restore_pet_ui(self):
        """恢复宠物窗口的尺寸、位置和图片"""
        # 透明色始终开启（绿幕视频也靠它透明），无需恢复
        if self._pet_geo:
            w, h, x, y = self._pet_geo
            try:
                self.window.geometry(f"{w}x{h}+{x}+{y}")
            except Exception:
                pass
            self._pet_geo = None
        try:
            self.label.configure(image=self.tk_image)
        except Exception:
            pass
        self.is_animating = False
        self.float_paused = False
        self.last_float_y = 0
        self.base_x = self.window.winfo_x()
        self.base_y = self.window.winfo_y()

    # ========== 物理飞行 ==========

    def _physics_tick(self):
        """物理更新循环（约 60fps），仅在飞行状态时推进"""
        now_ms = time.monotonic() * 1000
        if self.physics.active:
            self.physics.update(self, now_ms)
            # 渲染挤压形变
            sx, sy = self.physics.squish.get_scale(now_ms)
            if self.physics.squish.is_active():
                self._apply_squish(sx, sy)
            else:
                self._restore_physics_appearance()
            if not self.physics.active:
                # 飞行结束，恢复常规状态
                self._restore_physics_appearance()
                self.float_paused = False
                self.is_animating = False
                self.base_x = self.window.winfo_x()
                self.base_y = self.window.winfo_y()
        self._physics_job = self.window.after(16, self._physics_tick)

    def _apply_squish(self, sx, sy):
        """应用挤压形变：缩放图片显示（窗口尺寸不变，图片居中）。

        用 NEAREST 最近邻插值（而非 BILINEAR/LANCZOS），避免缩放时主体
        边缘与透明色插值混合产生紫边。
        """
        try:
            w = max(1, int(self.pet_width * sx))
            h = max(1, int(self.pet_height * sy))
            img = self.original_image.resize((w, h), Image.NEAREST)
            self._squish_photo = ImageTk.PhotoImage(img)
            self.label.configure(image=self._squish_photo)
        except Exception:
            pass

    def _restore_physics_appearance(self):
        """恢复宠物原始图片显示"""
        try:
            self.label.configure(image=self.tk_image)
        except Exception:
            pass

    # ========== 陪伴时长 ==========

    def _migrate_legacy(self, filename):
        """把程序目录下的旧文件迁移到用户数据目录（一次性）"""
        legacy = os.path.join(BASE_DIR, filename)
        new = os.path.join(DATA_DIR, filename)
        if os.path.exists(legacy) and not os.path.exists(new):
            try:
                import shutil
                shutil.copy2(legacy, new)
            except Exception:
                pass

    def load_total_minutes(self):
        """从用户数据目录读取累计陪伴分钟数（自动迁移旧文件）"""
        self._migrate_legacy("naiwa_time.txt")
        try:
            with open(TIME_FILE, "r", encoding="utf-8") as f:
                return int(f.read().strip())
        except Exception:
            return 0

    def get_total_minutes(self):
        """当前累计陪伴分钟数（历史 + 本次运行）"""
        return self.base_minutes + int((time.time() - self.start_time) / 60)

    def save_total_minutes(self):
        """将累计陪伴分钟数写回文件"""
        try:
            with open(TIME_FILE, "w", encoding="utf-8") as f:
                f.write(str(self.get_total_minutes()))
        except Exception:
            pass

    # ========== 问候气泡 ==========

    def get_greeting(self):
        """根据当前小时返回问候语"""
        h = time.localtime().tm_hour
        if 6 <= h < 12:
            return "早上好！"
        if 12 <= h < 18:
            return "下午好！"
        return "晚上好！"

    def show_greet_bubble(self):
        """启动时在奶蛙上方显示问候气泡，20 秒后自动关闭"""
        self.close_greet_bubble()  # 清理旧气泡
        bubble = tk.Toplevel(self.window)
        bubble.overrideredirect(True)
        bubble.wm_attributes("-topmost", True)
        bubble.wm_attributes("-toolwindow", True)
        bubble.configure(bg="white")
        bubble.transient(self.window)

        date_str = time.strftime("%Y/%m/%d %H:%M")
        lines = [
            self.get_greeting(),
            f"今天是 {date_str}",
            f"奶蛙已陪伴你 {self.get_total_minutes()} 分钟",
        ]

        # 估算气泡尺寸（基于文字长度）
        max_len = max(len(s) for s in lines)
        bubble_w = max_len * 15 + 24
        bubble_h = len(lines) * 24 + 16

        bubble.geometry(f"{bubble_w}x{bubble_h}")
        for i, line in enumerate(lines):
            tk.Label(
                bubble,
                text=line,
                bg="white",
                fg="#333333",
                font=("Microsoft YaHei", 12),
                anchor="w",
            ).place(x=12, y=6 + i * 24)

        # 位置：奶蛙窗口上方居中
        pet_x = self.window.winfo_rootx()
        pet_y = self.window.winfo_rooty()
        bx = pet_x + self.pet_width // 2 - bubble_w // 2
        by = pet_y - bubble_h - 10
        bx = max(0, bx)
        by = max(0, by)
        bubble.geometry(f"+{bx}+{by}")

        self.greet_bubble = bubble
        self.greet_job = self.window.after(20000, self.close_greet_bubble)

    def close_greet_bubble(self):
        """关闭问候气泡"""
        if self.greet_job:
            try:
                self.window.after_cancel(self.greet_job)
            except Exception:
                pass
            self.greet_job = None
        if self.greet_bubble:
            try:
                self.greet_bubble.destroy()
            except Exception:
                pass
            self.greet_bubble = None

    # ========== API 配置 ==========

    def load_api_config(self):
        """从用户数据目录加载 API 配置（自动迁移旧文件）"""
        self._migrate_legacy("api_config.json")
        try:
            with open(API_CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            return {
                "base_url": cfg.get("base_url", ""),
                "api_key": cfg.get("api_key", ""),
                "model": cfg.get("model", ""),
            }
        except Exception:
            return {"base_url": "", "api_key": "", "model": ""}

    def save_api_config(self, cfg):
        """保存 API 配置到文件"""
        try:
            with open(API_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def is_api_configured(self):
        """API 是否已配置（base_url 和 api_key 均非空）"""
        cfg = self.load_api_config()
        return bool(cfg["base_url"]) and bool(cfg["api_key"])

    def open_main_menu(self):
        """打开主菜单窗口"""
        if self._main_menu_win is not None:
            try:
                self._main_menu_win.win.lift()
                return
            except Exception:
                pass
        self._main_menu_win = MainMenu(self)
        self._main_menu_win.win.protocol("WM_DELETE_WINDOW", self._on_main_menu_close)

    def _on_main_menu_close(self):
        """关闭主菜单窗口"""
        if self._main_menu_win is not None:
            try:
                self._main_menu_win.destroy()
            except Exception:
                pass
            self._main_menu_win = None

    # ========== 对话功能 ==========

    def chat_with_naiwa(self):
        """右键菜单：与奶蛙对话（自定义输入窗 + 桌面气泡回复）"""
        if self.video_playing:
            self.stop_video_playback()

        if not self.is_api_configured():
            self.show_speech_bubble("本蛙还不会说话～主菜单已打开，填上你的 API Key 就能聊啦！")
            self.open_main_menu()
            return

        cfg = self.load_api_config()

        # 弹出自定义输入窗
        dialog = ChatDialog(self.window)
        self.window.wait_window(dialog.win)
        prompt = dialog.result
        if not prompt:
            return

        # 先显示"正在思考"气泡
        self.show_speech_bubble("本蛙想想... 🐸")

        # 后台线程调用 API，结果放入队列由主线程轮询显示
        threading.Thread(
            target=self._api_chat_worker,
            args=(cfg, prompt),
            daemon=True,
        ).start()

    def _api_chat_worker(self, cfg, prompt):
        """后台线程：调用 OpenAI 兼容 API，结果放入队列"""
        try:
            url = cfg["base_url"].rstrip("/")
            if not url.endswith("/v1"):
                url += "/v1"
            url += "/chat/completions"

            payload = {
                "model": cfg["model"],
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "你是奶蛙（Naiwa），一只有点憨憨的可爱桌面宠物，"
                            "住在用户的电脑桌面上。回复要求："
                            "1. 简短（40字以内）2. 可爱有趣 3. 中文为主，"
                            "偶尔用颜文字 4. 自称\"本蛙\"。"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 200,
                "temperature": 0.8,
            }

            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {cfg['api_key']}",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            reply = data["choices"][0]["message"]["content"].strip()
            if not reply:
                reply = "本蛙没听清...你再说一遍？"
            self._api_result_queue.put(reply)
        except urllib.error.HTTPError as e:
            # 显示 API 返回的具体错误原因
            msg = "请求失败"
            try:
                body = json.loads(e.read().decode("utf-8", errors="replace"))
                msg = body.get("error", {}).get("message", msg)
            except Exception:
                msg = f"请求失败 (HTTP {e.code})"
            self._api_result_queue.put(f"本蛙遇到问题了：{msg}")
        except Exception:
            self._api_result_queue.put("本蛙的信号不太好... 🐸")

    def _api_poll(self):
        """主线程轮询 API 结果队列（每 200ms），显示回复气泡"""
        try:
            while not self._api_result_queue.empty():
                result = self._api_result_queue.get_nowait()
                self.show_speech_bubble(result)
        except Exception:
            pass
        self._api_poll_job = self.window.after(200, self._api_poll)

    def show_speech_bubble(self, text, duration=12000):
        """在奶蛙上方显示对话气泡（支持多行折行）"""
        try:
            self.close_greet_bubble()
        except Exception:
            pass

        bubble = tk.Toplevel(self.window)
        bubble.overrideredirect(True)
        bubble.wm_attributes("-topmost", True)
        bubble.wm_attributes("-toolwindow", True)
        bubble.configure(bg="white")
        bubble.transient(self.window)

        # 自动折行：每行约 20 字符
        max_line = 20
        lines = []
        for paragraph in text.split("\n"):
            for i in range(0, len(paragraph), max_line):
                lines.append(paragraph[i:i + max_line])
            lines.append("")
        lines = [ln for ln in lines if ln]

        bubble_w = max_line * 16 + 24
        bubble_h = len(lines) * 22 + 16
        bubble.geometry(f"{bubble_w}x{bubble_h}")

        # 圆角模拟：白底 + 圆角边框容器（用 label 组合）
        container = tk.Frame(bubble, bg="white", highlightbackground="#d8d8d8",
                             highlightthickness=1, bd=0)
        container.pack(fill="both", expand=True, padx=2, pady=2)

        for i, line in enumerate(lines):
            tk.Label(
                container,
                text=line,
                bg="white",
                fg="#4A3728",
                font=("Microsoft YaHei", 12),
                anchor="w",
            ).grid(row=i, column=0, sticky="w", padx=12)

        # 位置：奶蛙窗口上方居中
        pet_x = self.window.winfo_rootx()
        pet_y = self.window.winfo_rooty()
        bx = pet_x + self.pet_width // 2 - bubble_w // 2
        by = pet_y - bubble_h - 10
        bx = max(0, min(bx, self.window.winfo_screenwidth() - bubble_w))
        by = max(0, by)
        bubble.geometry(f"+{bx}+{by}")

        self.greet_bubble = bubble
        self.greet_job = self.window.after(duration, self.close_greet_bubble)

    # ========== 动画效果 ==========

    def get_scaled_image(self, scale):
        """获取缩放后的 PhotoImage"""
        w = int(self.pet_width * scale)
        h = int(self.pet_height * scale)
        img = self.original_image.resize((w, h), Image.LANCZOS)
        return ImageTk.PhotoImage(img)

    def start_float_animation(self):
        """开始空闲飘浮动画"""
        if self.float_paused or self.is_animating:
            self.float_job_id = self.window.after(30, self.start_float_animation)
            return

        self.float_phase += 0.04 * FLOAT_SPEED
        offset_y = int(FLOAT_AMPLITUDE * math.sin(self.float_phase))

        # 只在飘浮偏移量改变时移动窗口
        if offset_y != self.last_float_y:
            dy = offset_y - self.last_float_y
            new_y = self.window.winfo_y() + dy
            self.window.geometry(f"+{self.window.winfo_x()}+{new_y}")
            self.last_float_y = offset_y

        self.float_job_id = self.window.after(30, self.start_float_animation)

    # ========== 退出 ==========

    def quit(self):
        """退出程序"""
        self.video_playing = False
        if self._video_frame_job:
            try:
                self.window.after_cancel(self._video_frame_job)
            except Exception:
                pass
        if self._physics_job:
            try:
                self.window.after_cancel(self._physics_job)
            except Exception:
                pass
        if self.float_job_id:
            self.window.after_cancel(self.float_job_id)
        if self.pet_switch_job:
            self.window.after_cancel(self.pet_switch_job)
        if self.greet_job:
            try:
                self.window.after_cancel(self.greet_job)
            except Exception:
                pass
        if self._api_poll_job:
            try:
                self.window.after_cancel(self._api_poll_job)
            except Exception:
                pass
        self.close_greet_bubble()
        self.save_total_minutes()  # 保存陪伴时长
        if self.audio_ok:
            try:
                pygame.mixer.quit()
            except Exception:
                pass
        self.window.destroy()
        sys.exit(0)


# ============================================================
# MainMenu —— 主菜单窗口
# 暖色调设计，包含 API 配置（Base URL / Key / 模型名）。
# ============================================================
class MainMenu:
    # 主题配色
    BG       = "#FFFBF0"   # 暖白主背景
    HEADER   = "#FFD580"   # 暖黄标题栏
    BTN      = "#FF8C42"   # 活力橙按钮
    BTN_HOV  = "#FFA266"
    TEXT     = "#4A3728"   # 深棕文字
    INPUT_BG = "#FFFFFF"

    def __init__(self, owner):
        self.owner = owner
        self.cfg = owner.load_api_config()
        # 预填默认值：没有配置时，用户只需填 API Key 即可对话
        if not self.cfg.get("base_url"):
            self.cfg["base_url"] = "https://api.deepseek.com"
        if not self.cfg.get("model"):
            self.cfg["model"] = "deepseek-chat"

        self.win = tk.Toplevel(owner.window)
        self.win.title("奶蛙桌宠 · 主菜单")
        self.win.configure(bg=self.BG)
        self.win.resizable(False, False)
        self.win.attributes("-topmost", True)

        self._build_ui()

        # 居中显示（相对奶蛙）
        self.win.update_idletasks()
        w = self.win.winfo_width()
        h = self.win.winfo_height()
        x = owner.window.winfo_rootx() + owner.pet_width // 2 - w // 2
        y = owner.window.winfo_rooty() - h - 10
        x = max(0, x)
        y = max(0, y)
        self.win.geometry(f"+{x}+{y}")

    # ---- UI 构建 ----

    def _build_ui(self):
        # 标题栏
        header = tk.Frame(self.win, bg=self.HEADER, height=52)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header, text="🐸  奶蛙桌宠", bg=self.HEADER, fg=self.TEXT,
            font=("Microsoft YaHei", 16, "bold"),
        ).pack(side="left", padx=20)

        # 主体内容
        body = tk.Frame(self.win, bg=self.BG, padx=24, pady=16)
        body.pack(fill="both", expand=True)

        # 配置区标题
        tk.Label(
            body, text="⚙️  API 配置", bg=self.BG, fg=self.TEXT,
            font=("Microsoft YaHei", 13, "bold"),
        ).pack(anchor="w", pady=(0, 10))

        # Base URL
        self._add_row(body, "Base URL", "base_url", "https://api.deepseek.com")
        # API Key
        self._add_row(body, "API Key", "api_key", "sk-", password=True)
        # 模型名
        self._add_row(body, "模型名称", "model", "deepseek-chat")

        # 按钮行
        btn_row = tk.Frame(body, bg=self.BG)
        btn_row.pack(fill="x", pady=(14, 6))
        self._make_button(btn_row, "💾 保存配置", self._on_save).pack(side="left")
        self._make_button(btn_row, "🔗 测试连接", self._on_test).pack(side="left", padx=8)

        # 状态标签
        self.status_lbl = tk.Label(
            body, text="", bg=self.BG, fg="#3A8F5F",
            font=("Microsoft YaHei", 11),
        )
        self.status_lbl.pack(anchor="w", pady=(6, 0))
        self._update_status()

        # 分隔线
        tk.Frame(body, bg="#E8DCC8", height=1).pack(fill="x", pady=12)

        # 使用说明
        tk.Label(
            body, text="📖  使用说明", bg=self.BG, fg=self.TEXT,
            font=("Microsoft YaHei", 11, "bold"),
        ).pack(anchor="w")
        tips = [
            "1. 填写上方 API 配置并点击「保存配置」",
            "2. 右键奶蛙 → 「对话」，输入想说的话",
            "3. 奶蛙会以可爱风格在气泡中回复你",
            "提示：支持任何 OpenAI 兼容接口",
        ]
        for tip in tips:
            tk.Label(
                body, text=tip, bg=self.BG, fg="#7A6A58",
                font=("Microsoft YaHei", 10),
            ).pack(anchor="w", pady=1)

    def _add_row(self, parent, label_text, key, placeholder, password=False):
        """配置表单项（标签 + 输入框）"""
        row = tk.Frame(parent, bg=self.BG)
        row.pack(fill="x", pady=4)
        tk.Label(
            row, text=label_text, bg=self.BG, fg=self.TEXT,
            font=("Microsoft YaHei", 11), width=9, anchor="w",
        ).pack(side="left")
        var = tk.StringVar(value=self.cfg.get(key, ""))
        entry = tk.Entry(
            row, textvariable=var, bg=self.INPUT_BG,
            font=("Microsoft YaHei", 11), width=32,
            highlightthickness=1, highlightbackground="#D9CBB6",
            highlightcolor="#FF8C42",
        )
        entry.pack(side="left", ipady=3)
        if password:
            entry.config(show="●")
            entry.insert(0, "")  # 确保光标位置
            entry.icursor(len(var.get()))
        setattr(self, f"var_{key}", var)
        # 绑定回车保存
        entry.bind("<Return>", lambda e: self._on_save())

    def _make_button(self, parent, text, command):
        """创建主题按钮（hover 变色）"""
        btn = tk.Button(
            parent, text=text, bg=self.BTN, fg="white",
            activebackground=self.BTN_HOV, activeforeground="white",
            font=("Microsoft YaHei", 11), bd=0, padx=14, pady=5,
            cursor="hand2", command=command,
        )
        btn.bind("<Enter>", lambda e: btn.config(bg=self.BTN_HOV))
        btn.bind("<Leave>", lambda e: btn.config(bg=self.BTN))
        return btn

    # ---- 逻辑 ----

    def _collect_cfg(self):
        # 模型名统一转小写（主流 API 模型名均为小写，避免大小写报错）
        return {
            "base_url": self.var_base_url.get().strip(),
            "api_key": self.var_api_key.get().strip(),
            "model": self.var_model.get().strip().lower(),
        }

    def _on_save(self):
        """保存配置"""
        cfg = self._collect_cfg()
        if not cfg["base_url"] or not cfg["api_key"]:
            self.status_lbl.config(text="⚠️  请填写 Base URL 和 API Key", fg="#C0502F")
            return
        self.owner.save_api_config(cfg)
        self._update_status("✅  配置已保存")
        # 显示成功气泡
        self.owner.show_speech_bubble("配置保存好啦，本蛙可以聊天了！")

    def _on_test(self):
        """测试连接：向 API 发送一条测试消息"""
        cfg = self._collect_cfg()
        if not cfg["base_url"] or not cfg["api_key"]:
            self.status_lbl.config(text="⚠️  请先填写 Base URL 和 API Key", fg="#C0502F")
            return
        self.status_lbl.config(text="🔄  正在测试连接...", fg="#4A3728")
        self.win.update_idletasks()

        def worker():
            try:
                url = cfg["base_url"].rstrip("/")
                if not url.endswith("/v1"):
                    url += "/v1"
                url += "/chat/completions"
                payload = {
                    "model": cfg["model"] or "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": "你是一只叫奶蛙的可爱桌宠。"},
                        {"role": "user", "content": "说一句简短的话证明你能听到"},
                    ],
                    "max_tokens": 30,
                }
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {cfg['api_key']}",
                    },
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                reply = data["choices"][0]["message"]["content"].strip()
                self.win.after(0, lambda: self.status_lbl.config(
                    text=f"✅  连接成功！奶蛙说：{reply[:20]}...", fg="#3A8F5F"))
            except urllib.error.HTTPError as e:
                self.win.after(0, lambda: self.status_lbl.config(
                    text=f"❌  API 返回错误 {e.code}，请检查配置", fg="#C0502F"))
            except Exception:
                self.win.after(0, lambda: self.status_lbl.config(
                    text="❌  连接失败，请检查网络或配置", fg="#C0502F"))

        threading.Thread(target=worker, daemon=True).start()

    def _update_status(self, text=None, color=None):
        """更新状态文字"""
        if text:
            self.status_lbl.config(text=text, fg=color or "#3A8F5F")
            return
        cfg = self._collect_cfg()
        if cfg["base_url"] and cfg["api_key"]:
            self.status_lbl.config(text="✅  API 已就绪", fg="#3A8F5F")
        else:
            self.status_lbl.config(text="⚠️  尚未配置 API", fg="#C0502F")

    def destroy(self):
        try:
            self.win.destroy()
        except Exception:
            pass


# ============================================================
# ChatDialog —— 自定义对话输入窗
# 暖色调设计，替代系统 simpledialog。Enter 发送，Esc 取消。
# ============================================================
class ChatDialog:
    BG      = "#FFFBF0"   # 暖白背景
    HEADER  = "#FFD580"   # 暖黄标题栏
    BTN     = "#FF8C42"   # 活力橙按钮
    BTN_HOV = "#FFA266"
    TEXT    = "#4A3728"   # 深棕文字

    def __init__(self, parent):
        self.result = None  # 用户输入的结果

        self.win = tk.Toplevel(parent)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=self.BG)

        self._build_ui()
        self._center_on(parent)

        self.win.bind("<Return>", self._on_send)
        self.win.bind("<Escape>", self._on_cancel)
        self.win.focus_set()
        self.entry.focus_set()

    # ---- UI ----

    def _build_ui(self):
        # 标题栏（可拖动）
        header = tk.Frame(self.win, bg=self.HEADER, height=40, cursor="fleur")
        header.pack(fill="x")
        header.pack_propagate(False)
        header.bind("<B1-Motion>", self._drag)
        header.bind("<Button-1>", self._drag_start)
        tk.Label(
            header, text="💬  和奶蛙聊聊天", bg=self.HEADER, fg=self.TEXT,
            font=("Microsoft YaHei", 13, "bold"),
        ).pack(side="left", padx=16)
        # 关闭按钮
        close_btn = tk.Label(
            header, text="✕", bg=self.HEADER, fg=self.TEXT,
            font=("Microsoft YaHei", 12), cursor="hand2",
        )
        close_btn.pack(side="right", padx=10)
        close_btn.bind("<Button-1>", lambda e: self._on_cancel())

        # 内容区
        body = tk.Frame(self.win, bg=self.BG, padx=18, pady=14)
        body.pack(fill="both", expand=True)

        tk.Label(
            body, text="对奶蛙说点什么吧：", bg=self.BG, fg=self.TEXT,
            font=("Microsoft YaHei", 11),
        ).pack(anchor="w", pady=(0, 6))

        # 多行输入框
        self.entry = tk.Text(
            body, height=3, width=36, bg="white", fg=self.TEXT,
            font=("Microsoft YaHei", 12), wrap="word",
            relief="flat", highlightthickness=1,
            highlightbackground="#D9CBB6", highlightcolor="#FF8C42",
            insertbackground=self.TEXT,
        )
        self.entry.pack(fill="both", expand=True)

        # 按钮行
        btn_row = tk.Frame(body, bg=self.BG)
        btn_row.pack(fill="x", pady=(12, 0))

        tip = tk.Label(
            btn_row, text="Enter 发送 · Esc 取消", bg=self.BG,
            fg="#A08C72", font=("Microsoft YaHei", 9),
        )
        tip.pack(side="left")

        send_btn = tk.Button(
            btn_row, text="发送 ➤", bg=self.BTN, fg="white",
            activebackground=self.BTN_HOV, activeforeground="white",
            font=("Microsoft YaHei", 11, "bold"), bd=0, padx=18, pady=4,
            cursor="hand2", command=self._on_send,
        )
        send_btn.pack(side="right")
        send_btn.bind("<Enter>", lambda e: send_btn.config(bg=self.BTN_HOV))
        send_btn.bind("<Leave>", lambda e: send_btn.config(bg=self.BTN))

    # ---- 拖动窗口 ----

    def _drag_start(self, event):
        self._drag_off = (event.x, event.y)

    def _drag(self, event):
        try:
            x = self.win.winfo_x() + event.x - self._drag_off[0]
            y = self.win.winfo_y() + event.y - self._drag_off[1]
            self.win.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _center_on(self, parent):
        self.win.update_idletasks()
        w = self.win.winfo_reqwidth()
        h = self.win.winfo_reqheight()
        x = parent.winfo_rootx() + parent.winfo_width() // 2 - w // 2
        y = parent.winfo_rooty() + parent.winfo_height() // 2 - h // 2
        x = max(0, x)
        y = max(0, y)
        self.win.geometry(f"{w}x{h}+{x}+{y}")

    # ---- 事件 ----

    def _on_send(self, event=None):
        text = self.entry.get("1.0", "end").strip()
        if text:
            self.result = text
            self.win.destroy()

    def _on_cancel(self, event=None):
        self.result = None
        self.win.destroy()


if __name__ == "__main__":
    DesktopPet()
