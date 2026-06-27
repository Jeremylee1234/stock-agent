#!/bin/bash
# 流式输出测试运行脚本

echo "=================================="
echo "股票分析系统 - 流式输出测试"
echo "=================================="
echo ""

# 检查 Python 是否安装
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到 Python 3"
    echo "请先安装 Python 3: https://www.python.org/downloads/"
    exit 1
fi

echo "✓ Python 3 已安装"
echo ""

# 显示菜单
echo "请选择测试模式:"
echo ""
echo "  1) 快速测试 (推荐，无需启动 API)"
echo "  2) 详细测试 (直接测试工作流)"
echo "  3) SSE 接口测试 (需要先启动 API)"
echo "  4) 生成前端测试文件"
echo "  5) 启动 API 服务"
echo "  6) 运行所有测试"
echo "  0) 退出"
echo ""

read -p "请输入选项 (0-6): " choice

case $choice in
    1)
        echo ""
        echo "运行快速测试..."
        echo "=================================="
        python3 quick_stream_test.py
        ;;
    2)
        echo ""
        echo "运行详细测试..."
        echo "=================================="
        python3 test_streaming.py --mode direct
        ;;
    3)
        echo ""
        echo "运行 SSE 接口测试..."
        echo "=================================="
        echo "⚠️  请确保 API 服务已在另一个终端启动"
        echo "    启动命令: python3 api/main.py"
        echo ""
        read -p "按 Enter 继续..."
        python3 test_streaming.py --mode sse
        ;;
    4)
        echo ""
        echo "生成前端测试文件..."
        echo "=================================="
        python3 test_streaming.py --mode frontend
        echo ""
        echo "✓ 已生成 test_streaming_frontend.html"
        echo ""
        echo "使用方法:"
        echo "  1. 启动 API 服务: python3 api/main.py"
        echo "  2. 在浏览器中打开: test_streaming_frontend.html"
        ;;
    5)
        echo ""
        echo "启动 API 服务..."
        echo "=================================="
        echo "按 Ctrl+C 停止服务"
        echo ""
        python3 api/main.py
        ;;
    6)
        echo ""
        echo "运行所有测试..."
        echo "=================================="
        python3 test_streaming.py --mode all
        ;;
    0)
        echo ""
        echo "退出"
        exit 0
        ;;
    *)
        echo ""
        echo "❌ 无效选项"
        exit 1
        ;;
esac

echo ""
echo "=================================="
echo "测试完成"
echo "=================================="
