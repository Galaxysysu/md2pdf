# MD2PDF

一个将Markdown文件转换为排版精美的PDF的Python工具，特别适用于包含数学公式、SVG图像和Mermaid流程图的学术文档。

## 功能特点

- 使用Pandoc作为后端，直接将Markdown转换为PDF
- 原生支持LaTeX格式的数学公式（内联公式和块级公式）
- 支持嵌入式SVG图像的渲染（来自Claude等AI生成的`<chat-artifact>`标签）
- 支持Mermaid流程图（同样来自`<chat-artifact>`标签）
- 专业的学术论文排版样式
- 保持图片在文档中的合适位置
- 自动生成PDF目录
- 长公式自动换行支持
- 自动检测并使用系统中的中文字体
- 智能调整流程图尺寸，避免过大

## 安装

1. 安装Pandoc（必需）:
   - 访问 [Pandoc安装页面](https://pandoc.org/installing.html)
   - 根据您的操作系统选择合适的安装方式
   - 确保安装LaTeX引擎（XeLaTeX），在大多数LaTeX发行版中包含
   
2. 克隆此仓库:
   ```bash
   git clone https://github.com/yourusername/md2pdf.git
   cd md2pdf
   ```

3. 安装依赖项:
   ```bash
   pip install -r requirements.txt
   ```

4. (可选) 安装中文字体:
   - 确保系统中安装了"Source Han Serif CN"和"Source Han Sans CN"字体
   - 或者修改脚本中的字体设置为您系统上可用的字体

## 使用方法

基本用法:

```bash
python md2pdf.py 输入的Markdown文件.md
```

指定输出文件:

```bash
python md2pdf.py 输入的Markdown文件.md -o 输出的PDF文件.pdf
```

### 示例

```bash
python md2pdf.py ./概念讲解/逆变基矢量与协变基矢量的正交关系.md
```

## 支持的Markdown格式

- 标准Markdown语法（标题、列表、链接等）
- LaTeX格式的数学公式（使用`$`和`$$`包围）
- 代码块和语法高亮
- 表格
- `<chat-artifact>`标签中的SVG图像和Mermaid流程图

## 常见问题

1. **转换PDF时出现字体问题**
   - 错误可能是因为缺少指定的字体，可以修改脚本中的`PANDOC_TEMPLATE`部分中的字体设置
   - 例如，将`\setCJKmainfont{Source Han Serif CN}`改为您系统上可用的字体

2. **Mermaid图表不显示**
   - 默认使用在线Mermaid服务，需要网络连接。如需离线使用，请安装`mermaid-cli`（需要Node.js）

3. **Pandoc转换失败**
   - 确保已正确安装Pandoc和XeLaTeX
   - 在Windows上，可能需要将Pandoc和TeX Live添加到PATH环境变量中

## 许可证

MIT 

## 最新功能

- **自动生成目录**: 为生成的PDF文档自动创建目录，提高文档可读性
- **长公式自动换行**: 使用breqn包支持长数学公式自动换行，防止公式超出页面边界
- **流程图尺寸优化**: 自动调整Mermaid流程图尺寸，使其更适合页面布局
- **中文字体自动检测**: 自动检测系统中可用的中文字体，无需手动配置
- **多级嵌套备用方案**: 提供多级备用转换方案，即使遇到问题也能生成PDF文件 