# Windows 用户 · 5 分钟上手

> 不用懂 Python，**只要装一个 Python，然后双击 start.bat**。

---

## 步骤 1：装 Python（只做一次）

1. 打开 https://www.python.org/downloads/
2. 点 **"Download Python 3.13.x"**（黄色大按钮）
3. 双击下载的 .exe 安装包
4. ⚠️ **第一个界面务必勾上** `Add python.exe to PATH`（最下面）
5. 选 `Install Now` 等完成

> 没勾 PATH？卸载重装，勾上。

---

## 步骤 2：下载项目代码

方式 A（推荐）：如果你装了 Git
```cmd
git clone https://github.com/weiyuan0917-a11y/etf-dashboard.git
cd etf-dashboard
```

方式 B（不装 Git）：去 https://github.com/weiyuan0917-a11y/etf-dashboard 点 `Code` → `Download ZIP`，解压到任意目录

---

## 步骤 3：双击 `start.bat`

在项目根目录（能看到 `app.py` 和 `start.bat` 那个目录）双击 `start.bat`。

第一次会：
- 检查 Python（没装会弹下载页）
- 装依赖（1-3 分钟，**只这一次**）
- 启 streamlit 服务
- **自动打开浏览器**到 http://localhost:8501/

之后每次双击 **3 秒开页面**（依赖已装好）。

---

## 用完怎么关？

关掉那个黑色 cmd 窗口即可。`Ctrl+C` 也行。

---

## 常见问题

### Q1：双击 start.bat 一闪而过？
- 装 Python 时**没勾** "Add Python to PATH"
- 重装 Python，勾上，重启电脑

### Q2：浏览器没自动打开？
- 手动打开浏览器，地址栏输入 `http://localhost:8501/`

### Q3：8501 端口被占用？
start.bat 会自动换 8502。打开的浏览器会指错端口 → **看黑色窗口里显示的实际端口**（比如 "Local URL: http://localhost:8502"）。

### Q4：怎么升级到最新版？
项目根目录重新跑 `git pull`，再双击 start.bat。

### Q5：杀毒软件报警？
start.bat 只是调 Python 和 streamlit，没有任何可疑行为。如果报警是误报，加白名单即可。

### Q6：数据怎么更新？
进 web 页面 → 主页右上角 "⏱ 数据更新" 区块有"启动 ETF 清单更新 / 启动 实时行情更新"两个按钮，按一下后台跑，进度实时显示。

---

## 卸载

1. 关掉 streamlit 窗口
2. 删项目目录
3. （可选）卸载 Python：控制面板 → 程序和功能 → Python 3.13 → 卸载
