import cv2
import os
import datetime
import logging
import configparser
from pathlib import Path
import asyncio
import websockets
import json

def load_config():
    """加载配置，优先使用环境变量"""
    config = {
        "CAMERA_IP": os.getenv('CAMERA_IP', '10.0.0.21'),
        "STREAM_PORT": int(os.getenv('STREAM_PORT', '8080')),
        "STREAM_PATH": os.getenv('STREAM_PATH', '/?action=stream'),
        "VIDEO_CODEC": os.getenv('VIDEO_CODEC', 'mp4v'),
        "FPS": int(os.getenv('FPS', '15')),
        "SHOW_PREVIEW": os.getenv('SHOW_PREVIEW', 'false').lower() == 'true',
        "MAX_DURATION": int(os.getenv('MAX_DURATION', '3600')),
        "MAX_DAYS": int(os.getenv('MAX_DAYS', '7')),
        "MAX_FILES": int(os.getenv('MAX_FILES', '20')),
        "WS_URL": os.getenv('WS_URL', 'ws://10.0.0.21:9999')
    }
    
    # 如果存在配置文件，则覆盖环境变量
    if os.path.exists('config.ini'):
        try:
            parser = configparser.ConfigParser()
            with open('config.ini', 'r', encoding='utf-8') as f:
                parser.read_file(f)
            
            if parser.has_section('Camera'):
                config.update({
                    "CAMERA_IP": parser.get('Camera', 'ip', fallback=config["CAMERA_IP"]),
                    "STREAM_PORT": parser.getint('Camera', 'port', fallback=config["STREAM_PORT"]),
                    "STREAM_PATH": parser.get('Camera', 'path', fallback=config["STREAM_PATH"])
                })
            
            if parser.has_section('Video'):
                config.update({
                    "VIDEO_CODEC": parser.get('Video', 'codec', fallback=config["VIDEO_CODEC"]),
                    "FPS": parser.getint('Video', 'fps', fallback=config["FPS"]),
                    "SHOW_PREVIEW": parser.getboolean('Video', 'show_preview', fallback=config["SHOW_PREVIEW"]),
                    "MAX_DURATION": parser.getint('Video', 'max_duration', fallback=config["MAX_DURATION"])
                })
            
            if parser.has_section('Storage'):
                config.update({
                    "MAX_DAYS": parser.getint('Storage', 'max_days', fallback=config["MAX_DAYS"]),
                    "MAX_FILES": parser.getint('Storage', 'max_files', fallback=config["MAX_FILES"])
                })
            
            if parser.has_section('WebSocket'):
                config["WS_URL"] = parser.get('WebSocket', 'url', fallback=config["WS_URL"])
                
        except Exception as e:
            logger.error(f"配置文件解析错误: {str(e)}")
    
    return config

def clean_old_videos(config):
    """清理旧视频文件"""
    try:
        # 获取当前日期和时间
        now = datetime.datetime.now()
        # 计算截止日期，即当前日期减去配置中指定的最大天数
        cutoff_date = now - datetime.timedelta(days=config['MAX_DAYS'])
        
        # 遍历当前目录下的所有文件夹
        for folder in Path('.').glob('*'):
            # 如果文件夹不是'备份'文件夹，则进行进一步检查
            if folder.is_dir() and folder.name != '备份':
                # 尝试将文件夹名称解析为日期格式（YYYY-MM-DD）
                try:
                    folder_date = datetime.datetime.strptime(folder.name, '%Y-%m-%d')
                    # 如果文件夹的日期早于截止日期，则删除该文件夹下的所有.avi文件并删除文件夹
                    if folder_date < cutoff_date:
                        logger.info(f"Removing old folder: {folder.name}")
                        for file in folder.glob('*.avi'):
                            file.unlink()  # 删除.avi文件
                        folder.rmdir()  # 删除空文件夹
                        continue
                except ValueError:
                    # 如果文件夹名称无法解析为日期格式，则跳过该文件夹
                    continue
                
                # 获取文件夹内所有.avi文件，并按修改时间排序
                files = list(folder.glob('*.avi'))
                files.sort(key=os.path.getmtime)
                # 如果文件夹内的.avi文件数量超过配置中指定的最大文件数，则删除最早的文件
                if len(files) > config['MAX_FILES']:
                    for file in files[:-config['MAX_FILES']]:
                        logger.info(f"Removing excess file: {file}")
                        file.unlink()  # 删除.avi文件
    except Exception as e:
        # 捕获并记录所有异常
        logger.error(f"Error cleaning old videos: {str(e)}")

import re

