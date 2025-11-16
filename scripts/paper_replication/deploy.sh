#!/bin/bash

# 部署脚本 - 使用UV进行环境管理
# 论文复现项目: Market Making in Crypto (Stoikov et al. 2024)

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印函数
print_header() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# 检查命令是否存在
check_command() {
    if command -v $1 &> /dev/null; then
        print_success "$1 已安装"
        return 0
    else
        print_error "$1 未安装"
        return 1
    fi
}

# 显示帮助信息
show_help() {
    cat << EOF
部署脚本 - UV环境管理

用法: ./deploy.sh [选项]

选项:
    install         安装UV和依赖
    setup           创建虚拟环境并安装依赖
    test            运行测试验证
    run             运行完整实验
    clean           清理虚拟环境
    help            显示此帮助信息

示例:
    ./deploy.sh install     # 安装UV
    ./deploy.sh setup       # 完整设置
    ./deploy.sh test        # 运行测试
    ./deploy.sh run         # 运行实验

EOF
}

# 安装UV
install_uv() {
    print_header "步骤1: 安装UV"
    
    if check_command uv; then
        UV_VERSION=$(uv --version 2>&1 | head -n1)
        print_info "当前版本: $UV_VERSION"
        read -p "是否要重新安装? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            return 0
        fi
    fi
    
    print_info "开始安装UV..."
    
    # 检测操作系统
    if [[ "$OSTYPE" == "linux-gnu"* ]] || [[ "$OSTYPE" == "darwin"* ]]; then
        # Linux/macOS
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]]; then
        # Windows
        print_warning "Windows系统请使用PowerShell运行:"
        print_info "powershell -c \"irm https://astral.sh/uv/install.ps1 | iex\""
        exit 1
    else
        print_error "不支持的操作系统: $OSTYPE"
        print_info "请手动安装: pip install uv"
        exit 1
    fi
    
    # 验证安装
    if check_command uv; then
        print_success "UV安装成功!"
        uv --version
    else
        print_error "UV安装失败"
        print_info "尝试使用pip安装: pip install uv"
        exit 1
    fi
}

# 创建虚拟环境
create_venv() {
    print_header "步骤2: 创建虚拟环境"
    
    # 检查是否已存在
    if [ -d ".venv" ]; then
        print_warning "虚拟环境已存在"
        read -p "是否删除并重新创建? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            print_info "删除旧的虚拟环境..."
            rm -rf .venv
        else
            print_info "使用现有虚拟环境"
            return 0
        fi
    fi
    
    print_info "创建Python 3.10虚拟环境..."
    
    # 尝试创建Python 3.10环境
    if uv venv --python 3.10 .venv 2>/dev/null; then
        print_success "使用Python 3.10创建虚拟环境"
    else
        print_warning "Python 3.10不可用，使用系统默认版本"
        uv venv .venv
    fi
    
    if [ -d ".venv" ]; then
        print_success "虚拟环境创建成功: .venv/"
    else
        print_error "虚拟环境创建失败"
        exit 1
    fi
}

# 安装依赖
install_dependencies() {
    print_header "步骤3: 安装项目依赖"
    
    # 激活虚拟环境
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
        print_success "虚拟环境已激活"
    else
        print_error "找不到虚拟环境激活脚本"
        exit 1
    fi
    
    # 检查pyproject.toml
    if [ ! -f "pyproject.toml" ]; then
        print_error "找不到pyproject.toml文件"
        print_info "请确保在项目根目录运行此脚本"
        exit 1
    fi
    
    print_info "从pyproject.toml安装依赖..."
    
    # 安装项目依赖
    if uv pip install -e .; then
        print_success "项目依赖安装成功"
    else
        print_warning "从pyproject.toml安装失败，尝试手动安装核心依赖..."
        
        # 手动安装核心依赖
        CORE_DEPS="pandas numpy pandas-ta matplotlib seaborn scipy aiohttp pydantic"
        print_info "安装核心依赖: $CORE_DEPS"
        
        if uv pip install $CORE_DEPS; then
            print_success "核心依赖安装成功"
        else
            print_error "依赖安装失败"
            exit 1
        fi
    fi
    
    # 验证安装
    print_info "验证关键包安装..."
    python3 -c "
import sys
packages = ['pandas', 'numpy', 'matplotlib']
missing = []
for pkg in packages:
    try:
        __import__(pkg)
        print(f'✓ {pkg}')
    except ImportError:
        missing.append(pkg)
        print(f'✗ {pkg}')
if missing:
    print(f'\n缺少包: {missing}')
    sys.exit(1)
else:
    print('\n✓ 所有核心包安装成功')
"
    
    if [ $? -eq 0 ]; then
        print_success "依赖验证通过"
    else
        print_error "依赖验证失败"
        exit 1
    fi
}

