import os
import sys
import socket
import socketserver
import re
from http.server import SimpleHTTPRequestHandler

# 端口号，可根据需要修改
PORT = 8091

def get_local_ip():
    """获取本机局域网IP，方便在其他设备上输入"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

class RangeRequestHandler(SimpleHTTPRequestHandler):
    """
    增强版请求处理类：
    1. 支持 HTTP 206 Partial Content (断点续传/视频拖动)
    2. 强制声明 Accept-Ranges，优化 VLC 等播放器的识别
    """

    def end_headers(self):
        """
        在发送 header 结束前，强制添加 Accept-Ranges 头。
        这告诉 VLC 或浏览器：“我是支持拖动进度条的”，
        即使是第一次请求（HTTP 200）也能让客户端知道这一点。
        """
        self.send_header('Accept-Ranges', 'bytes')
        super().end_headers()

    def send_head(self):
        """
        重写 send_head 以处理 Range 请求
        """
        if 'Range' not in self.headers:
            self.range = None
            return super().send_head()
            
        try:
            # 解析 Range 头，格式通常为 bytes=0- 或 bytes=100-200
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
            # 获取文件大小
            fs = os.fstat(f.fileno())
            file_len = fs[6]
            
            # 解析请求的起始和结束位置
            start = int(self.range[0])
            end = int(self.range[1]) if self.range[1] else file_len - 1
            
            # 边界检查
            if start >= file_len:
                self.send_error(416, "Requested Range Not Satisfiable")
                return None
                
            # 发送 206 响应头
            self.send_response(206)
            self.send_header("Content-type", ctype)
            # self.send_header("Accept-Ranges", "bytes") # end_headers 已全局添加，这里不用重复
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_len}")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
            self.end_headers()
            
            # 关键：移动文件指针到客户端请求的位置
            f.seek(start)
            return f
        except:
            f.close()
            raise

    def copyfile(self, source, outputfile):
        """
        重写 copyfile：
        如果是 Range 请求，只发送请求的那一部分数据，而不是整个文件。
        这大大节省了带宽，并实现了“秒跳转”。
        """
        if not self.range:
            super().copyfile(source, outputfile)
            return

        # 计算需要读取的长度
        start = int(self.range[0])
        end = int(self.range[1]) if self.range[1] else os.fstat(source.fileno())[6] - 1
        length = end - start + 1
        
        BUFFER_SIZE = 64 * 1024 # 64KB 缓冲区
        
        while length > 0:
            read_len = min(length, BUFFER_SIZE)
            buf = source.read(read_len)
            if not buf:
                break
            outputfile.write(buf)
            length -= len(buf)

class ThreadingServer(socketserver.ThreadingTCPServer):
    """
    多线程服务器类：
    允许同时处理多个请求（例如：同时播放多个文件，或者浏览器并发下载）
    """
    allow_reuse_address = True
    daemon_threads = True 

    def handle_error(self, request, client_address):
        """
        捕获 Broken Pipe 错误，防止 VLC 停止播放或拖动进度条时
        终端疯狂报错。
        """
        ex_type, ex_value, tb = sys.exc_info()
        # 忽略连接重置或管道破裂错误
        if isinstance(ex_value, (BrokenPipeError, ConnectionResetError)):
            return 
        super().handle_error(request, client_address)

def main():
    print("-" * 50)
    # 获取默认路径
    default_dir = os.getcwd()
    
    # 允许用户输入路径，如果直接回车则使用当前路径
    try:
        user_input = input(f"请输入媒体文件夹路径 (默认: {default_dir}): ").strip().replace('"', '').replace("'", "")
    except EOFError:
        user_input = ""
    
    target_dir = user_input if user_input else default_dir

    if not os.path.exists(target_dir):
        print(f"[错误] 路径不存在: {target_dir}")
        sys.exit(1)
    
    # 切换工作目录
    os.chdir(target_dir)

    try:
        # 启动服务
        with ThreadingServer(("", PORT), RangeRequestHandler) as httpd:
            ip = get_local_ip()
            print("-" * 50)
            print(f"✅ 媒体流服务已启动 (支持 WAV/MP4 拖动播放)")
            print(f"📂 共享目录: {target_dir}")
            print(f"👉 VLC/浏览器访问地址: http://{ip}:{PORT}")
            print("-" * 50)
            httpd.serve_forever()
            
    except OSError as e:
        if e.errno == 98:
            print(f"[错误] 端口 {PORT} 已被占用，请修改脚本中的 PORT 变量。")
        else:
            print(f"[错误] {e}")
    except KeyboardInterrupt:
        print("\n服务已停止。")

if __name__ == "__main__":
    main()