class PrinterStatusMonitor:
    def __init__(self, ws_url):
        self.ws_url = ws_url
        self.websocket = None
        self.should_record = False
        self.current_print_name = "unknown"
    
    def extract_print_name(self, file_str):
        """从打印文件字符串中提取模型名称"""
        try:
            if not file_str:
                return None
            
            # 提取文件名部分（去除路径）
            filename = os.path.basename(file_str)
            
            # 处理两种常见格式：
            # 1. "模型名称.stl_材料_时间.gcode"
            # 2. "模型名称.stl"
            match = re.search(r'([^/]+?)\.stl(?:_|$)', filename)
            if match:
                return match.group(1)
            
            # 如果都不匹配，尝试提取基本名称（去除.gcode后缀）
            return re.sub(r'\.gcode$', '', filename)
        except Exception:
            return None
    
    def if_state_should_record(self, state):
        """判断当前状态是否需要录制视频"""
        # 状态说明: 0空闲 1打印中 2打印完成 3打印失败 4打印终止 5暂停/异常
        return state in (1, 5)
    
    async def run(self):
        """运行WebSocket监听循环"""
        while True:
            try:
                self.websocket = await websockets.connect(self.ws_url)
                logger.info("WebSocket连接成功")
                
                while True:
                    message = await self.websocket.recv()
                    data = json.loads(message)
                    logger.debug(f"收到消息: {data}")
                    
                    try:
                        # 验证消息格式
                        if not isinstance(data, dict) or 'state' not in data:
                            raise ValueError("Invalid message format")
                        
                        state = int(data['state'])
                        if state not in range(6):  # 状态范围0-5
                            raise ValueError("Invalid state value")
                        
                        # 更新录制状态和打印任务名称
                        self.should_record = self.if_state_should_record(state)
                        if 'printFileName' in data and data['printFileName']:
                            self.current_print_name = self.extract_print_name(str(data['printFileName']))
                        
                        logger.info(f"状态更新: {state}, 录制状态: {'开启' if self.should_record else '关闭'}, 打印任务: {self.current_print_name or '未获取'}")
                    
                    except (ValueError, TypeError) as e:
                        logger.warning(f"消息解析错误: {str(e)}, 原始数据: {data}")
                        await self.websocket.close()
                        await asyncio.sleep(1)
                        break
                
            except websockets.exceptions.ConnectionClosedError as e:
                logger.error(f"连接关闭错误: {str(e)}")
            except websockets.exceptions.ConnectionClosedOK as e:
                logger.info(f"正常关闭连接: {str(e)}")
            except Exception as e:
                logger.error(f"发生错误: {str(e)}")
            finally:
                if self.websocket:
                    await self.websocket.close()
                await asyncio.sleep(1)

# 初始化日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

