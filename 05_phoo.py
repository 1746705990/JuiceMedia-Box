import os
import json
from flask import Flask, render_template_string, send_from_directory, abort
from urllib.parse import quote, unquote

# ================= 配置区域 =================
IMAGE_ROOT = '/mnt'  # 你的图片根目录
PORT = 8090          # 端口号
VALID_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.heic'}
# ===========================================

app = Flask(__name__)

# SVG 图标资源
ICONS = {
    'folder': '''<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>''',
    'back': '''<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6"></polyline></svg>'''
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gallery Explorer</title>
    <style>
        :root {
            --bg-color: #121212;
            --card-bg: #1e1e1e;
            --text-color: #e0e0e0;
            --accent-color: #4a90e2;
            --folder-color: #FFC107;
        }
        body {
            margin: 0;
            padding: 20px;
            background-color: var(--bg-color);
            color: var(--text-color);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            user-select: none; /* 防止频繁点击时选中文本 */
        }

        /* 顶部导航栏 */
        .navbar {
            display: flex;
            align-items: center;
            padding-bottom: 20px;
            border-bottom: 1px solid #333;
            margin-bottom: 20px;
        }
        
        .breadcrumb {
            font-size: 1.1em;
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }
        
        .breadcrumb a {
            color: var(--text-color);
            text-decoration: none;
            padding: 4px 8px;
            border-radius: 4px;
            transition: background 0.2s;
        }
        
        .breadcrumb a:hover {
            background-color: #333;
            color: var(--accent-color);
        }
        
        .breadcrumb span { opacity: 0.5; }

        /* 网格布局 */
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
            gap: 15px;
        }

        /* 卡片样式 */
        .item {
            background-color: var(--card-bg);
            border-radius: 8px;
            overflow: hidden;
            transition: transform 0.2s, box-shadow 0.2s;
            cursor: pointer;
            display: flex;
            flex-direction: column;
            aspect-ratio: 1 / 1.15;
            position: relative;
        }

        .item:hover {
            transform: translateY(-4px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.4);
            background-color: #2a2a2a;
        }

        .thumb {
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            background: #000;
        }

        .thumb img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        .thumb svg {
            width: 64px;
            height: 64px;
            color: var(--folder-color);
        }
        
        .item.back-btn .thumb svg { color: #888; }

        .info {
            padding: 10px;
            font-size: 0.85em;
            text-align: center;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            background: var(--card-bg);
            border-top: 1px solid #333;
            color: #ccc;
        }

        /* 灯箱 (全屏查看) */
        .lightbox {
            display: none;
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0, 0, 0, 0.98);
            z-index: 1000;
            justify-content: center;
            align-items: center;
        }
        .lightbox.active { display: flex; }
        
        .lightbox img {
            max-width: 95vw; max-height: 90vh;
            box-shadow: 0 0 30px rgba(0,0,0,1);
            transition: opacity 0.2s;
        }

        /* 计数器样式 (新增) */
        .counter {
            position: absolute;
            top: 20px;
            left: 20px;
            background: rgba(255, 255, 255, 0.1);
            color: #fff;
            padding: 5px 12px;
            border-radius: 20px;
            font-family: monospace;
            font-size: 14px;
            backdrop-filter: blur(4px);
            border: 1px solid rgba(255,255,255,0.1);
        }
    </style>
