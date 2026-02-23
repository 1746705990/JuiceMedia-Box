import os
import sys
import socket
import socketserver
import re
import urllib.parse
from http.server import SimpleHTTPRequestHandler

# 端口号 (根据你的实际情况修改，你刚才提到是 8090)
PORT = 8091

# 支持生成播放列表的视频格式
VIDEO_EXTENSIONS = ('.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.wav', '.mp3')

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

class AdvancedRequestHandler(SimpleHTTPRequestHandler):
    
    def do_GET(self):
        """
        拦截 GET 请求：
        1. 如果请求的是 /playlist.m3u -> 动态生成播放列表
        2. 其他情况 -> 走默认的文件下载/流式播放逻辑
        """
        if self.path == '/playlist.m3u':
            self.send_playlist()
        else:
            # 必须调用 super 的逻辑来处理标准文件请求
            super().do_GET()

    def send_playlist(self):
        """生成并发送 m3u 播放列表"""
        try:
            # 获取当前目录下所有媒体文件并排序
            files = [f for f in os.listdir(os.getcwd()) if f.lower().endswith(VIDEO_EXTENSIONS)]
            files.sort()

            # 获取客户端请求的 Host (例如 192.168.1.5:8090)
            host = self.headers.get('Host')
            if not host:
                host = f"{get_local_ip()}:{PORT}"

            # 构建 M3U 内容
            playlist_content = ["#EXTM3U"]
            for filename in files:
                # URL 编码文件名（处理中文和空格）
                safe_filename = urllib.parse.quote(filename)
                full_url = f"http://{host}/{safe_filename}"
                
                playlist_content.append(f"#EXTINF:-1,{filename}")
                playlist_content.append(full_url)
            
            content_bytes = "\n".join(playlist_content).encode('utf-8')

            # 发送响应
            self.send_response(200)
            self.send_header("Content-type", "audio/x-mpegurl; charset=utf-8") # 关键 MIME 类型
            self.send_header("Content-Length", str(len(content_bytes)))
            self.send_header("Content-Disposition", 'attachment; filename="playlist.m3u"')
            self.end_headers()
            self.wfile.write(content_bytes)
            print(f"[{self.client_address[0]}] -> 已获取播放列表 (包含 {len(files)} 个文件)")

        except Exception as e:
            self.send_error(500, f"Error generating playlist: {e}")

    # --- 以下是之前为了支持拖动进度条(Range)的代码 ---
    def end_headers(self):
        self.send_header('Accept-Ranges', 'bytes')
        super().end_headers()

    def send_head(self):
        if 'Range' not in self.headers:
            self.range = None
            return super().send_head()
        try:
            self.range = re.search(r'bytes=(\d+)-(\d*)', self.headers['Range']).groups()
        except AttributeError:
            self.range = None
            return super().send_head()
        path = self.translate_path(self.path)
        f = None
        try:
            f = open(path, 'rb')
        except OSError:
            self.send_error(404, "File not found")
            return None
        ctype = self.guess_type(path)
        try:
            fs = os.fstat(f.fileno())
            file_len = fs[6]
            start = int(self.range[0])
            end = int(self.range[1]) if self.range[1] else file_len - 1
            if start >= file_len:
                self.send_error(416, "Requested Range Not Satisfiable")
                return None
            self.send_response(206)
            self.send_header("Content-type", ctype)
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_len}")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
            self.end_headers()
            f.seek(start)
            return f
        except:
            f.close()
            raise

    def copyfile(self, source, outputfile):
        if not self.range:
            super().copyfile(source, outputfile)
            return
        start = int(self.range[0])
        end = int(self.range[1]) if self.range[1] else os.fstat(source.fileno())[6] - 1
        length = end - start + 1
        BUFFER_SIZE = 64 * 1024 
        while length > 0:
            read_len = min(length, BUFFER_SIZE)
            buf = source.read(read_len)
            if not buf:
                break
            outputfile.write(buf)
            length -= len(buf)

class ThreadingServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True 
    def handle_error(self, request, client_address):
        ex_type, ex_value, tb = sys.exc_info()
        if isinstance(ex_value, (BrokenPipeError, ConnectionResetError)):
            return 
        super().handle_error(request, client_address)

def main():
    print("-" * 50)
    # 默认路径
    default_dir = os.getcwd()
    try:
        user_input = input(f"请输入视频文件夹路径 (默认: {default_dir}): ").strip().replace('"', '').replace("'", "")
    except EOFError:
        user_input = ""
    target_dir = user_input if user_input else default_dir

    if not os.path.exists(target_dir):
        print(f"[错误] 路径不存在: {target_dir}")
        sys.exit(1)
    
    os.chdir(target_dir)

    try:
        with ThreadingServer(("", PORT), AdvancedRequestHandler) as httpd:
            ip = get_local_ip()
            print("-" * 50)
            print(f"✅ 服务已启动 (支持连播/拖动)")
            print(f"📂 目录: {target_dir}")
            print(f"👉 1. 单个播放: http://{ip}:{PORT}")
            print(f"👉 2. 自动连播: http://{ip}:{PORT}/playlist.m3u  <-- 复制这个进 VLC")
            print("-" * 50)
            httpd.serve_forever()
    except OSError as e:
        if e.errno == 98:
            print(f"[错误] 端口 {PORT} 被占用。")
        else:
            print(f"[错误] {e}")
    except KeyboardInterrupt:
        print("\n服务已停止。")

if __name__ == "__main__":
    main()
