# 使用多阶段构建减小镜像体积
FROM python:3.9 as builder

# 安装OpenCV系统依赖
RUN apt-get update && \
    apt-get install -y libgl1 libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --user -r requirements.txt

FROM python:3.9
WORKDIR /app

# 安装FFMPEG和图形库支持
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    libavcodec-dev \
    libavformat-dev \
    libswscale-dev \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgl1-mesa-dri \
    libglu1-mesa \
    mesa-utils && \
    rm -rf /var/lib/apt/lists/*

# 复制Python依赖
COPY --from=builder /root/.local /root/.local
COPY . .

# 确保脚本可执行
RUN chmod +x creality_K1_Monitor_storage.py

# 添加环境变量
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONPATH=/app

# 摄像头和WebSocket配置
ENV CAMERA_IP=10.0.0.21
ENV STREAM_PORT=8080
ENV STREAM_PATH=/?action=stream
ENV WS_URL=ws://10.0.0.21:9999

# 视频配置
ENV VIDEO_CODEC=mp4v
ENV FPS=15
ENV MAX_DURATION=3600
ENV MAX_DAYS=7
ENV MAX_FILES=20

# 挂载数据卷
VOLUME /data
WORKDIR /data

# 入口点
ENTRYPOINT ["python", "/app/creality_K1_Monitor_storage.py"]
