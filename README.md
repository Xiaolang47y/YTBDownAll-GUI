# YTBDownAll-GUI
基于[YTBDownAllScript](https://github.com/Xiaolang47y/YTBDownAllScript "YTBDownAllScript")制作的GUI版Youtube视频下载工具。

~~（其实不止Youtube能下载，yt-dlp支持的都能下）~~

主要基于yt-dlp ffmpeg pip python3等。

程序使用TRAE AI生成，请不放心使用。

配置文件存储于 `~/.config/ytbdownall/config.json`

#### 构建
运行此命令即可自动构建：`bash build.sh`
    
#### 支持功能
##### 环境管理
- 首次运行配置向导（欢迎 → 环境检测 → Cookie 设置 → 完成）
- 自动检测 yt-dlp / ffmpeg / deno / Python 环境
- 每个组件都有"安装"按钮，支持 Arch / Debian / Fedora 三种发行版
- 手动指定 yt-dlp / ffmpeg 可执行文件路径
- 设置中可重新检测环境

##### 下载内容选择
- 视频下载（MP4 最佳画质）
- 封面缩略图下载（JPG）
- SRT/VTT 字幕下载（点击按钮弹出语言选择窗口、互相独立）
- 音频提取（MP3）
- 每个链接可单独勾选

##### 字幕语言
- 支持 10 种语言：英语、简体中文、日语、繁体中文、韩语、西班牙语、法语、德语、俄语、葡萄牙语
- 设置中可配置默认字幕语言

##### 链接管理
- 大文本框批量输入链接（每行一个）
- 解析后以列表形式展示，每行显示链接 + 复选框
- 全选 / 取消全选 / 清空列表

##### 认证方式
- cookies.txt 文件（可浏览选择路径）
- Firefox 浏览器 Cookie
- Chrome 浏览器 Cookie
- 跳过认证
- 首次配置时询问，设置中可修改默认方式

##### 下载功能
- 失败项单独重试按钮
- 实时日志输出（成功绿色、失败红色高亮）
- 下载完成后显示 [标题] | [链接] 格式的结果列表

##### 保存与历史
- 每次下载可询问保存目录（可关闭）
- 设置默认保存目录
- 保存目录 / 历史记录目录都有"打开"按钮（调用系统文件管理器）
- 历史记录自动保存为 txt 文件，按时间命名
- 可设置历史记录保留数量（0 为不保存）
- 可设置历史记录保存目录

##### 设置
- 默认勾选配置（视频/封面/SRT/VTT/音频）
- 默认保存目录 + 每次询问开关
- 设置最大并发下载数
- 默认字幕语言
- 历史记录文件数量 + 保存目录
- 环境检测与重新检测

#### 已知问题
- 在程序运行时删除 `~/.config/ytbdownall/` 会导致程序卡住。

#### 待办事项
- 加入多语言支持
- 全选/取消全选改为单列生效

#### 图廊
<img width="900" height="728" alt="图片" src="https://github.com/user-attachments/assets/f368c5e2-327b-4385-aba7-e5a050092827" />
<img width="550" height="678" alt="图片" src="https://github.com/user-attachments/assets/8f4e9318-a750-4ed5-9d6b-baaf8bb25538" />
<img width="800" height="628" alt="图片" src="https://github.com/user-attachments/assets/812dc5fc-71b6-4b56-ad22-849e52481344" />
