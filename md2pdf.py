#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
md2pdf.py: 将Markdown文件转换为排版精美的PDF

这个脚本能处理包含复杂数学公式、SVG图像和Mermaid流程图的Markdown文件。
特别适合转换由Claude等大模型生成的包含<chat-artifact>标签的Markdown文档。
使用Pandoc作为后端，直接转换Markdown到PDF，保留LaTeX公式的原始格式。

用法:
    python md2pdf.py <markdown_file_path>

示例:
    python md2pdf.py ./概念讲解/逆变基矢量与协变基矢量的正交关系.md
"""

import os
import sys
import re
import argparse
import tempfile
import shutil
import uuid
import subprocess
from pathlib import Path
import base64
from typing import Dict, List, Tuple, Optional, Union

try:
    import cairosvg
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("缺少必要的依赖库。请安装所需包：")
    print("pip install beautifulsoup4 cairosvg requests")
    sys.exit(1)

# 检查pandoc是否已安装
try:
    subprocess.run(["pandoc", "--version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
except (subprocess.SubprocessError, FileNotFoundError):
    print("错误: 未安装pandoc。请从https://pandoc.org/installing.html安装pandoc。")
    sys.exit(1)

# 检查xelatex是否已安装
try:
    subprocess.run(["xelatex", "--version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
except (subprocess.SubprocessError, FileNotFoundError):
    print("错误: 未安装xelatex。请安装TeX Live、MiKTeX或其他包含XeLaTeX的TeX发行版。")
    sys.exit(1)

# 可能需要额外安装的mermaid转换工具
try:
    from mermaid import mermaid_to_image
    MERMAID_AVAILABLE = True
except ImportError:
    MERMAID_AVAILABLE = False
    print("警告: 未找到mermaid包，将使用替代方案转换mermaid图表。")
    print("要使用本地转换，请安装: pip install mermaid-cli")

# 检测系统中可用的中文字体
def detect_available_fonts():
    """检测系统中可用的中文字体"""
    common_cn_fonts = [
        "Source Han Serif CN", "思源宋体", "Noto Serif CJK SC", 
        "Source Han Sans CN", "思源黑体", "Noto Sans CJK SC",
        "SimSun", "宋体", "SimHei", "黑体", "Microsoft YaHei", "微软雅黑",
        "FangSong", "仿宋", "KaiTi", "楷体", "STSong", "华文宋体"
    ]
    
    available_fonts = []
    
    # 在macOS上检查字体
    if sys.platform == 'darwin':
        try:
            font_dirs = ['/System/Library/Fonts', '/Library/Fonts', os.path.expanduser('~/Library/Fonts')]
            for font_dir in font_dirs:
                if os.path.exists(font_dir):
                    # 简单检查字体文件名
                    for font in os.listdir(font_dir):
                        font_lower = font.lower()
                        if font_lower.endswith(('.ttf', '.otf', '.ttc')):
                            for cn_font in common_cn_fonts:
                                if cn_font.lower().replace(' ', '') in font_lower.replace(' ', ''):
                                    available_fonts.append(cn_font)
        except Exception as e:
            print(f"检查字体时出错: {e}")
    
    # 在Linux上使用fc-list检查字体
    elif sys.platform.startswith('linux'):
        try:
            result = subprocess.run(['fc-list', ':lang=zh'], capture_output=True, text=True)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    for cn_font in common_cn_fonts:
                        if cn_font.lower().replace(' ', '') in line.lower().replace(' ', ''):
                            available_fonts.append(cn_font)
        except Exception as e:
            print(f"检查字体时出错: {e}")
    
    # 在Windows上检查字体
    elif sys.platform == 'win32':
        try:
            font_dir = os.path.join(os.environ['WINDIR'], 'Fonts')
            for font in os.listdir(font_dir):
                font_lower = font.lower()
                if font_lower.endswith(('.ttf', '.otf', '.ttc')):
                    for cn_font in common_cn_fonts:
                        if cn_font.lower().replace(' ', '') in font_lower.replace(' ', ''):
                            available_fonts.append(cn_font)
        except Exception as e:
            print(f"检查字体时出错: {e}")
    
    # 去重
    available_fonts = list(set(available_fonts))
    
    # 如果没有找到字体，返回默认字体
    if not available_fonts:
        if sys.platform == 'darwin':
            return ["STSong", "STHeiti", "STFangsong"]
        elif sys.platform == 'win32':
            return ["SimSun", "SimHei", "KaiTi"]
        else:
            return ["Noto Serif CJK SC", "Noto Sans CJK SC", "Noto Sans Mono CJK SC"]
    
    return available_fonts

# 获取系统中可用的中文字体
available_cn_fonts = detect_available_fonts()
serif_font = available_cn_fonts[0] if available_cn_fonts else "SimSun"
sans_font = available_cn_fonts[1] if len(available_cn_fonts) > 1 else serif_font
mono_font = available_cn_fonts[2] if len(available_cn_fonts) > 2 else sans_font

print(f"检测到中文衬线字体: {serif_font}")
print(f"检测到中文无衬线字体: {sans_font}")
print(f"检测到中文等宽字体: {mono_font}")

# 生成Pandoc模板
def generate_pandoc_template(serif_font, sans_font, mono_font):
    return f"""
