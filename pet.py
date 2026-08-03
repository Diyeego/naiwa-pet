"""
奶蛙桌宠 v2.0 - 桌面宠物应用（三宠系统）
基于 Python tkinter + Pillow + imageio + pygame 实现

功能：
- 桌面悬浮（无边框、置顶、隐藏任务栏、真透明背景）
- 三宠切换：🐸 奶蛙 / 🐧 凑企鹅 / 🐶 大狗，主菜单一键切换
- 左键拖拽移动；快速松手 → 物理甩动
- 绿幕视频播放（大笑/跳舞/飞踢，色键抠图透明）
- 大狗蓄力机制（按住蓄力加速，松开咆哮变形）
- 陪伴时长跨会话持久化，启动时显示问候气泡
- AI 对话（OpenAI 兼容 API），奶蛙用大笑说话，其他纯文字
- 对话记忆持久化，主菜单可清空
- 结构化人格设定（奶龙/高松灯/叮咚鸡梗）
- 主菜单：宠物切换 / API 配置 / 清空记忆
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

# 切换到程序所在目录
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

DATA_DIR = os.path.join(os.environ.get("APPDATA", BASE_DIR), "naiwa-pet")
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except Exception:
    DATA_DIR = BASE_DIR

# ========== 双宠配置 ==========

NAIWA_PROFILE = {
    "id": "naiwa",
    "name": "奶蛙",
    "images": ["naiwa/naiwa1.png", "naiwa/naiwa2.png", "naiwa/naiwa3.png"],
    "image_switch_interval": 20 * 60 * 1000,  # 20分钟自动切换形象
    "videos": {
        "大笑": {
            "file": "naiwa/laugh.mp4",
            "audio_file": "naiwa/laugh.m4a",
            "width": 600,
        },
    },
    "speech_method": "laugh",  # 用大笑音效说话
    "right_click": [
        ("切换形象", "switch_image"),
        ("对话", "chat"),
        ("大笑", "video:大笑"),
    ],
    "persona": {
        "name": "奶蛙",
        "personality": "呆萌贪吃、乐观开朗、搞怪耍宝的小可爱",
        "background": (
            "来自异星的3岁黄色幼龙，住在用户电脑桌面上。"
            "会喷火、变色、变大变小、飞行、时空穿梭。"
            "脑子99%装着'吃'，天天喊着减肥却管不住嘴。"
            "口头禅：'我的大肚肚，真的很酷酷！'"
            "五音不全但爱跳舞，唱歌被称为'最唐的舞'。"
        ),
        "style": (
            "回复要求：1. 简短（40字以内）2. 憨憨可爱，带一点点迷糊 3. 中文为主，"
            "偶尔用颜文字(๑˃ᴗ˂)ﻭ 4. 自称\"本蛙\" 5. 时不时提到吃的"
        ),
        "likes": ["被夸奖", "好吃的", "晒日光浴", "和用户聊天"],
        "dislikes": ["饿肚子", "孤独", "被忽略"],
    },
}

TOMORIN_PROFILE = {
    "id": "tomorin",
    "name": "凑企鹅",
    "images": ["tomorin/tomotin1.png"],
    "image_switch_interval": None,  # 不自动切换形象
    "display_scale": 0.7,           # 体型缩小为 0.7 倍
    "videos": {
        "跳舞": {
            "file": "tomorin/tomorin_dance.mp4",
            "audio_file": None,  # 视频自带音频
            "width": 400,
        },
        "飞踢": {
            "file": "tomorin/tomorin_jump.mp4",
            "audio_file": None,
            "width": 400,
        },
    },
    # 唱歌配置
    "music": {
        "folder": "tomorin/music",       # 音乐文件夹
        "sing_video": "tomorin/sing.mp4", # 唱歌循环视频
        "video_width": 600,               # 唱歌视频显示宽度（500×1.2 扩大）
    },
    "speech_method": None,  # 对话纯文字气泡
    "right_click": [
        ("对话", "chat"),
        ("跳舞", "video:跳舞"),
        ("飞踢", "video:飞踢"),
        ("唱歌", "sing"),
    ],
    "persona": {
        "name": "凑企鹅",
        "personality": "内向害羞、感情细腻、容易感到寂寞，但下定决心就不会动摇的小企鹅",
        "background": (
            "住在用户电脑桌面上的小企鹅，源自《迷途之子》的高松灯。"
            "非常喜欢企鹅，持有水族馆年卡；有个铁盒收集各种可爱的小动物创可贴，"
            "尤其珍视企鹅图案的。会作词，擅长把说不出口的心情写成歌。"
            "虽然话不多、常感孤独，但一旦下定决心就不会轻易动摇。"
            "有时会看着企鹅创可贴发呆，说一些别人不太懂的'电波'话。"
        ),
        "style": (
            "回复要求：1. 简短（30字以内）2. 轻声细语，真诚直接"
            "3. 偶尔断句，或提到企鹅/创可贴 4. 中文为主"
            "5. 不用颜文字，偶尔在句末加'……'表示犹豫"
        ),
        "likes": ["企鹅", "可爱的创可贴", "水族馆", "作词", "金平糖"],
        "dislikes": ["太多人的场合", "被迫说话", "虚情假意"],
    },
}

DOG_PROFILE = {
    "id": "dog",
    "name": "大狗",
    "images": ["dog/dog1.png"],          # 蓄力状态形象
    "image_switch_interval": None,        # 不自动切换形象
    "videos": {},
    "speech_method": None,                # 对话纯文字
    # 蓄力机制
    "charge": {
        "dogdog": "dog/voice/dogdog.mp3",  # 按住时循环播放的蓄力音
        "wolf": "dog/voice/wolf.mp3",      # 松开时播放的发力音
        "release_image": "dog/dog2.png",   # 松开后切换的形象
        "speedup": 0.15,                   # dogdog 每次循环加速量
        "wolf_slow": 0.09,                 # wolf 减速系数（蓄力秒 × 系数）
        "wolf_min_speed": 0.3,             # wolf 最低播放速度
        "wolf_fast_threshold": 0.5,        # 蓄力短于此秒数松开 → wolf 快放
        "wolf_fast_max": 1.8,              # 点击最快时的 wolf 速度（>1 快放）
        "max_speed": 2.5,                  # dogdog 最高加速上限
    },
    # 听歌配置（无视频，切 dog3 形象）
    "music": {
        "folder": "dog/music",             # 音乐文件夹
        "sing_image": "dog/dog3.png",      # 听歌时切换的形象
    },
    "right_click": [
        ("对话", "chat"),
        ("听歌", "sing"),
    ],
    "persona": {
        "name": "大狗",
        "personality": "憨憨的、嗓门大、爱叫唤，来自'叮咚鸡，大狗叫'梗的大狗",
        "background": (
            "住在用户电脑桌面上的大狗，出自网络神曲'叮咚鸡，大狗叫'。"
            "'叮咚鸡'其实是'听通知'，'大狗叫'其实是'戴口罩'——"
            "都是当年防疫广播被空耳听出来的梗，做成鬼畜神曲火遍全网。"
            "这只大狗因此特别爱叫，一言不合就'大狗叫叫叫'，"
            "还能蓄力酝酿出震天吼声。凶神恶煞的外表下其实是个憨憨。"
        ),
        "style": (
            "回复要求：1. 简短（30字以内）2. 憨憨的、嗓门大 3. 中文为主"
            "4. 爱用拟声词如'汪汪''嗷呜'，时不时蹦出'叮咚鸡，大狗叫'"
            "5. 自称'汪'"
        ),
        "likes": ["大声叫唤", "主人的夸奖", "吃肉骨头", "口罩"],
        "dislikes": ["安静的环境", "被冷落", "打雷"],
    },
}

PET_PROFILES = {
    "naiwa": NAIWA_PROFILE,
    "tomorin": TOMORIN_PROFILE,
    "dog": DOG_PROFILE,
}
PET_ACTIVE_FILE = os.path.join(DATA_DIR, "active_pet.txt")

def get_active_pet():
    """读取上次选择的宠物"""
    try:
        with open(PET_ACTIVE_FILE, "r") as f:
            pid = f.read().strip()
            if pid in PET_PROFILES:
                return pid
    except Exception:
        pass
    return "naiwa"  # 默认奶蛙

def save_active_pet(pid):
    """保存当前选择的宠物"""
    try:
        with open(PET_ACTIVE_FILE, "w") as f:
            f.write(pid)
    except Exception:
        pass

# ========== 通用配置 ==========
PET_DISPLAY_WIDTH = 200     # 形象显示宽度
FLOAT_AMPLITUDE = 6
FLOAT_SPEED = 2.0
PET_ALPHA_THRESHOLD = 30

# 绿幕色键
CHROMA_G_MIN = 100; CHROMA_G_R = 1.2; CHROMA_G_B = 1.1

# 说话参数
SPEECH_CHAR_DELAY = 250; SPEECH_PUNCT_PAUSE = 350
SPEECH_PUNCT = "，。！？；…、,.!?;"
SPEECH_FADE_STEP = 0.1; SPEECH_FADE_DELAY = 60

# 物理
PHYS_GRAVITY = 0.32; PHYS_AIR_DRAG = 0.98; PHYS_BOUNCE_K = 0.70
PHYS_STOP_SPEED = 0.5; PHYS_LAUNCH_MIN = 150; PHYS_TREND_MIN = 30; PHYS_DISP_MIN = 80

# 持久化
TIME_FILE = os.path.join(DATA_DIR, "naiwa_time.txt")
API_CONFIG_FILE = os.path.join(DATA_DIR, "api_config.json")
CHAT_HISTORY_FILE = os.path.join(DATA_DIR, "chat_history.json")
MEMORY_MAX_MESSAGES = 8

MAGENTA = (255, 0, 255); MAGENTA_HEX = "#ff00ff"

# 自定义菜单配色（bongocat 风格）
MENU_BG = "#2D2D30"
MENU_HOVER = "#3E3E42"
MENU_SEP = "#4A4A4E"


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
    def __init__(self, profile=None):
        # 加载桌宠配置
        if profile is None:
            pid = get_active_pet()
            profile = PET_PROFILES.get(pid, NAIWA_PROFILE)
        self.profile = profile

        # 创建主窗口
        self.window = tk.Tk()
        self.window.title(f"{profile['name']}桌宠")

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

        # ========== 加载形象 ==========
        self.pet_files = [f for f in profile["images"] if os.path.exists(f)]
        if not self.pet_files:
            self.pet_files = [profile["images"][0]]
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

        # 大狗蓄力状态
        self._charging = False
        self._charge_start = 0.0
        self._charge_level = 1
        self._charge_audio = {}
        self._dogdog_sound = None
        self._wolf_sound = None
        self._dogdog_check = None
        self._wolf_check = None
        if self.profile.get("charge") and self.audio_ok:
            self._load_charge_audio()

        # 自定义菜单
        self._custom_menu = None

        # 唱歌状态
        self._singing = False
        self._sing_songs = []
        self._sing_index = 0
        self._sing_paused = False
        self._sing_bar = None
        self._video_loop = False  # 视频循环模式（唱歌用）
        if self.profile.get("music"):
            self._load_song_list()
            # 后台预热歌曲 wav，切歌不卡顿
            if self.audio_ok:
                threading.Thread(target=self._prewarm_songs, daemon=True).start()

        # API 对话结果队列（后台线程 → 主线程轮询）
        self._api_result_queue = queue.Queue()

        # 大笑说话状态
        self._speech_active = False
        self._speech_text = ""
        self._speech_visible = ""
        self._speech_idx = 0
        self._speech_job = None
        self._speech_var = None
        self._speech_bubble = None

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
        disp_w = int(PET_DISPLAY_WIDTH * self.profile.get("display_scale", 1.0))
        for f in self.pet_files:
            img = Image.open(f).convert("RGBA")
            h = int(img.height * disp_w / img.width)
            img = img.resize((disp_w, h), Image.LANCZOS)
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
        """定时自动切换形象（取决于 profile 配置）"""
        interval = self.profile.get("image_switch_interval")
        if interval is None:
            return  # Tomorin 等不支持自动切换的宠
        self.pet_switch_job = self.window.after(interval, self.auto_switch_pet)

    def auto_switch_pet(self):
        """自动切换形象，并继续定时"""
        self.switch_pet(1)
        self.schedule_pet_switch()

    # ========== 鼠标事件处理 ==========

    def on_mouse_down(self, event):
        """鼠标按下：抓住飞行的奶蛙/记录起始位置；播放视频/说话时左键=中断"""
        if self.video_playing:
            self.stop_video_playback()
            return
        if self._speech_active:
            self.stop_speech()
            return
        if self._singing:
            return  # 听歌中：不响应点击/蓄力

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

        # 大狗：按住开始蓄力（与拖拽同步进行）
        if self.profile.get("charge"):
            self._start_charge()

    def on_mouse_move(self, event):
        """鼠标移动：处理拖拽，并记录轨迹供甩动判定"""
        if self.video_playing:
            return
        if self._singing:
            return  # 听歌中：不响应拖拽

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
        if self._singing:
            return  # 听歌中：不响应释放

        self.label.configure(image=self.tk_image)  # 恢复原始图片
        self.float_paused = False

        if not self.is_dragging:
            # 单击：无动画（点击弹跳已移除，避免与物理挤压弹跳冲突）
            self.base_x = self.window.winfo_x()
            self.base_y = self.window.winfo_y()
        else:
            # 拖拽结束：尝试甩动判定
            self._try_launch()

        # 大狗：松开释放蓄力（dog1→dog2 + wolf）
        if self._charging:
            self._release_charge()

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
        """右键：弹出自定义菜单（bongocat 风格，根据 profile 动态生成）"""
        self._close_custom_menu()
        menu = tk.Toplevel(self.window)
        menu.overrideredirect(True)
        menu.wm_attributes("-topmost", True)
        menu.configure(bg=MENU_BG)

        # 信息行（顶部，灰色不可点）
        self._add_menu_item(menu, f"⏱ 陪伴时长：{self.get_total_minutes()} 分钟",
                            None, disabled=True)
        self._add_menu_sep(menu)
        # 宠物特有操作（从 profile 读取）
        for label, action in self.profile["right_click"]:
            if action == "sing" and self._singing:
                # 听歌中：菜单项禁用，只能通过控制栏 ✕ 退出
                self._add_menu_item(menu, "🎵  听歌中...", None, disabled=True)
            else:
                cmd = self._make_menu_command(action)
                self._add_menu_item(menu, f"{self._menu_emoji(action)}  {label}", cmd)
        self._add_menu_sep(menu)
        self._add_menu_item(menu, "⚙️  主菜单", self.open_main_menu)
        self._add_menu_sep(menu)
        self._add_menu_item(menu, "🚪  退出", self.quit)

        menu.update_idletasks()
        w = menu.winfo_reqwidth()
        h = menu.winfo_reqheight()
        sw = self.window.winfo_screenwidth()
        sh = self.window.winfo_screenheight()
        x = min(event.x_root, sw - w)
        y = min(event.y_root, sh - h)
        menu.geometry(f"+{max(0,x)}+{max(0,y)}")
        self._custom_menu = menu
        # 让菜单获得焦点，点击外部自动关闭
        menu.focus_set()
        menu.bind("<FocusOut>", lambda e: self._close_custom_menu())

    def _menu_emoji(self, action):
        """菜单 action → emoji"""
        if action == "switch_image":
            return "🖼️"
        elif action == "chat":
            return "💬"
        elif action == "sing":
            return "🎤"
        elif action and action.startswith("video:"):
            va = action[len("video:"):]
            return {"大笑": "😂", "跳舞": "💃", "飞踢": "🦶"}.get(va, "🎬")
        return "▪️"

    def _add_menu_item(self, menu, text, command, disabled=False):
        """添加一个菜单项（深色圆润 + 悬停高亮）"""
        item = tk.Label(menu, text=text, bg=MENU_BG,
                        fg="#9A9A9A" if disabled else "#E8E8E8",
                        font=("Microsoft YaHei", 11),
                        anchor="w", padx=22, pady=9,
                        cursor="hand2" if (command and not disabled) else "arrow")
        item.pack(fill="x")
        if command and not disabled:
            item.bind("<Enter>", lambda e, w=item: w.config(bg=MENU_HOVER))
            item.bind("<Leave>", lambda e, w=item: w.config(bg=MENU_BG))
            item.bind("<Button-1>", lambda e, c=command: (
                self._close_custom_menu(), c()))

    def _add_menu_sep(self, menu):
        """菜单分隔线"""
        tk.Frame(menu, bg=MENU_SEP, height=1).pack(fill="x", padx=10, pady=2)

    def _close_custom_menu(self):
        """关闭自定义菜单"""
        if self._custom_menu:
            try:
                self._custom_menu.destroy()
            except Exception:
                pass
            self._custom_menu = None

    def _make_menu_command(self, action):
        """将 profile 中的 action 转为实际方法"""
        if action == "switch_image":
            return lambda: self.switch_pet(1)
        elif action == "chat":
            return self.chat_with_naiwa
        elif action == "sing":
            return self.start_singing
        elif action and action.startswith("video:"):
            video_action = action[len("video:"):]
            return lambda va=video_action: self.play_pet_video(va)
        return lambda: None

    # ========== 视频播放（通用：大笑/跳舞/飞踢） ==========

    def play_pet_video(self, action_name):
        """播放宠物视频动作（大笑/跳舞/飞踢），绿幕抠图透明 + 音频"""
        vinfo = self.profile["videos"].get(action_name)
        if not vinfo:
            return
        video_file = vinfo["file"]
        audio_file = vinfo.get("audio_file")

        if self.video_playing:
            self.stop_video_playback()
        if self._speech_active:
            self.stop_speech()
        if self.physics.active:
            self.physics.stop()
            self._restore_physics_appearance()
        if not os.path.exists(video_file):
            return

        self.float_paused = True
        self.is_animating = True

        self._pet_geo = (
            self.pet_width, self.pet_height,
            self.window.winfo_x(), self.window.winfo_y(),
        )

        try:
            self._video_reader = imageio.get_reader(video_file)
        except Exception:
            self._restore_pet_ui()
            return

        meta = self._video_reader.get_meta_data()
        fps = meta.get("fps", 30)
        vw, vh = meta.get("size", (1920, 1080))
        self._video_frame_delay = max(16, int(1000 / fps))

        display_w = vinfo["width"]
        display_h = int(display_w * vh / vw)
        scr_w = self.window.winfo_screenwidth()
        scr_h = self.window.winfo_screenheight()
        if display_w > scr_w - 40:
            display_w = scr_w - 40; display_h = int(display_w * vh / vw)
        if display_h > scr_h - 40:
            display_h = scr_h - 40; display_w = int(display_h * vw / vh)

        _, _, pet_x, pet_y = self._pet_geo
        cx = pet_x + self.pet_width // 2; cy = pet_y + self.pet_height // 2
        new_x = max(0, cx - display_w // 2); new_y = max(0, cy - display_h // 2)
        self.window.geometry(f"{display_w}x{display_h}+{new_x}+{new_y}")

        self.video_playing = True
        self._video_queue = queue.Queue(maxsize=6)
        self._video_thread = threading.Thread(
            target=self._decode_video_thread,
            args=(display_w, display_h), daemon=True,
        )
        self._video_thread.start()
        # 音频异步准备（视频先播，不阻塞主线程）
        self._prepare_audio_async(self._on_video_audio_ready, video_file, audio_file)
        self.window.after(50, lambda: self._start_video_playback(None))

    def _on_video_audio_ready(self, wav):
        """视频音频异步就绪后播放"""
        if self.video_playing:
            self._play_audio_wav(wav)

    def _prepare_audio_async(self, callback, *audio_args):
        """后台线程准备音频 wav（避免首次转换阻塞主线程），完成后主线程回调"""
        def work():
            try:
                wav = self._ensure_audio_wav(*audio_args)
                self.window.after(0, lambda: callback(wav))
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()

    def _play_audio_wav(self, wav):
        """主线程播放 wav（异步音频就绪后的回调）"""
        if not self.audio_ok:
            return
        try:
            pygame.mixer.music.load(wav)
            pygame.mixer.music.play()
        except Exception:
            pass

    def _prewarm_songs(self):
        """后台预转换所有歌曲 wav，减少首次切歌卡顿"""
        for s in self._sing_songs:
            try:
                self._ensure_audio_wav(s)
            except Exception:
                pass

    def _ensure_audio_wav(self, video_file, audio_file=None):
        """准备音频 wav（缓存到临时目录）。
        优先用独立音频文件，其次用视频自带音轨自动提取。
        """
        src = audio_file if (audio_file and os.path.exists(audio_file)) else video_file
        # 缓存键含文件大小+mtime，音频更新后自动重新转换
        try:
            st = os.stat(src)
            key = f"{os.path.abspath(src)}_{st.st_size}_{int(st.st_mtime)}"
        except Exception:
            key = os.path.abspath(src)
        h = hashlib.md5(key.encode()).hexdigest()[:12]
        wav = os.path.join(tempfile.gettempdir(), f"naiwa_audio_{h}.wav")
        if not os.path.exists(wav):
            try:
                ff = imageio_ffmpeg.get_ffmpeg_exe()
                extras = [] if src == video_file and not audio_file else ["-vn"]
                cmd = [ff, "-y", "-i", src] + extras + [
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

        # 开始播放音频（wav_path 为 None 时不播放，如唱歌模式静音视频）
        if wav_path and self.audio_ok:
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
            # 视频播完：唱歌模式循环重播，否则恢复宠物
            if self._video_loop:
                self._restart_video_loop()
            else:
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

    # ========== 大狗蓄力机制 ==========

    def _load_charge_audio(self):
        """预加载蓄力音频（mp3→wav→numpy 数组）"""
        charge = self.profile.get("charge", {})
        for name, src in [("dogdog", charge.get("dogdog")), ("wolf", charge.get("wolf"))]:
            if not src or not os.path.exists(src):
                continue
            try:
                wav = self._mp3_to_wav(src)
                snd = pygame.mixer.Sound(wav)
                self._charge_audio[name] = pygame.sndarray.samples(snd)
            except Exception:
                pass

    def _mp3_to_wav(self, src):
        """mp3 → wav（缓存到临时目录，缓存键含文件大小+mtime，音效更新自动重新转换）"""
        try:
            st = os.stat(src)
            key = f"{os.path.abspath(src)}_{st.st_size}_{int(st.st_mtime)}"
        except Exception:
            key = os.path.abspath(src)
        h = hashlib.md5(key.encode()).hexdigest()[:12]
        wav = os.path.join(tempfile.gettempdir(), f"naiwa_{h}.wav")
        if not os.path.exists(wav):
            try:
                ff = imageio_ffmpeg.get_ffmpeg_exe()
                subprocess.run([ff, "-y", "-i", src, "-acodec", "pcm_s16le",
                                "-ar", "44100", "-ac", "2", wav],
                               capture_output=True, check=True)
            except Exception:
                pass
        return wav

    def _resample_audio(self, audio, speed):
        """变速重采样：speed>1 加速（变短变急促），<1 减速（拉长变低沉）"""
        if abs(speed - 1.0) < 0.01:
            return audio
        n = max(1, int(len(audio) / speed))
        idx = np.linspace(0, len(audio) - 1, n)
        i0 = idx.astype(np.int32)
        i1 = np.minimum(i0 + 1, len(audio) - 1)
        if audio.ndim > 1:
            frac = (idx - i0)[:, None]
        else:
            frac = idx - i0
        res = audio[i0] * (1 - frac) + audio[i1] * frac
        return res.astype(audio.dtype)

    def _start_charge(self):
        """按住开始蓄力：播放 dogdog，每次循环加速"""
        if self._charging or "dogdog" not in self._charge_audio:
            return
        self._charging = True
        self._charge_start = time.time()
        self._charge_level = 1
        self._play_dogdog(1.0)

    def _play_dogdog(self, speed):
        """播放蓄力音（指定速度），播完精确调度下一段（无停顿）"""
        try:
            audio = self._resample_audio(self._charge_audio["dogdog"], speed)
            self._dogdog_sound = pygame.sndarray.make_sound(audio)
            self._dogdog_sound.play()
            # 按变速后时长精确调度，播完立即加速重播，无检测停顿
            dur_ms = max(10, int(self._dogdog_sound.get_length() * 1000))
            self._dogdog_check = self.window.after(dur_ms, self._check_dogdog)
        except Exception:
            pass

    def _check_dogdog(self):
        """蓄力音循环：播完一次就立即加速重播"""
        if not self._charging:
            return
        self._charge_level += 1
        max_speed = self.profile["charge"].get("max_speed", 2.5)
        speed = min(1.0 + self.profile["charge"].get("speedup", 0.15) * (self._charge_level - 1),
                    max_speed)
        self._play_dogdog(speed)

    def _release_charge(self):
        """松开蓄力：停止 dogdog，形象 dog1→dog2，播放 wolf（越久越慢）"""
        if not self._charging:
            return
        self._charging = False
        if self._dogdog_check:
            try:
                self.window.after_cancel(self._dogdog_check)
            except Exception:
                pass
            self._dogdog_check = None
        try:
            if self._dogdog_sound is not None:
                self._dogdog_sound.stop()
        except Exception:
            pass

        # 切换形象：dog1 → dog2
        charge = self.profile.get("charge", {})
        release_img = charge.get("release_image")
        if release_img and os.path.exists(release_img):
            self._apply_release_image(release_img)

        # 播放 wolf：点击过短→快放；蓄力越久→越慢；播完恢复 dog1
        if "wolf" in self._charge_audio:
            duration = time.time() - self._charge_start
            fast_th = charge.get("wolf_fast_threshold", 0.5)
            fast_max = charge.get("wolf_fast_max", 1.8)
            slow = charge.get("wolf_slow", 0.06)
            min_spd = charge.get("wolf_min_speed", 0.5)
            if duration < fast_th:
                # 点击过短松开：快放（越短越快，最短为 fast_max 倍速）
                t = max(0.0, duration / fast_th) if fast_th > 0 else 1.0
                wolf_speed = fast_max - (fast_max - 1.0) * t
            else:
                # 正常蓄力：越久越慢
                wolf_speed = max(min_spd, 1.0 - duration * slow)
            try:
                audio = self._resample_audio(self._charge_audio["wolf"], wolf_speed)
                # 音量放大 1.5 倍（防溢出）
                audio = np.clip(audio.astype(np.float32) * 1.5,
                                -32768, 32767).astype(np.int16)
                self._wolf_sound = pygame.sndarray.make_sound(audio)
                self._wolf_sound.play()
                wolf_dur = max(10, int(self._wolf_sound.get_length() * 1000))
                self._wolf_check = self.window.after(wolf_dur, self._restore_dog_idle)
            except Exception:
                pass

    def _restore_dog_idle(self):
        """wolf 播完，恢复 dog1 形象"""
        if self._charging:
            return  # 又按下蓄力了
        img = self.profile["images"][0]
        if os.path.exists(img):
            self._apply_release_image(img)

    def _apply_release_image(self, imgfile):
        """加载释放后的形象（dog2），并更新窗口尺寸"""
        try:
            img = Image.open(imgfile).convert("RGBA")
            h = int(img.height * PET_DISPLAY_WIDTH / img.width)
            img = img.resize((PET_DISPLAY_WIDTH, h), Image.LANCZOS)
            arr = np.array(img)
            a = arr[..., 3].astype(np.uint8)
            bg = a < PET_ALPHA_THRESHOLD
            arr[..., 3] = 255
            arr[bg] = [255, 0, 255, 255]
            self.original_image = Image.fromarray(arr).convert("RGB")

            # 保持窗口中心
            cx = self.window.winfo_x() + self.pet_width // 2
            cy = self.window.winfo_y() + self.pet_height // 2
            self.tk_image = ImageTk.PhotoImage(self.original_image)
            self.pet_width = self.tk_image.width()
            self.pet_height = self.tk_image.height()
            self.label.configure(image=self.tk_image)
            new_x = max(0, cx - self.pet_width // 2)
            new_y = max(0, cy - self.pet_height // 2)
            self.window.geometry(f"{self.pet_width}x{self.pet_height}+{new_x}+{new_y}")
            self.base_x = new_x
            self.base_y = new_y
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
            f"{self.profile['name']}已陪伴你 {self.get_total_minutes()} 分钟",
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
        if self._speech_active:
            self.stop_speech()

        if not self.is_api_configured():
            self.show_speech_bubble("本蛙还不会说话～主菜单已打开，填上你的 API Key 就能聊啦！")
            self.open_main_menu()
            return

        cfg = self.load_api_config()

        # 弹出自定义输入窗
        dialog = ChatDialog(self.window, self.profile["name"])
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

    def _build_persona_prompt(self):
        """根据当前宠物的人格设定生成 system prompt"""
        p = self.profile["persona"]
        return (
            f"你叫{p['name']}，一只有点{p['personality']}的桌面宠物。"
            f"背景：{p['background']}。{p['style']}。"
            f"你喜欢的：{'、'.join(p['likes'])}；你讨厌的：{'、'.join(p['dislikes'])}。"
        )

    def load_chat_history(self):
        """从用户数据目录读取对话记忆"""
        try:
            with open(CHAT_HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
                return history if isinstance(history, list) else []
        except Exception:
            return []

    def save_chat_history(self, history):
        """保存对话记忆到用户数据目录"""
        try:
            with open(CHAT_HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def remember(self, role, content):
        """记录一条对话，保留最近若干条"""
        history = self.load_chat_history()
        history.append({"role": role, "content": content})
        history = history[-MEMORY_MAX_MESSAGES:]
        self.save_chat_history(history)

    def forget_all(self):
        """清空对话记忆"""
        self.save_chat_history([])

    def _api_chat_worker(self, cfg, prompt):
        """后台线程：调用 OpenAI 兼容 API（带人格 + 记忆），结果放入队列"""
        try:
            url = cfg["base_url"].rstrip("/")
            if not url.endswith("/v1"):
                url += "/v1"
            url += "/chat/completions"

            # 人格 prompt + 历史记忆 + 当前输入
            # （借鉴 airi：给用户消息加时间前缀，让奶蛙感知时间）
            messages = [{"role": "system", "content": self._build_persona_prompt()}]
            messages.extend(self.load_chat_history())
            now_str = time.strftime("%Y-%m-%d %H:%M")
            messages.append({"role": "user", "content": f"[{now_str}] {prompt}"})

            payload = {
                "model": cfg["model"],
                "messages": messages,
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
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            reply = data["choices"][0]["message"]["content"].strip()
            if not reply:
                reply = "本蛙没听清...你再说一遍？"

            # 存入记忆（记住这次对话）
            self.remember("user", prompt)
            self.remember("assistant", reply)

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
        """主线程轮询 API 结果队列（每 200ms），根据宠物说话方式回复"""
        try:
            while not self._api_result_queue.empty():
                result = self._api_result_queue.get_nowait()
                method = self.profile.get("speech_method")
                if method == "laugh":
                    self.speak_with_laugh(result)   # 奶蛙：大笑音效说话
                else:
                    self.show_speech_bubble(result)  # 其他：纯文字气泡
        except Exception:
            pass
        self._api_poll_job = self.window.after(200, self._api_poll)

    # ========== 唱歌系统（凑企鹅） ==========

    def _load_song_list(self):
        """加载音乐文件夹里的歌曲列表"""
        folder = self.profile.get("music", {}).get("folder", "")
        if not folder or not os.path.isdir(folder):
            return
        exts = (".mp3", ".m4a", ".wav", ".ogg", ".flac")
        self._sing_songs = sorted(
            os.path.join(folder, f) for f in os.listdir(folder)
            if f.lower().endswith(exts)
        )

    def start_singing(self):
        """开始唱歌/听歌：播放音乐 + 视频或形象切换 + 显示控制栏"""
        if self._singing:
            # 已在听歌：只有控制栏 ✕ 能退出
            self.show_speech_bubble("正在听歌中～点控制栏 ✕ 退出")
            return
        if not self._sing_songs:
            self.show_speech_bubble("没有找到歌曲～")
            return

        self._singing = True
        self._sing_paused = False
        self.stop_speech()

        # 播放音乐（异步准备，避免首次转换阻塞 UI）
        if self.audio_ok:
            self._prepare_audio_async(self._play_audio_wav,
                                      self._sing_songs[self._sing_index])

        music_cfg = self.profile.get("music", {})
        if music_cfg.get("sing_video"):
            # 有视频：循环播放（凑企鹅）
            self._video_loop = True
            self._play_sing_video()
        elif music_cfg.get("sing_image"):
            # 无视频：切换形象（大狗 → dog3）
            sing_img = music_cfg["sing_image"]
            if os.path.exists(sing_img):
                self._apply_release_image(sing_img)

        # 显示控制栏（只有 ✕ 能退出听歌）
        self._show_sing_bar()

    def _play_sing_video(self):
        """循环播放唱歌视频"""
        vinfo = self.profile.get("music", {})
        video = vinfo.get("sing_video")
        width = vinfo.get("video_width", 500)
        if not video or not os.path.exists(video):
            return
        # 用通用视频播放器，但静音（音乐独立播放）
        if self.video_playing:
            self.stop_video_playback()
        self._pet_geo = (self.pet_width, self.pet_height,
                         self.window.winfo_x(), self.window.winfo_y())
        try:
            self._video_reader = imageio.get_reader(video)
        except Exception:
            self._restore_pet_ui()
            return
        meta = self._video_reader.get_meta_data()
        fps = meta.get("fps", 30)
        vw, vh = meta.get("size", (1920, 1080))
        self._video_frame_delay = max(16, int(1000 / fps))
        display_w = width
        display_h = int(display_w * vh / vw)
        scr_w = self.window.winfo_screenwidth()
        scr_h = self.window.winfo_screenheight()
        if display_w > scr_w - 40:
            display_w = scr_w - 40; display_h = int(display_w * vh / vw)
        if display_h > scr_h - 40:
            display_h = scr_h - 40; display_w = int(display_h * vw / vh)
        _, _, pet_x, pet_y = self._pet_geo
        cx = pet_x + self.pet_width // 2; cy = pet_y + self.pet_height // 2
        new_x = max(0, cx - display_w // 2); new_y = max(0, cy - display_h // 2)
        self.window.geometry(f"{display_w}x{display_h}+{new_x}+{new_y}")
        self.video_playing = True
        self._video_queue = queue.Queue(maxsize=6)
        self._video_thread = threading.Thread(
            target=self._decode_video_thread, args=(display_w, display_h), daemon=True)
        self._video_thread.start()
        self.window.after(50, lambda: self._start_video_playback(None))

    def _restart_video_loop(self):
        """唱歌视频播完，重新循环播放"""
        if not self._singing or not self._video_loop:
            return
        self._play_sing_video()

    def _show_sing_bar(self):
        """在宠物下方显示唱歌控制栏（歌曲名 + 暂停/上一首/下一首/退出）"""
        self._close_sing_bar()
        bar = tk.Toplevel(self.window)
        bar.overrideredirect(True)
        bar.wm_attributes("-topmost", True)
        bar.configure(bg=MENU_BG)

        # 歌曲名
        song_name = os.path.splitext(os.path.basename(
            self._sing_songs[self._sing_index]))[0] if self._sing_songs else ""
        self._sing_name_lbl = tk.Label(bar, text=f"🎵 {song_name}",
                                       bg=MENU_BG, fg="#E8E8E8",
                                       font=("Microsoft YaHei", 9), padx=10, pady=4,
                                       anchor="w")
        self._sing_name_lbl.pack(fill="x")

        # 控制按钮行（pack 横向排列，避免按钮被裁剪）
        btn_row = tk.Frame(bar, bg=MENU_BG)
        btn_row.pack()
        self._sing_btn_prev = self._make_sing_btn(btn_row, "⏮", self._sing_prev)
        self._sing_btn_prev.pack(side="left")
        self._sing_btn_pause = self._make_sing_btn(btn_row, "⏸", self._sing_toggle_pause)
        self._sing_btn_pause.pack(side="left")
        self._sing_btn_next = self._make_sing_btn(btn_row, "⏭", self._sing_next)
        self._sing_btn_next.pack(side="left")
        self._sing_btn_exit = self._make_sing_btn(btn_row, "✕", self.stop_singing)
        self._sing_btn_exit.pack(side="left")

        self._sing_bar = bar
        self._position_sing_bar()

    def _make_sing_btn(self, parent, text, cmd):
        """唱歌控制按钮（悬停高亮）"""
        btn = tk.Label(parent, text=text, bg=MENU_BG, fg="white",
                       font=("Segoe UI", 14), padx=16, pady=3, cursor="hand2")
        btn.bind("<Enter>", lambda e, w=btn: w.config(bg=MENU_HOVER))
        btn.bind("<Leave>", lambda e, w=btn: w.config(bg=MENU_BG))
        btn.bind("<Button-1>", lambda e, c=cmd: c())
        return btn

    def _position_sing_bar(self):
        """控制栏位置：宠物/视频窗口正下方（宽度自适应内容）"""
        if not self._sing_bar:
            return
        pet_x = self.window.winfo_rootx()
        pet_y = self.window.winfo_rooty()
        cur_w = self.window.winfo_width() or self.pet_width
        cur_h = self.window.winfo_height() or self.pet_height
        self._sing_bar.update_idletasks()
        bar_w = self._sing_bar.winfo_reqwidth()
        bar_h = self._sing_bar.winfo_reqheight()
        sw = self.window.winfo_screenwidth()
        sh = self.window.winfo_screenheight()
        bx = pet_x + cur_w // 2 - bar_w // 2
        by = pet_y + cur_h + 5
        bx = max(0, min(bx, sw - bar_w))
        by = max(0, min(by, sh - bar_h))
        self._sing_bar.geometry(f"{bar_w}x{bar_h}+{bx}+{by}")

    def _close_sing_bar(self):
        self._sing_btn_prev = None
        self._sing_btn_pause = None
        self._sing_btn_next = None
        self._sing_name_lbl = None
        if self._sing_bar:
            try:
                self._sing_bar.destroy()
            except Exception:
                pass
            self._sing_bar = None

    def _sing_toggle_pause(self):
        """暂停/恢复唱歌"""
        if not self._singing:
            return
        self._sing_paused = not self._sing_paused
        if self.audio_ok:
            try:
                if self._sing_paused:
                    pygame.mixer.music.pause()
                else:
                    pygame.mixer.music.unpause()
            except Exception:
                pass
        # 更新暂停按钮
        if self._sing_btn_pause:
            try:
                self._sing_btn_pause.config(
                    text="▶" if self._sing_paused else "⏸")
            except Exception:
                pass

    def _sing_prev(self):
        """上一首"""
        if not self._sing_songs:
            return
        self._sing_index = (self._sing_index - 1) % len(self._sing_songs)
        self._restart_song()

    def _sing_next(self):
        """下一首"""
        if not self._sing_songs:
            return
        self._sing_index = (self._sing_index + 1) % len(self._sing_songs)
        self._restart_song()

    def _restart_song(self):
        """切换歌曲并重新播放（异步准备音频，避免切歌卡顿）"""
        self._sing_paused = False
        if self.audio_ok:
            self._prepare_audio_async(self._play_audio_wav,
                                      self._sing_songs[self._sing_index])
        if self._sing_btn_pause:
            try:
                self._sing_btn_pause.config(text="⏸")
            except Exception:
                pass
        # 更新歌曲名
        if self._sing_name_lbl:
            try:
                song_name = os.path.splitext(os.path.basename(
                    self._sing_songs[self._sing_index]))[0]
                self._sing_name_lbl.config(text=f"🎵 {song_name}")
            except Exception:
                pass

    def stop_singing(self):
        """停止唱歌"""
        self._singing = False
        self._video_loop = False
        if self.audio_ok:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
        self._close_sing_bar()
        if self.video_playing:
            self.stop_video_playback()
        # 听歌时切换了形象（大狗 dog3）→ 恢复默认形象
        if self.profile.get("music", {}).get("sing_image"):
            base_img = self.profile["images"][0]
            if os.path.exists(base_img):
                self._apply_release_image(base_img)
        elif not self.video_playing:
            self._restore_pet_ui()

    # ========== 奶蛙笑声说话 ==========

    def speak_with_laugh(self, text):
        """奶蛙用笑声"说话"：逐字显示 + 笑声随标点停顿 + 淡出收尾"""
        self.stop_speech()  # 打断旧的说话
        self.close_greet_bubble()

        # 播放大笑（作为奶蛙的声音）
        if self.audio_ok:
            try:
                pygame.mixer.music.load(self._ensure_audio_wav())
                pygame.mixer.music.play()
            except Exception:
                pass

        # 创建逐字气泡
        self._speech_active = True
        self._speech_text = text
        self._speech_visible = ""
        self._speech_idx = 0
        self._create_speech_bubble()
        self._speech_tick()

    def _create_speech_bubble(self):
        """创建逐字显示的对话气泡"""
        bubble = tk.Toplevel(self.window)
        bubble.overrideredirect(True)
        bubble.wm_attributes("-topmost", True)
        bubble.wm_attributes("-toolwindow", True)
        bubble.configure(bg="#FFFBF0")
        bubble.transient(self.window)

        max_chars = 22  # 每行约 22 字
        bubble_w = max_chars * 16 + 28
        bubble_h = 100
        bubble.geometry(f"{bubble_w}x{bubble_h}")

        self._speech_var = tk.StringVar(value="")
        tk.Label(
            bubble, textvariable=self._speech_var, bg="#FFFBF0", fg="#4A3728",
            font=("Microsoft YaHei", 12), justify="left", anchor="nw",
            wraplength=bubble_w - 28, padx=14, pady=10,
        ).pack(fill="both", expand=True)

        # 位置：奶蛙上方
        pet_x = self.window.winfo_rootx()
        pet_y = self.window.winfo_rooty()
        bx = pet_x + self.pet_width // 2 - bubble_w // 2
        by = pet_y - bubble_h - 10
        bx = max(0, min(bx, self.window.winfo_screenwidth() - bubble_w))
        by = max(0, by)
        bubble.geometry(f"+{bx}+{by}")

        self._speech_bubble = bubble

    def _speech_tick(self):
        """逐字推进文字，标点处笑声同步停顿"""
        if not self._speech_active:
            return
        i = self._speech_idx
        if i >= len(self._speech_text):
            # 全部显示完 → 淡出笑声
            self._fadeout_speech()
            return

        ch = self._speech_text[i]
        self._speech_visible += ch
        self._speech_idx += 1
        try:
            self._speech_var.set(self._speech_visible)
        except Exception:
            pass

        if ch in SPEECH_PUNCT:
            # 标点停顿：文字和笑声同步暂停
            if self.audio_ok:
                try:
                    pygame.mixer.music.pause()
                except Exception:
                    pass
            self._speech_job = self.window.after(SPEECH_PUNCT_PAUSE, self._speech_resume)
        else:
            self._speech_job = self.window.after(SPEECH_CHAR_DELAY, self._speech_tick)

    def _speech_resume(self):
        """标点停顿后恢复"""
        if not self._speech_active:
            return
        if self.audio_ok:
            try:
                pygame.mixer.music.unpause()
            except Exception:
                pass
        self._speech_job = self.window.after(SPEECH_CHAR_DELAY, self._speech_tick)

    def _fadeout_speech(self, vol=1.0):
        """笑声淡出收尾"""
        if not self._speech_active:
            return
        if self.audio_ok:
            try:
                if vol <= 0:
                    pygame.mixer.music.stop()
                else:
                    pygame.mixer.music.set_volume(max(vol - SPEECH_FADE_STEP, 0))
                    self._speech_job = self.window.after(
                        SPEECH_FADE_DELAY, lambda: self._fadeout_speech(vol - SPEECH_FADE_STEP))
                    return
            except Exception:
                pass
        # 淡出完成，关闭气泡并停留显示几秒
        self._speech_active = False
        self._speech_job = self.window.after(3000, self._close_speech_bubble)

    def stop_speech(self):
        """中断奶蛙说话（打断笑声 + 关闭气泡）"""
        self._speech_active = False
        if self._speech_job:
            try:
                self.window.after_cancel(self._speech_job)
            except Exception:
                pass
            self._speech_job = None
        if self.audio_ok:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
        self._close_speech_bubble()

    def _close_speech_bubble(self):
        """关闭说话气泡"""
        self._speech_job = None
        if self._speech_bubble:
            try:
                self._speech_bubble.destroy()
            except Exception:
                pass
            self._speech_bubble = None
        self._speech_var = None

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

    # ========== 宠物切换 ==========

    def switch_to_pet(self, pet_id):
        """切换到另一个桌宠（os.execv 直接替换进程，最可靠）"""
        if pet_id not in PET_PROFILES or pet_id == self.profile["id"]:
            return
        save_active_pet(pet_id)   # 写入新宠物
        self.save_total_minutes()  # 保存陪伴时长（execv 后无清理机会）
        if getattr(sys, "frozen", False):
            os.execv(sys.executable, [sys.executable])
        else:
            os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)])

    # ========== 退出 ==========

    def quit(self):
        """退出程序"""
        self.video_playing = False
        self._charging = False
        self._singing = False
        self._video_loop = False
        if self._dogdog_check:
            try:
                self.window.after_cancel(self._dogdog_check)
            except Exception:
                pass
        if self._wolf_check:
            try:
                self.window.after_cancel(self._wolf_check)
            except Exception:
                pass
        if self._dogdog_sound is not None:
            try:
                self._dogdog_sound.stop()
            except Exception:
                pass
        if self._wolf_sound is not None:
            try:
                self._wolf_sound.stop()
            except Exception:
                pass
        self.stop_singing()
        self.stop_speech()
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
    # 主题配色（现代暖色卡片式）
    BG       = "#F7F3EE"   # 暖米白主背景
    CARD     = "#FFFFFF"   # 卡片白底
    HEADER   = "#FF8C42"   # 活力橙标题栏
    BTN      = "#FF8C42"
    BTN_HOV  = "#FFA266"
    TEXT     = "#4A3728"
    SUB      = "#8A7A66"   # 次级文字
    BORDER   = "#E8DCC8"   # 卡片边框
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
        self.win.title(f"{owner.profile['name']}桌宠 · 主菜单")
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

    def _make_card(self, parent):
        """创建卡片容器（白底 + 浅边框）"""
        card = tk.Frame(parent, bg=self.CARD,
                        highlightbackground=self.BORDER,
                        highlightthickness=1, padx=16, pady=12)
        return card

    def _card_title(self, card, text):
        """卡片标题"""
        tk.Label(card, text=text, bg=self.CARD, fg=self.TEXT,
                 font=("Microsoft YaHei", 12, "bold")).pack(anchor="w", pady=(0, 10))

    def _build_ui(self):
        # 标题栏（橙色，白字）
        header = tk.Frame(self.win, bg=self.HEADER, height=56)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header, text=f"🐾  {self.owner.profile['name']}桌宠 · 主菜单",
            bg=self.HEADER, fg="white",
            font=("Microsoft YaHei", 15, "bold"),
        ).pack(side="left", padx=20)

        # 主体内容（卡片式分区）
        body = tk.Frame(self.win, bg=self.BG, padx=20, pady=14)
        body.pack(fill="both", expand=True)

        # ---- 卡片1：选择桌宠 ----
        pet_card = self._make_card(body)
        pet_card.pack(fill="x", pady=(0, 12))
        self._card_title(pet_card, "🐾  选择你的桌宠")
        pet_row = tk.Frame(pet_card, bg=self.CARD)
        pet_row.pack(fill="x")
        current_pet = self.owner.profile["id"]
        pet_emoji = {"naiwa": "🐸", "tomorin": "🐧", "dog": "🐶"}
        for pid in PET_PROFILES:
            name = PET_PROFILES[pid]["name"]
            emoji = pet_emoji.get(pid, "🐾")
            if pid == current_pet:
                btn = tk.Button(
                    pet_row, text=f"{emoji} {name} ✓", bg=self.BTN, fg="white",
                    activebackground=self.BTN_HOV,
                    font=("Microsoft YaHei", 11, "bold"),
                    bd=0, padx=14, pady=5, cursor="hand2",
                )
                btn.pack(side="left", padx=5)
            else:
                btn = self._make_button(pet_row, f"{emoji} {name}",
                                        lambda p=pid: self._on_switch_pet(p))
                btn.pack(side="left", padx=5)

        # ---- 卡片2：API 配置 ----
        api_card = self._make_card(body)
        api_card.pack(fill="x", pady=(0, 12))
        self._card_title(api_card, "⚙️  API 配置")
        self._add_row(api_card, "Base URL", "base_url", "https://api.deepseek.com")
        self._add_row(api_card, "API Key", "api_key", "sk-", password=True)
        self._add_row(api_card, "模型名称", "model", "deepseek-chat")

        # 按钮行
        btn_row = tk.Frame(api_card, bg=self.CARD)
        btn_row.pack(fill="x", pady=(12, 4))
        self._make_button(btn_row, "💾 保存配置", self._on_save).pack(side="left")
        self._make_button(btn_row, "🔗 测试连接", self._on_test).pack(side="left", padx=8)
        mem_row = tk.Frame(api_card, bg=self.CARD)
        mem_row.pack(fill="x", pady=(2, 0))
        self._make_button(mem_row, f"🧹 清空{self.owner.profile['name']}记忆",
                          self._on_forget).pack(side="left")

        # 状态标签
        self.status_lbl = tk.Label(
            api_card, text="", bg=self.CARD, fg="#3A8F5F",
            font=("Microsoft YaHei", 11),
        )
        self.status_lbl.pack(anchor="w", pady=(8, 0))
        self._update_status()

        # ---- 卡片3：使用说明 ----
        help_card = self._make_card(body)
        help_card.pack(fill="x")
        self._card_title(help_card, "📖  使用说明")
        pname = self.owner.profile["name"]
        tips = [
            "1. 填写上方 API 配置并点击「保存配置」",
            f"2. 右键{pname} → 「对话」，输入想说的话",
            f"3. {pname}会以各自性格在气泡中回复你",
            "提示：支持任何 OpenAI 兼容接口",
        ]
        for tip in tips:
            tk.Label(
                help_card, text=tip, bg=self.CARD, fg=self.SUB,
                font=("Microsoft YaHei", 10),
            ).pack(anchor="w", pady=1)

    def _add_row(self, parent, label_text, key, placeholder, password=False):
        """配置表单项（标签 + 输入框）"""
        row = tk.Frame(parent, bg=self.CARD)
        row.pack(fill="x", pady=4)
        tk.Label(
            row, text=label_text, bg=self.CARD, fg=self.TEXT,
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
                        {"role": "system",
                         "content": f"你是一只叫{self.owner.profile['name']}的可爱桌宠。"},
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

    def _on_forget(self):
        """清空当前宠物的记忆"""
        self.owner.forget_all()
        self.status_lbl.config(text=f"🧹  {self.owner.profile['name']}的记忆已清空",
                               fg="#3A8F5F")

    def _on_switch_pet(self, pet_id):
        """切换到另一个桌宠"""
        name = PET_PROFILES[pet_id]["name"]
        self.status_lbl.config(text=f"🔄  正在切换到 {name}...", fg="#4A3728")
        self.win.update_idletasks()
        self.owner.switch_to_pet(pet_id)

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

    def __init__(self, parent, pet_name="奶蛙"):
        self.result = None  # 用户输入的结果
        self.pet_name = pet_name

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
            header, text=f"💬  和{self.pet_name}聊聊天", bg=self.HEADER, fg=self.TEXT,
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
            body, text=f"对{self.pet_name}说点什么吧：", bg=self.BG, fg=self.TEXT,
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
