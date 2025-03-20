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

# 使用已安装的mermaid-py包进行转换
try:
    import mermaid as md
    from mermaid.graph import Graph
    MERMAID_AVAILABLE = True
    print("已找到mermaid-py包，将使用它来转换mermaid图表。")
except ImportError:
    MERMAID_AVAILABLE = False
    print("警告: 未找到mermaid-py包，将使用替代方案转换mermaid图表。")
    print("要使用本地转换，请安装: pip install mermaid-py")

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
\\usepackage{{bm}}     % 提供更好的粗体数学符号支持

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

% 添加对粗体希腊字母的更好支持
\\newcommand{{\\mbf}}[1]{{\\mathbf{{#1}}}}
\\newcommand{{\\mbfOmega}}{{\\bm{{\\Omega}}}}
\\newcommand{{\\mbfomega}}{{\\bm{{\\omega}}}}

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
    
    # 处理直接嵌入的SVG代码
    processed_text, svg_artifacts = extract_inline_svg(processed_text, len(artifacts))
    artifacts.update(svg_artifacts)
    
    # 处理直接嵌入的Mermaid流程图
    processed_text, mermaid_artifacts = extract_inline_mermaid(processed_text, len(artifacts))
    artifacts.update(mermaid_artifacts)
    
    # 处理LaTeX数学公式中的特殊符号
    processed_text = preprocess_latex_math(processed_text)
    
    return processed_text, artifacts

def preprocess_latex_math(markdown_text: str) -> str:
    """
    预处理Markdown中的LaTeX数学公式，确保特殊符号被正确处理
    
    Args:
        markdown_text: 原始的Markdown文本
        
    Returns:
        处理后的Markdown文本
    """
    # 处理行内数学公式 $...$
    # 确保数学公式被正确处理
    def process_math(match):
        math_content = match.group(1)
        # 这里不做太多处理，只确保内容完整传递
        return f"${math_content}$"
    
    processed_text = re.sub(r'\$([^$]+?)\$', process_math, markdown_text)
    
    # 处理行间数学公式 $$...$$
    def process_display_math(match):
        math_content = match.group(1)
        return f"$${math_content}$$"
    
    processed_text = re.sub(r'\$\$([\s\S]+?)\$\$', process_display_math, processed_text)
    
    return processed_text

def extract_inline_svg(markdown_text: str, start_id: int = 0) -> Tuple[str, Dict[str, Dict]]:
    """
    从Markdown文本中提取直接嵌入的SVG代码和```svg代码块
    
    Args:
        markdown_text: Markdown文本
        start_id: 起始ID编号
        
    Returns:
        处理后的Markdown文本和SVG artifacts字典
    """
    artifacts = {}
    
    # 正则表达式匹配<svg>标签，包括所有属性和内容
    inline_pattern = r'(<svg[\s\S]*?</svg>)'
    
    # 正则表达式匹配```svg代码块
    codeblock_pattern = r'```svg\s*([\s\S]*?)```'
    
    def svg_replacer(match, is_codeblock=False):
        nonlocal start_id
        svg_content = ""
        
        if is_codeblock:
            code_content = match.group(1).strip()
            # 检查代码块内容是否已经是完整的SVG
            if code_content.startswith('<svg') and code_content.endswith('</svg>'):
                svg_content = code_content
            else:
                # 不是有效的SVG，返回原始内容
                return match.group(0)
        else:
            svg_content = match.group(1)
        
        # 确保SVG内容不为空且格式正确
        if not svg_content or not svg_content.startswith('<svg'):
            return match.group(0)
            
        # 为SVG生成唯一ID
        artifact_id = f"inline_svg_{start_id}"
        start_id += 1
        
        # 尝试从SVG中提取标题
        title_match = re.search(r'<title>(.*?)</title>', svg_content)
        title = title_match.group(1) if title_match else f"内嵌SVG图形 {start_id}"
        
        # 存储SVG artifact
        artifacts[artifact_id] = {
            'id': artifact_id,
            'version': '1.0',
            'type': 'image/svg+xml',
            'title': title,
            'content': svg_content
        }
        
        # 返回占位符
        return f"\n\n[artifact:{artifact_id}]\n\n"
    
    # 先替换所有SVG代码块，然后再处理内联SVG（避免内联SVG被重复匹配）
    processed_text = re.sub(codeblock_pattern, lambda m: svg_replacer(m, True), markdown_text)
    processed_text = re.sub(inline_pattern, lambda m: svg_replacer(m, False), processed_text)
    
    return processed_text, artifacts

def extract_inline_mermaid(markdown_text: str, start_id: int = 0) -> Tuple[str, Dict[str, Dict]]:
    """
    从Markdown文本中提取直接嵌入的Mermaid流程图代码
    
    Args:
        markdown_text: Markdown文本
        start_id: 起始ID编号
        
    Returns:
        处理后的Markdown文本和Mermaid artifacts字典
    """
    artifacts = {}
    
    # 正则表达式匹配```mermaid代码块 - 改进以处理不同格式
    # 处理两种情况：1) ```mermaid换行内容 2) ```mermaid直接内容
    pattern = r'```mermaid\s*([\s\S]*?)```'
    
    def mermaid_replacer(match):
        nonlocal start_id
        mermaid_content = match.group(1).strip()
        
        # 确保内容不为空
        if not mermaid_content:
            return match.group(0)
            
        # 为Mermaid生成唯一ID
        artifact_id = f"inline_mermaid_{start_id}"
        start_id += 1
        
        # 尝试从Mermaid中提取标题或类型
        title = "流程图"
        if mermaid_content.startswith('flowchart') or mermaid_content.startswith('graph'):
            title = "流程图"
        elif mermaid_content.startswith('sequenceDiagram'):
            title = "时序图"
        elif mermaid_content.startswith('classDiagram'):
            title = "类图"
        elif mermaid_content.startswith('stateDiagram'):
            title = "状态图"
        elif mermaid_content.startswith('erDiagram'):
            title = "ER图"
        elif mermaid_content.startswith('gantt'):
            title = "甘特图"
        elif mermaid_content.startswith('pie'):
            title = "饼图"
        
        # 存储Mermaid artifact
        artifacts[artifact_id] = {
            'id': artifact_id,
            'version': '1.0',
            'type': 'application/vnd.chat.mermaid',
            'title': title,
            'content': mermaid_content
        }
        
        # 返回占位符
        return f"\n\n[artifact:{artifact_id}]\n\n"
    
    # 替换所有Mermaid代码块
    processed_text = re.sub(pattern, mermaid_replacer, markdown_text)
    
    return processed_text, artifacts

def process_svg_artifact(artifact: Dict, temp_dir: str) -> str:
    """处理SVG类型的artifact"""
    svg_content = artifact['content']
    svg_filename = f"{artifact['id']}.svg"
    svg_path = os.path.join(temp_dir, svg_filename)
    
    # 保存SVG到临时文件
    with open(svg_path, 'w', encoding='utf-8') as f:
        f.write(svg_content)
    
    # 转换SVG为PNG (更适合嵌入)
    png_filename = f"{artifact['id']}.png"
    png_path = os.path.join(temp_dir, png_filename)
    
    try:
        # 首先尝试使用inkscape (通常有更好的SVG支持)
        try:
            # 使用更高的DPI设置提高图像质量
            cmd = ["inkscape", svg_path, "--export-filename", png_path, "--export-dpi=300"]
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(f"使用Inkscape成功转换SVG: {artifact['id']}")
            image_path = png_path
        except (subprocess.SubprocessError, FileNotFoundError):
            # 使用cairosvg尝试直接转换为PNG
            cairosvg.svg2png(url=svg_path, write_to=png_path, scale=2.0)
            print(f"使用cairosvg成功转换SVG到PNG: {artifact['id']}")
            image_path = png_path
    except Exception as e:
        # 如果转换失败，使用原始SVG
        print(f"转换SVG到PNG失败 ({e})，将使用原始SVG格式")
        image_path = svg_path
    
    # 返回Markdown格式的图片引用，包括图片标题
    # 使用纯文件名而不是路径，确保在Pandoc处理时能正确找到图像
    just_filename = os.path.basename(image_path)
    caption = artifact['title'] if 'title' in artifact else "图像"
    
    return f"![{caption}]({just_filename})\n\n*{caption}*"

def process_mermaid_artifact(artifact: Dict, temp_dir: str) -> str:
    """处理Mermaid类型的artifact"""
    mermaid_content = artifact['content']
    
    # 将graph格式转换为flowchart格式（兼容旧版Mermaid语法）
    if mermaid_content.startswith('graph '):
        mermaid_content = 'flowchart ' + mermaid_content[6:]
    
    mermaid_filename = f"{artifact['id']}.mmd"
    mermaid_path = os.path.join(temp_dir, mermaid_filename)
    png_filename = f"{artifact['id']}.png"
    png_path = os.path.join(temp_dir, png_filename)
    svg_filename = f"{artifact['id']}.svg"
    svg_path = os.path.join(temp_dir, svg_filename)
    
    # 保存Mermaid到临时文件
    with open(mermaid_path, 'w', encoding='utf-8') as f:
        f.write(mermaid_content)
    
    # 生成图像
    conversion_success = False
    
    # 方法1: 尝试使用Python的graphviz库来转换简单的流程图
    if mermaid_content.startswith('flowchart') or mermaid_content.startswith('graph'):
        try:
            import graphviz
            
            # 创建一个有向图
            dot = graphviz.Digraph(comment=artifact['title'], format='png')
            dot.attr('graph', rankdir='TB', size='8,10', dpi='300')
            # 确保使用支持中文的字体，尤其是节点文本
            dot.attr('node', shape='box', style='filled,rounded', fillcolor='lightblue', 
                   fontname=f'"{sans_font}"')
            dot.attr('edge', fontname=f'"{sans_font}"')
            
            # 解析mermaid内容来提取节点和边
            lines = mermaid_content.strip().split('\n')
            
            print(f"解析Mermaid图表: {artifact['id']}")
            
            # 处理flowchart的方向
            direction = "TB"  # 默认方向：从上到下
            if len(lines) > 0:
                first_line = lines[0].strip()
                if "LR" in first_line:
                    direction = "LR"  # 从左到右
                elif "RL" in first_line:
                    direction = "RL"  # 从右到左
                elif "BT" in first_line:
                    direction = "BT"  # 从下到上
                elif "TD" in first_line:
                    direction = "TB"  # 从上到下（与TB相同）
            
            dot.attr('graph', rankdir=direction)
            
            # 跳过第一行，因为它是flowchart类型声明
            nodes = {}
            node_styles = {}  # 存储每个节点的样式
            edges = []
            
            # 定义不同类型节点的正则表达式
            # 矩形节点 A[内容]
            rect_node_regex = r'^\s*([A-Za-z0-9_]+)\s*\[\s*([^\]]+)\s*\]'
            
            # 圆角矩形 A([内容]) 或 A(([内容])) 或 A([内容])
            rounded_rect_regex = r'^\s*([A-Za-z0-9_]+)\s*\(\s*\[\s*([^\]]+)\s*\]\s*\)'
            
            # 圆形节点 A((内容))
            circle_node_regex = r'^\s*([A-Za-z0-9_]+)\s*\(\(\s*([^\)]+)\s*\)\)'
            
            # 菱形节点 A{内容}
            rhombus_node_regex = r'^\s*([A-Za-z0-9_]+)\s*\{\s*([^\}]+)\s*\}'
            
            # 六边形节点 A{{内容}}
            hexagon_node_regex = r'^\s*([A-Za-z0-9_]+)\s*\{\{\s*([^\}]+)\s*\}\}'
            
            # 简单文本节点（没有形状标记）
            text_node_regex = r'^\s*([A-Za-z0-9_]+)'
            
            # 解析节点定义 - 支持所有节点类型和带引号的内容
            for line in lines[1:]:
                line = line.strip()
                if not line or " --> " in line or " --> " in line or "style " in line:
                    continue
                
                # 尝试匹配不同类型的节点
                
                # 1. 矩形节点
                rect_match = re.search(rect_node_regex, line)
                if rect_match:
                    node_id, node_label = rect_match.groups()
                    # 删除可能的引号
                    node_label = node_label.strip('"\'')
                    # 替换<br>为换行符
                    node_label = node_label.replace("<br>", "\n")
                    nodes[node_id] = node_label
                    node_styles[node_id] = {'shape': 'box', 'style': 'filled,rounded', 'fillcolor': 'lightblue'}
                    continue
                
                # 2. 圆角矩形节点
                rounded_match = re.search(rounded_rect_regex, line)
                if rounded_match:
                    node_id, node_label = rounded_match.groups()
                    # 删除可能的引号
                    node_label = node_label.strip('"\'')
                    # 替换<br>为换行符
                    node_label = node_label.replace("<br>", "\n")
                    nodes[node_id] = node_label
                    node_styles[node_id] = {'shape': 'box', 'style': 'filled,rounded', 'fillcolor': 'lightgreen'}
                    continue
                
                # 3. 圆形节点
                circle_match = re.search(circle_node_regex, line)
                if circle_match:
                    node_id, node_label = circle_match.groups()
                    # 删除可能的引号
                    node_label = node_label.strip('"\'')
                    nodes[node_id] = node_label
                    node_styles[node_id] = {'shape': 'circle', 'style': 'filled', 'fillcolor': 'lightblue'}
                    continue
                
                # 4. 菱形节点
                rhombus_match = re.search(rhombus_node_regex, line)
                if rhombus_match:
                    node_id, node_label = rhombus_match.groups()
                    # 删除可能的引号
                    node_label = node_label.strip('"\'')
                    nodes[node_id] = node_label
                    node_styles[node_id] = {'shape': 'diamond', 'style': 'filled', 'fillcolor': 'lightyellow'}
                    continue
                
                # 5. 六边形节点
                hexagon_match = re.search(hexagon_node_regex, line)
                if hexagon_match:
                    node_id, node_label = hexagon_match.groups()
                    # 删除可能的引号
                    node_label = node_label.strip('"\'')
                    nodes[node_id] = node_label
                    node_styles[node_id] = {'shape': 'hexagon', 'style': 'filled', 'fillcolor': 'lightpink'}
                    continue
                
                # 6. 如果只有节点ID，添加为简单文本节点
                text_match = re.search(text_node_regex, line)
                if text_match:
                    node_id = text_match.group(1)
                    if node_id not in nodes:
                        nodes[node_id] = node_id
                        node_styles[node_id] = {'shape': 'plaintext', 'style': '', 'fillcolor': 'white'}
            
            # 检查是否有边定义但无对应节点的情况
            for line in lines[1:]:
                if " --> " in line or " --> " in line:
                    parts = []
                    if " --> " in line:
                        parts = line.split(" --> ")
                    elif " --> " in line:
                        parts = line.split(" --> ")
                        
                    if not parts:
                        continue
                        
                    # 处理源节点
                    src = parts[0].strip()
                    src_match = re.search(r'^([A-Za-z0-9_]+)', src)
                    if src_match:
                        src_id = src_match.group(1)
                        if src_id not in nodes:
                            # 提取可能的节点内容
                            content_match = re.search(r'\[([^\]]+)\]', src)
                            if content_match:
                                content = content_match.group(1).strip('"\'')
                                nodes[src_id] = content
                                node_styles[src_id] = {'shape': 'box', 'style': 'filled,rounded', 'fillcolor': 'lightblue'}
                            else:
                                nodes[src_id] = src_id
                                node_styles[src_id] = {'shape': 'plaintext', 'style': '', 'fillcolor': 'white'}
                    
                    # 处理目标节点
                    if len(parts) > 1:
                        tgt = parts[1].strip()
                        tgt_match = re.search(r'^([A-Za-z0-9_]+)', tgt)
                        if tgt_match:
                            tgt_id = tgt_match.group(1)
                            if tgt_id not in nodes:
                                # 提取可能的节点内容
                                content_match = re.search(r'\[([^\]]+)\]', tgt)
                                if content_match:
                                    content = content_match.group(1).strip('"\'')
                                    nodes[tgt_id] = content
                                    node_styles[tgt_id] = {'shape': 'box', 'style': 'filled,rounded', 'fillcolor': 'lightblue'}
                                else:
                                    nodes[tgt_id] = tgt_id
                                    node_styles[tgt_id] = {'shape': 'plaintext', 'style': '', 'fillcolor': 'white'}
            
            # 解析所有边
            for line in lines[1:]:
                line = line.strip()
                if " --> " in line or " --> " in line:
                    parts = []
                    if " --> " in line:
                        parts = line.split(" --> ")
                    elif " --> " in line:
                        parts = line.split(" --> ")
                        
                    if not parts:
                        continue
                        
                    source = parts[0].strip()
                    target = parts[1].strip()
                    
                    # 提取源节点ID
                    source_match = re.search(r'^([A-Za-z0-9_]+)', source)
                    if source_match:
                        source_id = source_match.group(1)
                    else:
                        continue
                    
                    # 提取目标节点ID
                    target_match = re.search(r'^([A-Za-z0-9_]+)', target)
                    if target_match:
                        target_id = target_match.group(1)
                    else:
                        continue
                    
                    # 检查是否有边标签
                    label = ""
                    label_match = re.search(r'\|([^|]+)\|', line)
                    if label_match:
                        label = label_match.group(1)
                    
                    # 创建边
                    if label:
                        edges.append((source_id, target_id, label))
                    else:
                        edges.append((source_id, target_id))
            
            # 解析样式设置
            for line in lines[1:]:
                line = line.strip()
                if line.startswith('style '):
                    # 例如 style A fill:#f9f,stroke:#333,stroke-width:2px
                    parts = line.split(' ', 2)
                    if len(parts) >= 3:
                        node_id = parts[1]
                        style_str = parts[2]
                        if node_id in nodes:
                            # 保存基本形状
                            shape = node_styles.get(node_id, {}).get('shape', 'box')
                            
                            # 解析style属性
                            fillcolor = 'lightblue'  # 默认填充颜色
                            if 'fill:' in style_str:
                                fill_match = re.search(r'fill:(#[0-9a-fA-F]+)', style_str)
                                if fill_match:
                                    fillcolor = fill_match.group(1)
                            
                            # 更新节点样式
                            node_styles[node_id] = {
                                'shape': shape,
                                'style': 'filled,rounded',
                                'fillcolor': fillcolor
                            }
            
            # 添加所有节点，应用它们的样式
            for node_id, label in nodes.items():
                style = node_styles.get(node_id, {'shape': 'box', 'style': 'filled,rounded', 'fillcolor': 'lightblue'})
                
                # 设置节点属性
                attrs = {
                    'shape': style.get('shape', 'box'),
                    'style': style.get('style', 'filled,rounded'),
                    'fillcolor': style.get('fillcolor', 'lightblue'),
                    'fontname': f'"{sans_font}"',
                    'fontsize': '14'  # 增加字体大小以提高可读性
                }
                
                dot.node(node_id, label, **attrs)
            
            # 添加所有边
            for edge in edges:
                if len(edge) == 2:
                    source, target = edge
                    dot.edge(source, target)
                elif len(edge) == 3:
                    source, target, label = edge
                    dot.edge(source, target, label)
                else:
                    source, target, label, style = edge
                    if style == 'dashed':
                        dot.edge(source, target, label, style='dashed')
                    else:
                        dot.edge(source, target, label)
            
            # 设置更合理的图形布局参数
            dot.attr('graph', dpi='400', nodesep='0.8', ranksep='1.0', splines='true', overlap='false')
            
            # 保存为PNG - 使用更高的DPI以提高清晰度
            dot_output = os.path.join(temp_dir, artifact['id'])
            dot.render(dot_output, cleanup=True)
            png_output = dot_output + '.png'
            if os.path.exists(png_output):
                # 复制文件到预期的输出路径
                if png_output != png_path:  # 确保源和目标不是同一个文件
                    shutil.copy(png_output, png_path)
                conversion_success = True
                print(f"使用Graphviz成功转换流程图: {artifact['id']}")
        except Exception as e:
            print(f"警告: Graphviz转换失败 ({e})")
    
    # 方法2: 使用mermaid-cli (如果可用)
    if not conversion_success:
        try:
            cmd = [
                "npx", 
                "@mermaid-js/mermaid-cli", 
                "--input", mermaid_path,
                "--output", png_path,
                "--backgroundColor", "white",
                "--width", "800",
                "--height", "600",
                "--cssFile", "/dev/null"  # 防止加载默认CSS
            ]
            
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            
            # 检查图片是否生成成功
            if os.path.exists(png_path) and os.path.getsize(png_path) > 100:
                conversion_success = True
                print(f"使用mermaid-cli成功转换图表: {artifact['id']}")
            else:
                print(f"警告: mermaid-cli生成的图像过小或无效")
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            print(f"警告: mermaid-cli转换失败 ({e})")
    
    # 方法3: 创建特殊的SVG格式的Mermaid代码图像，使用正确的中文字体
    if not conversion_success:
        try:
            # 创建特殊的SVG来显示mermaid图表
            lines = mermaid_content.split('\n')
            
            svg_width = 800
            svg_height = 400 + (len(lines) * 15)  # 根据行数调整高度
            
            # 确保引用正确的中文字体
            svg_content = f"""
            <svg xmlns="http://www.w3.org/2000/svg" width="{svg_width}" height="{svg_height}">
                <style>
                    @font-face {{
                        font-family: 'CustomFont';
                        src: local('Arial'), local('{sans_font}'), local('Microsoft YaHei'), local('微软雅黑'), local('SimSun'), local('宋体');
                    }}
                    .title {{ font-family: 'CustomFont', sans-serif; font-size: 18px; font-weight: bold; }}
                    .mermaid {{ font-family: 'CustomFont', monospace; font-size: 14px; white-space: pre; }}
                    .box {{ background-color: #f0f0f0; padding: 15px; border-radius: 8px; border: 1px solid #ddd; }}
                    .flowchart {{ font-weight: bold; }}
                </style>
                
                <rect width="{svg_width}" height="{svg_height}" fill="#ffffff" />
                <text x="20" y="30" class="title">{artifact['title']}</text>
                
                <foreignObject x="20" y="50" width="{svg_width-40}" height="{svg_height-70}">
                    <div xmlns="http://www.w3.org/1999/xhtml" class="box">
                        <pre class="mermaid" style="margin: 0;">{mermaid_content.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')}</pre>
                    </div>
                </foreignObject>
            </svg>
            """
            
            # 保存SVG到临时文件
            with open(svg_path, 'w', encoding='utf-8') as f:
                f.write(svg_content)
            
            # 使用cairosvg将SVG转换为PNG
            cairosvg.svg2png(url=svg_path, write_to=png_path, scale=1.5)
            conversion_success = True
            print(f"已创建增强的Mermaid代码图像: {artifact['id']}")
        except Exception as e:
            print(f"警告: 增强图像创建失败 ({e})")
    
    # 最后的备选方案：使用改进的代码图像
    if not conversion_success:
        improved_code_image(png_path, mermaid_content, f"Mermaid流程图: {artifact['title']}")
        print(f"已创建改进的Mermaid代码图像（最终方案）: {artifact['id']}")
    
    # 返回Markdown格式的图片引用，包括图片标题
    rel_path = os.path.basename(png_path)
    caption = artifact['title'] if 'title' in artifact else "流程图"
    
    return f"![{caption}]({rel_path})\n\n*{caption}*"

def improved_code_image(output_path, code_content, title):
    """创建美观的代码图像，支持中文字符"""
    # 将代码内容分割成行
    lines = code_content.splitlines()
    
    # 限制行数，避免图像过大
    if len(lines) > 30:
        lines = lines[:27] + ["...", "（代码过长，已截断）"]
    
    # 计算图像高度 (每行24像素 + 标题和边框)
    height = len(lines) * 24 + 80
    width = 800
    
    # 创建SVG
    svg_content = f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">
        <rect width="{width}" height="{height}" fill="#f8f9fa" />
        <text x="20" y="40" font-family="Arial, 'Microsoft YaHei', '微软雅黑', sans-serif" font-size="16" font-weight="bold">{title}</text>
        <rect x="10" y="60" width="{width-20}" height="{height-70}" fill="#f1f1f1" stroke="#cccccc" stroke-width="1" />
    """
    
    # 添加代码行
    for i, line in enumerate(lines):
        y_pos = 84 + i * 24
        # 转义XML特殊字符
        line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        svg_content += f'<text x="20" y="{y_pos}" font-family="Menlo, Consolas, \'Microsoft YaHei\', \'微软雅黑\', monospace" font-size="14">{line}</text>\n'
    
    svg_content += "</svg>"
    
    # 转换为PNG
    try:
        cairosvg.svg2png(bytestring=svg_content.encode('utf-8'), write_to=output_path, scale=1.5)
    except Exception as e:
        print(f"无法创建改进的代码图像: {e}")
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
    # 获取绝对路径，确保输出正确
    output_path = os.path.abspath(output_path)
    print(f"输出PDF将保存到: {output_path}")
    
    # 提取artifacts
    processed_markdown, artifacts = extract_artifacts(markdown_text)
    
    # 替换artifacts为Markdown图片引用
    processed_markdown = replace_artifacts_in_markdown(processed_markdown, artifacts, temp_dir)
    
    # 创建临时Markdown文件
    temp_md_path = os.path.join(temp_dir, "temp.md")
    with open(temp_md_path, 'w', encoding='utf-8') as f:
        f.write(processed_markdown)
    
    # 创建自定义的LaTeX头文件，提供更好的数学符号支持
    header_file = os.path.join(temp_dir, "header.tex")
    with open(header_file, 'w', encoding='utf-8') as f:
        f.write(r"""
% 基础数学支持包
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{amsfonts}

% 定义数学字体和符号 
\DeclareMathAlphabet{\mathbf}{OT1}{cmr}{bx}{n}
\DeclareSymbolFont{letters}{OML}{cmm}{m}{it}
\DeclareSymbolFont{operators}{OT1}{cmr}{m}{n}
\DeclareSymbolFont{symbols}{OMS}{cmsy}{m}{n}

% 定义希腊字母命令
\let\Omega\relax
\DeclareMathSymbol{\Omega}{\mathalpha}{letters}{"0A}
\let\omega\relax
\DeclareMathSymbol{\omega}{\mathalpha}{letters}{"21}
\let\theta\relax
\DeclareMathSymbol{\theta}{\mathalpha}{letters}{"12}

% 改进数学公式中的间距处理
\thickmuskip=5mu plus 3mu minus 1mu
\medmuskip=4mu plus 2mu minus 1mu
\thinmuskip=3mu

% 定义特殊的数学操作符
\DeclareMathOperator{\diff}{d}  % 微分算子
\DeclareMathOperator{\Tr}{Tr}   % 迹算子
\DeclareMathOperator{\Det}{Det} % 行列式算子
""")
    
    # 使用更直接的转换命令，确保包顺序正确
    cmd = [
        "pandoc",
        temp_md_path,
        "-o", output_path,
        "--pdf-engine=xelatex",
        "--include-in-header", header_file,
        "-V", f"CJKmainfont={serif_font}",
        "-V", "geometry:margin=2.5cm",
        "-V", "colorlinks=true",
        "--toc",
        "--toc-depth=3",
        "--listings",
        "--number-sections",
        "--resource-path", temp_dir,
        "--mathjax"  # 添加mathjax支持
    ]
    
    try:
        # 运行pandoc命令
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"PDF已生成: {output_path}")
        # 检查文件是否存在
        if os.path.exists(output_path):
            print(f"确认文件已成功生成: {output_path}")
            print(f"文件大小: {os.path.getsize(output_path)} 字节")
        else:
            print(f"警告: 文件转换似乎成功，但找不到输出文件: {output_path}")
    except subprocess.CalledProcessError as e:
        print(f"Pandoc转换失败: {e}")
        print(f"错误输出: {e.stderr}")
        
        # 尝试备用方法
        try:
            print("尝试使用备用方法转换...")
            # 使用更简单的LaTeX设置
            simple_header = os.path.join(temp_dir, "simple_header.tex")
            with open(simple_header, 'w', encoding='utf-8') as f:
                f.write(r"""
% 基础数学支持
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{amsfonts}

% 定义希腊字母命令
\let\theta\relax
\DeclareMathSymbol{\theta}{\mathalpha}{letters}{"12}

% 改进数学公式中的间距处理
\thickmuskip=5mu plus 3mu minus 1mu
\medmuskip=4mu plus 2mu minus 1mu
\thinmuskip=3mu

% 重定义粗体希腊字母命令，使用bm包
\DeclareRobustCommand{\bfseries}{\fontseries\bfdefault\selectfont}
\renewcommand{\mathbf}[1]{\text{\bfseries{#1}}}
\newcommand{\bm}[1]{\boldsymbol{#1}}
""")
            
            cmd_fallback = [
                "pandoc",
                temp_md_path,
                "-o", output_path,
                "--pdf-engine=xelatex",
                "--include-in-header", simple_header,
                "-V", f"CJKmainfont={serif_font}",
                "--resource-path", temp_dir,
                "--mathjax"
            ]
            result = subprocess.run(cmd_fallback, check=True, capture_output=True, text=True)
            print(f"PDF已使用备用方法生成: {output_path}")
        except subprocess.CalledProcessError as e2:
            print(f"备用方法也失败: {e2}")
            print(f"错误输出: {e2.stderr}")
            
            # 尝试最简单的方法
            try:
                print("尝试使用最简单的方法转换...")
                cmd_simple = [
                    "pandoc",
                    temp_md_path,
                    "-o", output_path,
                    "--pdf-engine=xelatex",
                    "-V", f"CJKmainfont={serif_font}",
                    "--resource-path", temp_dir,
                    "--mathjax"
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