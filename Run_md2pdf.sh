#!/bin/bash

# 获取脚本所在目录的绝对路径
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 用法帮助
if [ "$1" == "-h" ] || [ "$1" == "--help" ] || [ $# -lt 1 ]; then
    echo "用法: $0 <markdown文件> [输出PDF文件]"
    echo "用于将包含Python代码的Markdown文件转换为PDF，支持代码高亮和中文注释"
    exit 0
fi

input_file="$1"

# 检查输入文件是否存在
if [ ! -f "$input_file" ]; then
    echo "错误: 找不到输入文件 '$input_file'"
    exit 1
fi

# 获取输入文件的绝对路径
if [[ "$input_file" != /* ]]; then
    input_file="$(pwd)/$input_file"
fi

# 设置输出文件
if [ $# -ge 2 ]; then
    output_file="$2"
    # 获取输出文件的绝对路径
    if [[ "$output_file" != /* ]]; then
        output_file="$(pwd)/$output_file"
    fi
else
    # 使用输入文件名，但更改扩展名为.pdf
    filename=$(basename -- "$input_file")
    basename="${filename%.*}"
    output_file="$(pwd)/${basename}.pdf"
fi

# 检查是否安装了Python
if ! command -v python &> /dev/null; then
    echo "错误: 未安装Python。请安装Python 3.6或更高版本。"
    exit 1
fi

# 执行转换
echo "正在将Markdown转换为PDF，支持Python代码高亮..."
python "$SCRIPT_DIR/md2pdf.py" "$input_file" -o "$output_file"

# 检查是否成功
if [ $? -eq 0 ]; then
    echo "转换成功！PDF已保存为: $output_file"
    
    # 尝试打开PDF文件（根据不同操作系统）
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        open "$output_file"
    elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]] || [[ "$OSTYPE" == "cygwin" ]]; then
        # Windows
        start "$output_file"
    else
        # Linux或其他系统
        if command -v xdg-open &> /dev/null; then
            xdg-open "$output_file"
        else
            echo "PDF已生成，但无法自动打开。请手动打开文件: $output_file"
        fi
    fi
else
    echo "转换失败，请查看错误信息。"
    exit 1
fi 