async def video_recording_loop(config, status_monitor):
    """视频录制主循环"""
    while True:
        try:
            # 等待有效的录制状态
            while not status_monitor.should_record:
                await asyncio.sleep(1)
            
            # 清理旧文件
            clean_old_videos(config)
            
            # 创建视频流URL（兼容新旧格式）
            base_url = f"http://{config['CAMERA_IP']}:{config['STREAM_PORT']}"
            stream_url = f"{base_url}{config['STREAM_PATH']}" if config['STREAM_PATH'].startswith('/') else f"{base_url}/{config['STREAM_PATH']}"
            logger.debug(f"使用视频流URL: {stream_url}")
            logger.info(f"Connecting to camera stream: {stream_url}")

            # 强制使用FFMPEG backend
            cap = None
            try:
                cap = cv2.VideoCapture(stream_url, cv2.CAP_FFMPEG)
                if not cap.isOpened():
                    # 尝试添加协议前缀
                    if not stream_url.startswith(('http://', 'rtsp://')):
                        stream_url = 'http://' + stream_url
                    cap.open(stream_url, cv2.CAP_FFMPEG)
                    
                if not cap.isOpened():
                    # 获取支持的backend列表
                    backends = [cv2.CAP_FFMPEG, cv2.CAP_GSTREAMER, cv2.CAP_ANY]
                    for backend in backends:
                        cap = cv2.VideoCapture(stream_url, backend)
                        if cap.isOpened():
                            break
                        cap.release()
                
                if not cap or not cap.isOpened():
                    # 详细记录backend信息
                    backend_info = "\n".join([
                        f"Available backends: {cv2.videoio_registry.getBackendName(backend)}"
                        for backend in cv2.videoio_registry.getBackends()
                    ])
                    raise RuntimeError(
                        f"无法打开视频流: {stream_url}\n"
                        f"支持的backend:\n{backend_info}\n"
                        f"请确认:\n"
                        f"1. 摄像头URL可访问\n"
                        f"2. 服务器安装了FFMPEG\n"
                        f"3. 防火墙允许访问摄像头端口"
                    )
            except Exception as e:
                logger.error(f"初始化视频捕获失败: {str(e)}")
                if cap:
                    cap.release()
                raise
                
            # 设置视频流参数
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            cap.set(cv2.CAP_PROP_FPS, config['FPS'])
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            
            # 尝试打开摄像头，最多重试3次
            max_retries = 3
            for i in range(max_retries):
                if cap.isOpened():
                    break
                logger.warning(f"尝试连接摄像头失败 ({i+1}/{max_retries})")
                await asyncio.sleep(1)
                cap.open(stream_url)  # 重新尝试打开

            if not cap.isOpened():
                logger.error(f"无法打开视频流: {stream_url}")
                raise RuntimeError(f"无法打开视频流: {stream_url}")
                raise RuntimeError("Failed to open video capture")

            # 设置输出视频参数
            fourcc = cv2.VideoWriter_fourcc(*config['VIDEO_CODEC'])
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))  
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            logger.info(f"Video resolution: {width}x{height}")

            # 创建视频写入对象
            now = datetime.datetime.now()
            folder_name = now.strftime('%Y-%m-%d')
            os.makedirs(folder_name, exist_ok=True)
            
            # 确保有有效的打印任务名称（等待最多3秒）
            start_wait = datetime.datetime.now()
            while not status_monitor.current_print_name:
                if (datetime.datetime.now() - start_wait).total_seconds() > 3:
                    logger.warning("等待打印任务名称超时，使用默认名称")
                    status_monitor.current_print_name = "未命名任务"
                    break
                await asyncio.sleep(0.1)
            
            def clean_filename(name):
                """清理文件名中的非法字符"""
                if not name:
                    return "未命名任务"
                # 替换路径分隔符和特殊字符
                name = re.sub(r'[\\/:*?"<>|]', '_', name)
                # 限制长度并去除首尾空格
                return name.strip()[:50] or "未命名任务"

            # 生成安全的文件名
            print_name = clean_filename(status_monitor.current_print_name)
            time_str = now.strftime('%Y%m%d_%H%M%S')
            file_name = f"{print_name}_{time_str}.avi"
            file_path = os.path.join(folder_name, file_name)
            logger.info(f"准备录制视频到: {file_path} (打印任务: {print_name})")

            # 确保目录存在
            os.makedirs(folder_name, exist_ok=True)
            
            # 验证文件可写
            try:
                test_path = os.path.join(folder_name, 'test_write.avi')
                with open(test_path, 'w') as f:
                    f.write('test')
                os.unlink(test_path)
            except Exception as e:
                logger.error(f"无法写入视频文件: {str(e)}")
                raise

            out = cv2.VideoWriter(file_path, fourcc, config['FPS'], (width, height))
            if not out.isOpened():
                raise RuntimeError("无法创建视频写入器")

            try:
                start_time = datetime.datetime.now()
                frame_count = 0
                
                while cap.isOpened():
                    try:
                        # 每帧检查一次打印机状态
                        if not status_monitor.should_record:
                            logger.info("打印机状态变化，停止录制")
                            break
                        
                        # 高频状态检查（每10帧）
                        if frame_count % 10 == 0:
                            await asyncio.sleep(0)  # 允许事件循环处理状态更新
                        
                        ret, frame = cap.read()
                        if not ret:
                            logger.error("无法从摄像头读取帧，停止录制")
                            break
                        
                        # 保存帧到视频文件
                        try:
                            out.write(frame)
                            frame_count += 1
                        except Exception as e:
                            logger.error(f"视频写入失败: {str(e)}")
                            raise
                        
                        # 检查录制时长
                        if config['MAX_DURATION'] > 0:
                            elapsed = (datetime.datetime.now() - start_time).total_seconds()
                            if elapsed >= config['MAX_DURATION']:
                                logger.info(f"达到最大录制时长 {config['MAX_DURATION']}秒，停止录制")
                                break
                        
                        # 可选预览
                        if config['SHOW_PREVIEW']:
                            try:
                                cv2.imshow('Recording', frame)
                                if cv2.waitKey(1) & 0xFF == ord('q'):
                                    logger.info("用户请求停止录制")
                                    break
                            except Exception as e:
                                logger.error(f"预览窗口错误: {str(e)}")
                                config['SHOW_PREVIEW'] = False
                    
                    except Exception as e:
                        logger.error(f"录制过程中发生错误: {str(e)}")
                        break

            except Exception as e:
                logger.error(f"视频捕获过程中发生严重错误: {str(e)}", exc_info=True)
                # 等待5秒后重试
                await asyncio.sleep(5)
                continue

            finally:
                # 确保资源释放
                cap.release()
                out.release()
                if config['SHOW_PREVIEW']:
                    cv2.destroyAllWindows()
                logger.info("Resources released successfully")
                
                # 等待状态变为需要录制
                while not status_monitor.should_record:
                    await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Fatal error in video loop: {str(e)}")
            await asyncio.sleep(5)  # 错误后等待5秒再重试

async def main():
    """主程序入口"""
    try:
        # 加载配置
        config = load_config()
        
        # 创建状态监控器
        status_monitor = PrinterStatusMonitor(config['WS_URL'])
        
        # 启动两个任务
        await asyncio.gather(
            status_monitor.run(),
            video_recording_loop(config, status_monitor)
        )
        
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(main())