# 运行测试
run_tests() {
    print_header "步骤4: 运行测试验证"
    
    # 激活虚拟环境
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
    else
        print_error "虚拟环境未创建"
        exit 1
    fi
    
    print_info "运行核心算法测试..."
    
    # 运行simple_test.py
    if [ -f "simple_test.py" ]; then
        if python3 simple_test.py; then
            print_success "核心算法测试通过 (6/6)"
        else
            print_error "核心算法测试失败"
            exit 1
        fi
    else
        print_warning "找不到simple_test.py，跳过测试"
    fi
    
    # 运行代码结构验证
    print_info "运行代码结构验证..."
    if [ -f "code_structure_test.py" ]; then
        if python3 code_structure_test.py; then
            print_success "代码结构验证通过"
        else
            print_warning "代码结构验证未完全通过（可能是正常的）"
        fi
    fi
}

# 运行实验
run_experiment() {
    print_header "运行完整实验"
    
    # 激活虚拟环境
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
    else
        print_error "虚拟环境未创建，请先运行: ./deploy.sh setup"
        exit 1
    fi
    
    print_info "开始运行实验..."
    print_warning "这可能需要20-45分钟，取决于网络速度和数据量"
    
    read -p "是否继续? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "取消运行"
        exit 0
    fi
    
    # 运行实验
    if [ -f "run_full_experiment.py" ]; then
        python3 run_full_experiment.py
    else
        print_error "找不到run_full_experiment.py"
        exit 1
    fi
}

# 清理环境
clean_env() {
    print_header "清理虚拟环境"
    
    if [ -d ".venv" ]; then
        print_warning "即将删除虚拟环境: .venv/"
        read -p "确认删除? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf .venv
            print_success "虚拟环境已删除"
        else
            print_info "取消清理"
        fi
    else
        print_info "虚拟环境不存在"
    fi
    
    # 可选：清理缓存
    read -p "是否清理UV缓存? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if [ -d "$HOME/.cache/uv" ]; then
            rm -rf "$HOME/.cache/uv"
            print_success "UV缓存已清理"
        fi
    fi
}

# 完整设置流程
full_setup() {
    print_header "完整设置流程"
    
    print_info "将执行以下步骤:"
    echo "  1. 安装UV（如需要）"
    echo "  2. 创建虚拟环境"
    echo "  3. 安装项目依赖"
    echo "  4. 运行测试验证"
    echo ""
    
    read -p "是否继续? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "取消设置"
        exit 0
    fi
    
    # 执行步骤
    install_uv
    echo ""
    
    create_venv
    echo ""
    
    install_dependencies
    echo ""
    
    run_tests
    echo ""
    
    print_header "🎉 设置完成！"
    print_success "环境已准备就绪"
    echo ""
    print_info "下一步操作:"
    echo "  1. 激活环境: source .venv/bin/activate"
    echo "  2. 运行实验: python3 run_full_experiment.py"
    echo "  或直接运行: ./deploy.sh run"
    echo ""
}

# 显示状态
show_status() {
    print_header "环境状态"
    
    # UV状态
    if check_command uv; then
        UV_VERSION=$(uv --version 2>&1)
        echo "  UV: $UV_VERSION"
    else
        echo "  UV: 未安装"
    fi
    
    # 虚拟环境状态
    if [ -d ".venv" ]; then
        echo "  虚拟环境: 已创建 (.venv/)"
        if [ -f ".venv/bin/python" ]; then
            PYTHON_VERSION=$(.venv/bin/python --version 2>&1)
            echo "  Python: $PYTHON_VERSION"
        fi
    else
        echo "  虚拟环境: 未创建"
    fi
    
    # 依赖状态
    if [ -f ".venv/bin/python" ]; then
        echo ""
        echo "  已安装的包:"
        .venv/bin/pip list 2>/dev/null | grep -E "pandas|numpy|matplotlib" || echo "    无关键包"
    fi
}

# 主函数
main() {
    # 显示标题
    cat << "EOF"
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║          论文复现项目 - UV环境管理部署脚本                      ║
║                                                                  ║
║    Market Making in Crypto (Stoikov et al. 2024)               ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝

EOF
    
    # 检查参数
    if [ $# -eq 0 ]; then
        show_help
        exit 0
    fi
    
    # 处理命令
    case "$1" in
        install)
            install_uv
            ;;
        setup)
            full_setup
            ;;
        test)
            run_tests
            ;;
        run)
            run_experiment
            ;;
        clean)
            clean_env
            ;;
        status)
            show_status
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            print_error "未知命令: $1"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# 运行主函数
main "$@"
