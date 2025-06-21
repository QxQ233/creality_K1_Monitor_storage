# Creality K1 3D打印机监控系统

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
- 本项目由AI协助开发

一个用于监控Creality K1 3D打印机状态并自动录制打印过程的解决方案。

## 功能特性
- 🎥 实时捕获打印机摄像头视频流
- 🔌 通过WebSocket监控打印机状态
- ⏱️ 根据打印状态自动开始/停止录制
- 📁 智能视频文件管理（按日期和打印任务分类）
- 🐳 支持Docker容器化部署
- ⚙️ 灵活的配置选项

## 系统要求
### 本地运行
- Python 3.9+
- OpenCV 4.5.5+
- 支持FFMPEG的系统环境

### Docker部署
- Docker 20.10+
- docker-compose 1.29+

## 快速开始

### Windos本地运行
1. 克隆仓库
   ```bash
   git clone https://github.com/QxQ233/creality_K1_Monitor_storage.git
   cd ./creality_K1_Monitor_storage
   ```

2. 安装依赖
   ```bash
   pip install -r requirements.txt
   ```

3. 启动监控
   ```bash
   python creality_K1_Monitor_storage.py
   ```

### 配置文件
编辑`config.ini`可覆盖环境变量：
```ini
[Camera]
ip = 10.0.0.21
port = 8080
path = /?action=stream

[Video]
codec = XVID
fps = 15
max_duration = 3600

[Storage]
max_days = 7
max_files = 100
```

### Docker部署
```bash
git clone https://github.com/QxQ233/creality_K1_Monitor_storage.git
cd ./creality_K1_Monitor_storage
docker build -t creality-monitor .
docker run -d --name creality-monitor --restart unless-stopped \
  -v /path/to/videos:/data \
  -e CAMERA_IP=10.0.0.21 \
  -e WS_URL=ws://10.0.0.21:9999 \
  creality-monitor
```

## 配置说明

### 环境变量
| 变量名 | 默认值 | 描述 |
|--------|--------|------|
| CAMERA_IP | 10.0.0.21 | 打印机摄像头IP |
| STREAM_PORT | 8080 | 视频流端口 |
| STREAM_PATH | /?action=stream | 视频流路径 |
| WS_URL | ws://10.0.0.21:9999 | WebSocket地址 |
| FPS | 15 | 视频帧率 |
| MAX_DURATION | 3600 | 最大录制时长(秒) |
| MAX_DAYS | 7 | 视频保留天数 |
| MAX_FILES | 20 | 每个文件夹最大文件数 |

## 开发指南

### 项目结构
```
.
├── creality_K1_Monitor_storage.py  # 主程序
├── config.ini                      # 配置文件
├── Dockerfile                      # Docker构建文件
└── requirements.txt                # Python依赖
```

### 构建自定义Docker镜像
```bash
docker build -t custom-monitor --build-arg PYTHON_VERSION=3.9 .
```

## 常见问题
1. **无法连接摄像头**
   - 检查摄像头IP是否正确
   - 确认网络连通性

2. **视频录制不清晰**
   - 调整FPS参数
   - 修改视频编解码器

3. **Docker容器无法启动**
   - 检查端口映射
   - 验证卷挂载权限

## 贡献指南
欢迎提交Pull Request。请确保：
1. 代码符合PEP8规范
2. 更新相关文档
3. 通过基础测试

## 许可证
MIT License - 详见 [LICENSE](LICENSE) 文件
