#!/bin/bash
# 打包 YTBDownAllGUI 为可执行文件

echo "安装 PyInstaller..."
pip install -U pyinstaller --break-system-packages 2>/dev/null

echo "开始打包..."
cd "$(dirname "$0")"

pyinstaller --onefile \
    --windowed \
    --name "YTBDownAll" \
    --hidden-import tkinter \
    --hidden-import tkinter.ttk \
    --hidden-import tkinter.messagebox \
    --hidden-import tkinter.filedialog \
    --hidden-import tkinter.scrolledtext \
    YTBDownAllGUI.py

echo ""
echo "打包完成！可执行文件位于: dist/YTBDownAll"
