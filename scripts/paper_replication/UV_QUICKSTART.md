# UV 快速开始指南

## 🚀 5分钟快速部署

### 方法1: 使用部署脚本（推荐）

```bash
cd /workspace/scripts/paper_replication

# 一键完整设置
./deploy.sh setup

# 激活环境并运行
source .venv/bin/activate
python3 run_full_experiment.py
```

### 方法2: 手动逐步执行

```bash
# 1. 安装UV
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 创建虚拟环境
cd /workspace/scripts/paper_replication
uv venv --python 3.10

# 3. 激活环境
source .venv/bin/activate

# 4. 安装依赖
uv pip install -e .

# 5. 运行实验
python3 run_full_experiment.py
```

---

## 📋 部署脚本命令

### 完整设置
```bash
./deploy.sh setup
```
自动完成：安装UV → 创建环境 → 安装依赖 → 运行测试

### 单独命令

```bash
# 安装UV
./deploy.sh install

# 运行测试验证
./deploy.sh test

# 运行完整实验
./deploy.sh run

# 查看环境状态
./deploy.sh status

# 清理环境
./deploy.sh clean

# 显示帮助
./deploy.sh help
```

---

## 🎯 常用操作

### 日常使用

```bash
# 1. 激活环境
source .venv/bin/activate

# 2. 运行脚本
python3 simple_test.py              # 测试验证
python3 run_full_experiment.py      # 完整实验

# 3. 退出环境
deactivate
```

### 数据下载

```bash
source .venv/bin/activate

# 下载测试数据（3个交易对）
python3 download_candles_data.py test

# 下载所有数据（30个交易对）
python3 download_candles_data.py all

# 按类别下载
python3 download_candles_data.py layer1
python3 download_candles_data.py meme
```

### 回测运行

```bash
source .venv/bin/activate

# 单个交易对
python3 backtest_comparison.py SOL-USDT

# 所有测试交易对
python3 backtest_comparison.py ALL
```

---

## 🔧 依赖管理

### 安装新包

```bash
source .venv/bin/activate

# 安装单个包
uv pip install pandas

# 安装多个包
uv pip install pandas numpy matplotlib

# 从requirements.txt安装
uv pip install -r requirements.txt
```

### 更新包

```bash
# 更新单个包
uv pip install --upgrade pandas

# 更新所有包
uv pip install --upgrade-all
```

### 查看已安装的包

```bash
uv pip list
uv pip freeze > requirements.txt
```

---

## 🐛 故障排除

### 问题1: UV命令找不到

```bash
# 添加到PATH
export PATH="$HOME/.cargo/bin:$PATH"
echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### 问题2: 虚拟环境激活失败

```bash
# 确保activate脚本可执行
chmod +x .venv/bin/activate

# 或直接使用python
.venv/bin/python script.py
```

### 问题3: 依赖安装失败

```bash
# 删除环境重新创建
rm -rf .venv
uv venv
source .venv/bin/activate
uv pip install -e .
```

---

## 📊 性能对比

### UV vs PIP

```bash
# 安装pandas numpy matplotlib

# PIP (传统方式)
pip install pandas numpy matplotlib
# 时间: ~45秒

# UV (新方式)
uv pip install pandas numpy matplotlib
# 时间: ~3秒

# 速度提升: 15倍! ⚡
```

---

## 🌏 国内用户配置

### 使用国内镜像

```bash
# 临时使用
export UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
uv pip install pandas

# 永久配置
mkdir -p ~/.config/uv
cat > ~/.config/uv/uv.toml << EOF
[pip]
index-url = "https://pypi.tuna.tsinghua.edu.cn/simple"
EOF

# 其他镜像源
# 清华: https://pypi.tuna.tsinghua.edu.cn/simple
# 阿里云: https://mirrors.aliyun.com/pypi/simple/
# 中科大: https://pypi.mirrors.ustc.edu.cn/simple/
```

---

## 📚 更多文档

- **完整指南**: [UV_DEPLOYMENT_GUIDE.md](UV_DEPLOYMENT_GUIDE.md)
- **项目文档**: [README.md](README.md)
- **快速上手**: [QUICKSTART.md](QUICKSTART.md)

---

## ✅ 验证安装

```bash
# 激活环境
source .venv/bin/activate

# 验证Python包
python3 -c "
import pandas as pd
import numpy as np
import matplotlib
print('✓ 所有依赖安装成功!')
print(f'  Pandas: {pd.__version__}')
print(f'  NumPy: {np.__version__}')
print(f'  Matplotlib: {matplotlib.__version__}')
"

# 运行测试
python3 simple_test.py
```

---

## 🎉 开始实验

```bash
cd /workspace/scripts/paper_replication

# 完整设置（首次）
./deploy.sh setup

# 运行实验
./deploy.sh run

# 或者手动
source .venv/bin/activate
python3 run_full_experiment.py
```

---

**享受UV带来的极速体验！** ⚡
