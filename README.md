# 🐸 奶蛙桌宠

一只住在你 Windows 桌面上的可爱小奶蛙。无边框透明悬浮、可以甩来甩去、陪你聊天、还会播放"奶龙大笑"！

## 写在前面
闲着用cc+dsapi跑了个奶蛙桌宠，功能很不完善，后续也许会优化，代码含人量为0，readme也是直接跑的

## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| 🪟 桌面悬浮 | 无边框透明窗口，始终置顶，不占任务栏 |
| 🖼️ 多形象 | pet1~pet3 三套形象，右键切换或每 20 分钟自动切换 |
| 🏀 物理甩动 | 拖动快速松手 → 奶蛙甩出去，重力下落、撞屏幕边缘反弹并挤压变形 |
| 🎤 大笑 | 右键 → 大笑，播放"奶龙大笑"视频（绿幕抠图透明，带音效），体型放大 1.5 倍 |
| 💬 对话 | 接入任意 OpenAI 兼容大模型 API，右键 → 对话，奶蛙以可爱风格气泡回复 |
| ⏱️ 陪伴时长 | 累计陪伴分钟数跨会话持久化，右键菜单查看 |
| 👋 问候气泡 | 启动时显示问候（时间 + 陪伴时长） |

## 🚀 快速开始

### 方式一：直接下载 exe（推荐）

1. 从 [Releases](../../releases) 下载最新版本压缩包
2. 解压到任意文件夹
3. 双击 `naiwa-pet.exe` 运行

> **素材文件必须与 exe 放在同一文件夹**（pet*.png、视频、音频文件）

### 方式二：源码运行

需要 Python 3.11+ 和 pip：

```bash
# 创建虚拟环境并安装依赖
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 运行
python pet.py
```

## 💬 配置 AI 对话

1. 右键奶蛙 → **主菜单**
2. 填写 API 配置：
   - **Base URL**：如 `https://api.deepseek.com`（支持任意 OpenAI 兼容接口）
   - **API Key**：你的密钥
   - **模型名称**：如 `deepseek-v4-flash`
3. 点击 **保存配置**
4. 右键奶蛙 → **对话**，开始聊天

## 🎮 操作指南

| 操作 | 效果 |
|------|------|
| 左键拖动 | 移动奶蛙 |
| 左键快速甩动松手 | 把奶蛙甩出去（物理飞行） |
| 右键 | 打开菜单：切换形象 / 对话 / 大笑 / 主菜单 / 退出 |

## 📦 从源码打包

```bash
.venv\Scripts\pip install pyinstaller
.venv\Scripts\pyinstaller --onefile --noconsole --name naiwa-pet \
  --icon exesign.ico \
  --add-data ".venv\Lib\site-packages\imageio_ffmpeg\binaries;imageio_ffmpeg\binaries" \
  --hidden-import imageio_ffmpeg \
  --hidden-import PIL._tkinter_finder \
  --copy-metadata imageio \
  pet.py
```

打包产物在 `dist/naiwa-pet.exe`，需与素材文件放在同一目录。

## 🛠️ 技术栈

- **语言**：Python 3.11
- **GUI**：tkinter（无边框透明窗口，magenta 色键透明）
- **视频**：imageio + imageio-ffmpeg（逐帧解码 + 绿幕色键抠图）
- **音频**：pygame
- **打包**：PyInstaller