\\documentclass[12pt, a4paper]{{article}}
\\usepackage{{fontspec}}
\\usepackage{{xeCJK}}
\\usepackage{{geometry}}
\\usepackage{{graphicx}}
\\usepackage{{hyperref}}
\\usepackage{{fancyhdr}}
\\usepackage{{titlesec}}
\\usepackage{{titling}}
\\usepackage{{caption}}
\\usepackage{{listings}}
\\usepackage{{xcolor}}
\\usepackage{{booktabs}}
\\usepackage{{amsmath}}
\\usepackage{{amssymb}}
\\usepackage{{unicode-math}}
\\usepackage{{longtable}}
\\usepackage{{array}}
\\usepackage{{multirow}}
\\usepackage{{wrapfig}}
\\usepackage{{float}}
\\usepackage{{colortbl}}
\\usepackage{{pdflscape}}
\\usepackage{{tabu}}
\\usepackage{{threeparttable}}
\\usepackage{{threeparttablex}}
\\usepackage{{ulem}}
\\usepackage{{makecell}}
\\usepackage{{xeCJK}}
\\usepackage{{breqn}}   % 为长公式提供自动换行支持

% 添加pandoc需要的命令定义
\\providecommand{{\\pandocbounded}}[1]{{#1}}
\\providecommand{{\\tightlist}}{{\\setlength{{\\itemsep}}{{0pt}}\\setlength{{\\parskip}}{{0pt}}}}
\\providecommand{{\\noalign}}{{}}

% 设置中文字体
\\setCJKmainfont{{{serif_font}}}
\\setCJKsansfont{{{sans_font}}}
\\setCJKmonofont{{{mono_font}}}

% 设置英文字体
\\setmainfont{{Times New Roman}}
\\setsansfont{{Arial}}
\\setmonofont{{Courier New}}

% 页面设置
\\geometry{{a4paper, margin=2.5cm}}

% 标题格式
\\titleformat{{\\section}}{{\\Large\\bfseries}}{{\\thesection}}{{1em}}{{}}
\\titleformat{{\\subsection}}{{\\large\\bfseries}}{{\\thesubsection}}{{1em}}{{}}
\\titleformat{{\\subsubsection}}{{\\normalsize\\bfseries}}{{\\thesubsubsection}}{{1em}}{{}}

% 代码样式
\\definecolor{{codeback}}{{rgb}}{{0.95,0.95,0.95}}
\\definecolor{{codeframe}}{{rgb}}{{0.8,0.8,0.8}}
\\lstset{{
    backgroundcolor=\\color{{codeback}},
    frame=single,
    rulecolor=\\color{{codeframe}},
    basicstyle=\\ttfamily\\small,
    breaklines=true,
    captionpos=b
}}

% 页眉页脚设置
\\pagestyle{{fancy}}
\\fancyhf{{}}
\\fancyfoot[C]{{\\thepage}}
\\renewcommand{{\\headrulewidth}}{{0pt}}

% 图像和表格设置
\\captionsetup{{font=small}}

% 设置公式自动换行
\\allowdisplaybreaks
\\setlength{{\\mathindent}}{{0pt}}

% 超链接设置
\\hypersetup{{
    colorlinks=true,
    linkcolor=blue,
    filecolor=magenta,
    urlcolor=cyan,
}}

\\begin{{document}}

% 添加目录
\\tableofcontents
\\newpage

$body$

\\end{{document}}
"""

# 动态生成Pandoc模板
PANDOC_TEMPLATE = generate_pandoc_template(serif_font, sans_font, mono_font)

def extract_artifacts(markdown_text: str) -> Tuple[str, Dict[str, Dict]]:
    """
    从Markdown文本中提取并移除<chat-artifact>标签，返回处理后的Markdown文本和存储的artifacts
    
    Args:
        markdown_text: 原始的Markdown文本
        
    Returns:
        处理后的Markdown文本和包含artifacts的字典
    """
    artifacts = {}
    
    # 正则表达式来匹配<chat-artifact>标签
    pattern = r'<chat-artifact\s+id="([^"]+)"\s+version="([^"]+)"\s+type="([^"]+)"\s+title="([^"]+)">([\s\S]*?)</chat-artifact>'
    
    def artifact_replacer(match):
        artifact_id = match.group(1)
        version = match.group(2)
        artifact_type = match.group(3)
        title = match.group(4)
        content = match.group(5).strip()
        
        artifacts[artifact_id] = {
            'id': artifact_id,
            'version': version,
            'type': artifact_type,
            'title': title,
            'content': content
        }
        
        # 插入一个占位符，稍后会被替换为适当的Markdown图片引用
        return f"\n\n[artifact:{artifact_id}]\n\n"
    
    # 替换所有<chat-artifact>标签
    processed_text = re.sub(pattern, artifact_replacer, markdown_text)
    
    return processed_text, artifacts

def process_svg_artifact(artifact: Dict, temp_dir: str) -> str:
    """处理SVG类型的artifact"""
    svg_content = artifact['content']
    svg_filename = f"{artifact['id']}.svg"
    svg_path = os.path.join(temp_dir, svg_filename)
    
    # 保存SVG到临时文件
    with open(svg_path, 'w', encoding='utf-8') as f:
        f.write(svg_content)
    
    # 转换SVG为PDF (更适合LaTeX嵌入)
    pdf_filename = f"{artifact['id']}.pdf"
    pdf_path = os.path.join(temp_dir, pdf_filename)
    
    try:
        # 使用svg2pdf将SVG转换为PDF (如果不成功，使用cairosvg转换为PNG)
        try:
            # 首先尝试使用inkscape (通常有更好的SVG支持)
            try:
                cmd = ["inkscape", svg_path, "--export-filename", pdf_path]
                result = subprocess.run(cmd, check=True, capture_output=True, text=True)
                print(f"使用Inkscape成功转换SVG: {artifact['id']}")
                image_path = pdf_path
            except (subprocess.SubprocessError, FileNotFoundError):
                # 使用cairosvg尝试直接转换为PDF
                cairosvg.svg2pdf(url=svg_path, write_to=pdf_path)
                print(f"使用cairosvg成功转换SVG到PDF: {artifact['id']}")
                image_path = pdf_path
        except Exception as e:
            # 如果转换为PDF失败，尝试转换为PNG
            print(f"转换SVG到PDF失败 ({e})，尝试转换为PNG")
            png_filename = f"{artifact['id']}.png"
            png_path = os.path.join(temp_dir, png_filename)
            cairosvg.svg2png(url=svg_path, write_to=png_path, scale=2.0)
            print(f"使用cairosvg成功转换SVG到PNG: {artifact['id']}")
            image_path = png_path
    except Exception as e:
        print(f"警告: 所有SVG转换方法均失败 ({e})，将直接使用SVG格式")
        image_path = svg_path
    
    # 返回Markdown格式的图片引用，包括图片标题
    return f"![{artifact['title']}]({image_path})\n\n*{artifact['title']}*"

def process_mermaid_artifact(artifact: Dict, temp_dir: str) -> str:
    """处理Mermaid类型的artifact"""
    mermaid_content = artifact['content']
    mermaid_filename = f"{artifact['id']}.mmd"
    mermaid_path = os.path.join(temp_dir, mermaid_filename)
    png_filename = f"{artifact['id']}.png"
    png_path = os.path.join(temp_dir, png_filename)
    
    # 保存Mermaid到临时文件
    with open(mermaid_path, 'w', encoding='utf-8') as f:
        f.write(mermaid_content)
    
    # 生成图像
    conversion_success = False
    
    # 方法1: 使用本地mermaid-cli转换 (如果已安装)
    if MERMAID_AVAILABLE:
        try:
            # 降低图表宽度，防止比例过大
            mermaid_to_image(mermaid_path, output_file=png_path, width=600)
            # 检查图片是否生成成功
            if os.path.exists(png_path) and os.path.getsize(png_path) > 100:
                conversion_success = True
                print(f"使用本地mermaid-cli成功转换图表: {artifact['id']}")
            else:
                print(f"警告: mermaid-cli生成的图像过小或无效")
        except Exception as e:
            print(f"警告: 本地Mermaid转换失败 ({e})")
    
    # 方法2: 使用mmdc命令行工具 (如果已安装)
    if not conversion_success:
        try:
            # 检查mmdc是否可用
            subprocess.run(["mmdc", "--version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # 使用mmdc转换，降低图表宽度
            cmd = [
                "mmdc",
                "-i", mermaid_path,
                "-o", png_path,
                "-w", "600",  # 减小宽度
                "-H", "500"   # 减小高度
            ]
            
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # 检查图片是否生成成功
            if os.path.exists(png_path) and os.path.getsize(png_path) > 100:
                conversion_success = True
                print(f"使用mmdc命令行工具成功转换图表: {artifact['id']}")
            else:
                print(f"警告: mmdc生成的图像过小或无效")
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            print(f"警告: mmdc命令行转换失败 ({e})")
    
    # 方法3: 使用npx @mermaid-js/mermaid-cli
    if not conversion_success:
        try:
            cmd = [
                "npx", 
                "-p", "@mermaid-js/mermaid-cli", 
                "mmdc",
                "-i", mermaid_path,
                "-o", png_path,
                "-w", "600",  # 减小宽度
                "-H", "500"   # 减小高度
            ]
            
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # 检查图片是否生成成功
            if os.path.exists(png_path) and os.path.getsize(png_path) > 100:
                conversion_success = True
                print(f"使用npx mermaid-cli成功转换图表: {artifact['id']}")
            else:
                print(f"警告: npx mermaid-cli生成的图像过小或无效")
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            print(f"警告: npx mermaid-cli转换失败 ({e})")
    
    # 方法4: 如果有docker，使用docker镜像转换
    if not conversion_success:
        try:
            # 创建临时配置文件以传递给docker
            temp_config = os.path.join(temp_dir, f"{artifact['id']}_config.json")
            with open(temp_config, 'w') as f:
                f.write('{"theme": "default"}')
            
            cmd = [
                "docker", "run", "--rm",
                "-v", f"{os.path.abspath(temp_dir)}:/data",
                "minlag/mermaid-cli",
                "-i", f"/data/{os.path.basename(mermaid_path)}",
                "-o", f"/data/{os.path.basename(png_path)}",
                "-c", f"/data/{os.path.basename(temp_config)}",
                "-w", "600"  # 尝试设置宽度
            ]
            
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # 检查图片是否生成成功
            if os.path.exists(png_path) and os.path.getsize(png_path) > 100:
                conversion_success = True
                print(f"使用Docker成功转换图表: {artifact['id']}")
            else:
                print(f"警告: Docker生成的图像过小或无效")
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            print(f"警告: Docker转换失败 ({e})")
    
    # 如果所有转换方法都失败，创建一个包含原始代码的图像
    if not conversion_success:
        create_code_image(png_path, mermaid_content, f"Mermaid图表: {artifact['title']}")
        print(f"已创建包含原始Mermaid代码的图像: {artifact['id']}")
    
    # 返回Markdown格式的图片引用，包括图片标题
    return f"![{artifact['title']}]({png_path})\n\n*{artifact['title']}*"

def create_error_image(output_path: str, error_message: str) -> None:
    """创建显示错误消息的简单SVG图像"""
    svg_content = f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="400" height="100">
        <rect width="400" height="100" fill="#f8d7da" />
        <text x="10" y="50" font-family="Arial" font-size="14" fill="#721c24">
            {error_message}
        </text>
    </svg>
    """
    try:
        cairosvg.svg2png(bytestring=svg_content.encode('utf-8'), write_to=output_path)
    except:
        # 如果转换失败，只是记录错误
        print(f"无法创建错误图像: {output_path}")

def create_code_image(output_path: str, code_content: str, title: str) -> None:
    """创建包含代码内容的图像"""
    # 将代码内容分割成行，每行不超过50个字符
    lines = []
    for line in code_content.splitlines():
        while len(line) > 50:
            lines.append(line[:50])
            line = line[50:]
        if line:
            lines.append(line)
    
    # 限制行数，避免图像过大
    if len(lines) > 30:
        lines = lines[:27] + ["...", "（代码过长，已截断）"]
    
    # 计算图像高度 (每行30像素 + 标题和边框)
    height = len(lines) * 30 + 80
    
    # 创建SVG
    svg_content = f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="800" height="{height}">
        <rect width="800" height="{height}" fill="#f8f9fa" />
        <text x="20" y="40" font-family="Arial" font-size="16" font-weight="bold">{title}</text>
        <rect x="10" y="60" width="780" height="{height-70}" fill="#f1f1f1" stroke="#cccccc" stroke-width="1" />
    """
    
    # 添加代码行
    for i, line in enumerate(lines):
        y_pos = 90 + i * 30
        # 转义XML特殊字符
        line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        svg_content += f'<text x="20" y="{y_pos}" font-family="Courier New" font-size="14">{line}</text>\n'
    
    svg_content += "</svg>"
    
    # 转换为PNG
    try:
        cairosvg.svg2png(bytestring=svg_content.encode('utf-8'), write_to=output_path, scale=1.0)
    except Exception as e:
        print(f"无法创建代码图像: {e}")
        # 如果转换失败，保存SVG文件
        svg_path = output_path.replace('.png', '.svg')
        with open(svg_path, 'w', encoding='utf-8') as f:
            f.write(svg_content)
        print(f"已保存SVG文件: {svg_path}")

def replace_artifacts_in_markdown(markdown_content: str, artifacts: Dict, temp_dir: str) -> str:
    """
    在Markdown中替换artifact占位符为实际内容
    
    Args:
        markdown_content: 包含占位符的Markdown内容
        artifacts: artifacts字典
        temp_dir: 临时目录路径
        
    Returns:
        处理后的Markdown内容
    """
    lines = markdown_content.split('\n')
    result_lines = []
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('[artifact:') and line.endswith(']'):
            artifact_id = line[10:-1]  # 提取artifact ID
            
            if artifact_id in artifacts:
                artifact = artifacts[artifact_id]
                replacement = ''
                
                # 根据artifact类型进行处理
                if artifact['type'] == 'image/svg+xml':
                    replacement = process_svg_artifact(artifact, temp_dir)
                elif artifact['type'] == 'application/vnd.chat.mermaid':
                    replacement = process_mermaid_artifact(artifact, temp_dir)
                else:
                    replacement = f"*{artifact['title']} (不支持的类型: {artifact['type']})*"
                
                # 添加替换内容
                result_lines.append(replacement)
            else:
                # 如果找不到artifact，保留原始行
                result_lines.append(line)
        else:
            # 添加非artifact行
            result_lines.append(lines[i])
        
        i += 1
    
    return '\n'.join(result_lines)

def markdown_to_pdf(markdown_text: str, output_path: str, temp_dir: str) -> None:
    """
    使用pandoc将Markdown文本转换为PDF
    
    Args:
        markdown_text: Markdown文本
        output_path: 输出PDF文件路径
        temp_dir: 临时目录路径
    """
    # 提取artifacts
    processed_markdown, artifacts = extract_artifacts(markdown_text)
    
    # 替换artifacts为Markdown图片引用
    processed_markdown = replace_artifacts_in_markdown(processed_markdown, artifacts, temp_dir)
    
    # 创建临时Markdown文件
    temp_md_path = os.path.join(temp_dir, "temp.md")
    with open(temp_md_path, 'w', encoding='utf-8') as f:
        f.write(processed_markdown)
    
    # 创建临时模板文件
    template_path = os.path.join(temp_dir, "template.tex")
    with open(template_path, 'w', encoding='utf-8') as f:
        f.write(PANDOC_TEMPLATE)
    
    # 使用pandoc将Markdown转换为PDF（先尝试使用更简单的参数）
    cmd = [
        "pandoc",
        temp_md_path,
        "-o", output_path,
        "--pdf-engine=xelatex",
        "-V", f"CJKmainfont={serif_font}",
        "-V", f"CJKsansfont={sans_font}",
        "-V", f"CJKmonofont={mono_font}",
        "-V", "geometry:margin=2.5cm",
        "-V", "colorlinks=true",
        "--toc",
        "--toc-depth=3"
    ]
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"PDF已生成: {output_path}")
    except subprocess.CalledProcessError as e:
        print(f"Pandoc转换失败: {e}")
        print(f"错误输出: {e.stderr}")
        
        # 尝试使用备用方法（不使用自定义模板，但添加必要的中文字体支持）
        print("尝试使用备用方法转换...")
        try:
            cmd_fallback = [
                "pandoc",
                temp_md_path,
                "-o", output_path,
                "--pdf-engine=xelatex",
                "-V", f"CJKmainfont={serif_font}",
                "--toc"
            ]
            result = subprocess.run(cmd_fallback, check=True, capture_output=True, text=True)
            print(f"PDF已使用备用方法生成: {output_path}")
        except subprocess.CalledProcessError as e2:
            print(f"备用方法也失败: {e2}")
            print(f"错误输出: {e2.stderr}")
            
            # 尝试最简单的转换方式
            try:
                print("尝试使用最简单的方法转换...")
                cmd_simple = [
                    "pandoc",
                    temp_md_path,
                    "-o", output_path,
                    "--pdf-engine=xelatex"
                ]
                result = subprocess.run(cmd_simple, check=True, capture_output=True, text=True)
                print(f"PDF已使用最简单方法生成: {output_path}")
            except subprocess.CalledProcessError as e3:
                print(f"最简单方法也失败: {e3}")
                print(f"错误输出: {e3.stderr}")
                raise

def process_markdown_to_pdf(input_path: str, output_path: Optional[str] = None) -> None:
    """
    处理Markdown文件并转换为PDF
    
    Args:
        input_path: Markdown文件路径
        output_path: 可选的PDF输出路径
    """
    # 如果未指定输出路径，使用相同的基本文件名但扩展名为.pdf
    if output_path is None:
        input_path_obj = Path(input_path)
        output_path = str(input_path_obj.with_suffix('.pdf'))
    
    # 确保输出目录存在
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # 创建临时目录存储处理过程中的文件
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # 读取Markdown文件
            with open(input_path, 'r', encoding='utf-8') as f:
                markdown_text = f.read()
            
            # 转换为PDF
            markdown_to_pdf(markdown_text, output_path, temp_dir)
            
        except Exception as e:
            print(f"处理失败: {e}")
            raise

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='将Markdown文件转换为PDF')
    parser.add_argument('input_file', help='输入的Markdown文件路径')
    parser.add_argument('-o', '--output', help='输出的PDF文件路径 (默认使用输入文件名但扩展名改为.pdf)')
    args = parser.parse_args()
    
    # 验证输入文件
    if not os.path.isfile(args.input_file):
        print(f"错误: 找不到输入文件 '{args.input_file}'")
        sys.exit(1)
    
    # 处理转换
    try:
        process_markdown_to_pdf(args.input_file, args.output)
    except Exception as e:
        print(f"转换过程中发生错误: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main() 