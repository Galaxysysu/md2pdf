#!/bin/bash

# 获取脚本所在的目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 激活虚拟环境
source "$SCRIPT_DIR/venv/bin/activate"

# 运行md2pdf.py并传递所有参数
python "$SCRIPT_DIR/md2pdf_repo/md2pdf.py" "$@"

# 输出完成消息
echo "转换完成！" 