</head>
<body>

    <nav class="navbar">
        <div class="breadcrumb">
            <a href="/">Home</a>
            {% for part in breadcrumbs %}
                <span>/</span>
                <a href="/browse/{{ part.path }}">{{ part.name }}</a>
            {% endfor %}
        </div>
    </nav>

    <div class="grid">
        {% if current_path != '' %}
        <div class="item back-btn" onclick="location.href='/browse/{{ parent_path }}'">
            <div class="thumb">{{ icons.back|safe }}</div>
            <div class="info">.. (返回上一级)</div>
        </div>
        {% endif %}

        {% for folder in folders %}
        <div class="item" onclick="location.href='/browse/{{ folder.path }}'">
            <div class="thumb">{{ icons.folder|safe }}</div>
            <div class="info">{{ folder.name }}</div>
        </div>
        {% endfor %}

        {% for img in images %}
        <div class="item" onclick="openLightbox({{ loop.index0 }})">
            <div class="thumb">
                <img src="/file/{{ img.path }}" loading="lazy" alt="{{ img.name }}">
            </div>
            <div class="info">{{ img.name }}</div>
        </div>
        {% endfor %}
    </div>

    <div class="lightbox" id="lightbox" onclick="if(event.target === this) closeLightbox()">
        <div class="counter" id="counterDisplay"></div>
        <img id="lbImg" src="">
    </div>

    <script>
        const images = {{ images | tojson }};
        let currentIndex = 0;
        const lightbox = document.getElementById('lightbox');
        const lbImg = document.getElementById('lbImg');
        const counterDisplay = document.getElementById('counterDisplay');

        function openLightbox(index) {
            if (images.length === 0) return;
            currentIndex = index;
            updateImage();
            lightbox.classList.add('active');
            document.body.style.overflow = 'hidden';
        }

        function closeLightbox() {
            lightbox.classList.remove('active');
            document.body.style.overflow = '';
            lbImg.src = '';
        }

        function updateImage() {
            // 更新图片
            lbImg.src = '/file/' + images[currentIndex].path;
            
            // 更新计数器文字 (当前索引+1 / 总数)
            counterDisplay.innerText = `${currentIndex + 1} / ${images.length}`;
        }

        function nextImage() {
            if (images.length === 0) return;
            currentIndex = (currentIndex + 1) % images.length;
            updateImage();
        }

        function prevImage() {
            if (images.length === 0) return;
            currentIndex = (currentIndex - 1 + images.length) % images.length;
            updateImage();
        }

        // 键盘控制
        document.addEventListener('keydown', (e) => {
            if (!lightbox.classList.contains('active')) return;
            
            if (e.key === 'ArrowRight') nextImage();
            if (e.key === 'ArrowLeft') prevImage();
            if (e.key === 'Escape') closeLightbox();
        });
        
        // 简单的触摸支持
        let touchStartX = 0;
        lightbox.addEventListener('touchstart', e => touchStartX = e.changedTouches[0].screenX);
        lightbox.addEventListener('touchend', e => {
            let touchEndX = e.changedTouches[0].screenX;
            if (touchEndX < touchStartX - 50) nextImage();
            if (touchEndX > touchStartX + 50) prevImage();
        });
    </script>
</body>
</html>
"""

def get_breadcrumbs(path_str):
    if not path_str: return []
    parts = path_str.strip('/').split('/')
    breadcrumbs = []
    current = ""
    for part in parts:
        current = f"{current}/{part}" if current else part
        breadcrumbs.append({'name': part, 'path': current})
    return breadcrumbs

@app.route('/')
@app.route('/browse/<path:subpath>')
def browse(subpath=''):
    if '..' in subpath: abort(403)
    
    abs_path = os.path.join(IMAGE_ROOT, subpath)
    if not os.path.exists(abs_path): return "Path not found", 404

    dirs, files = [], []
    try:
        with os.scandir(abs_path) as it:
            for entry in it:
                if entry.name.startswith('.'): continue
                rel_path = os.path.join(subpath, entry.name).replace('\\', '/')
                
                if entry.is_dir():
                    dirs.append({'name': entry.name, 'path': quote(rel_path)})
                elif entry.is_file() and os.path.splitext(entry.name)[1].lower() in VALID_EXTENSIONS:
                    files.append({'name': entry.name, 'path': quote(rel_path)})
    except PermissionError: return "Permission Denied", 403

    # 排序：忽略大小写
    dirs.sort(key=lambda x: x['name'].lower())
    files.sort(key=lambda x: x['name'].lower())

    parent_path = os.path.dirname(subpath.rstrip('/')) if subpath else ''

    return render_template_string(
        HTML_TEMPLATE,
        folders=dirs,
        images=files,
        breadcrumbs=get_breadcrumbs(subpath),
        current_path=subpath,
        parent_path=parent_path,
        icons=ICONS
    )

@app.route('/file/<path:filepath>')
def serve_file(filepath):
    return send_from_directory(IMAGE_ROOT, unquote(filepath))

if __name__ == '__main__':
    print(f"Server is running on http://0.0.0.0:{PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=False)
