'''
class CategoryType(IntEnum):
     title = 0               # 标题
     plain_text = 1          # 文本
     abandon = 2             # 包括页眉页脚页码和页面注释
     figure = 3              # 图片
     figure_caption = 4      # 图片描述
     table = 5               # 表格
     table_caption = 6       # 表格描述
     table_footnote = 7      # 表格注释
     isolate_formula = 8     # 行间公式
     formula_caption = 9     # 行间公式的标号

     embedding = 13          # 行内公式
     isolated = 14           # 行间公式
     text = 15               # ocr 识别结果
'''
import json
import re
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt

def find_model_json_files(directory='.'):
    """查找目录下的model.json文件"""
    directory = Path(directory)
    json_files = []
    
    # 查找所有model.json文件
    for json_file in directory.glob('*model.json'):
        json_files.append(json_file)
    
    return json_files

def process_layout_dets(layout_dets):
    """处理布局检测结果"""
    content = []
    
    # 按y坐标排序
    sorted_dets = sorted(layout_dets, key=lambda x: x['poly'][1])
    
    for det in sorted_dets:
        # 只处理文本类型
        if det['category_id'] == 15 and 'text' in det:
            content.append(det['text'])
    
    return content  # 返回列表而不是拼接的字符串

def convert_to_markdown(model_data):
    """将model.json转换为Markdown格式"""
    markdown_content = []
    
    # 检查数据结构
    if isinstance(model_data, list):
        # 如果是列表，假设每个元素是一个页面
        for page_info in model_data:
            page_no = page_info.get('page_no', 0)
            if 'layout_dets' in page_info:
                content_lines = process_layout_dets(page_info['layout_dets'])
                if content_lines:
                    # 添加页码标记
                    markdown_content.append(f'```page\n{page_no + 1}\n```')
                    # 每行文本单独一行
                    for line in content_lines:
                        markdown_content.append(line)
                    markdown_content.append('---')  # 页面分隔符
    
    return '\n'.join(markdown_content)

def main():
    console = Console()
    
    # 获取工作目录
    work_dir = Prompt.ask("请输入工作目录", default=".").strip().strip('"')
    if not work_dir:
        work_dir = "."
    
    # 查找匹配的文件
    with console.status("[bold green]查找model.json文件...[/bold green]"):
        json_files = find_model_json_files(work_dir)
    
    if not json_files:
        console.print(f"\n[red]在目录 {work_dir} 中没有找到model.json文件[/red]")
        return
    
    console.print("\n[bold]找到以下文件:[/bold]")
    for i, json_file in enumerate(json_files, 1):
        console.print(f"{i}. [cyan]{json_file.name}[/cyan]")
    
    # 选择文件
    file_choice = Prompt.ask("选择要处理的文件编号", default="1")
    try:
        file_index = int(file_choice) - 1
        if not (0 <= file_index < len(json_files)):
            console.print("[red]无效的文件编号，使用第一个文件[/red]")
            file_index = 0
    except ValueError:
        console.print("[red]无效的输入，使用第一个文件[/red]")
        file_index = 0
    
    json_file = json_files[file_index]
    
    try:
        # 读取JSON文件
        with console.status("[bold green]读取JSON文件...[/bold green]"):
            with open(json_file, 'r', encoding='utf-8') as f:
                model_data = json.load(f)
        
        # 检查数据结构
        if not isinstance(model_data, list):
            raise ValueError(f"不支持的数据结构: {type(model_data)}")
        
        # 转换为Markdown格式
        with console.status("[bold green]转换为Markdown格式...[/bold green]"):
            markdown_content = convert_to_markdown(model_data)
        
        # 生成输出文件路径
        output_path = json_file.parent / f"{json_file.stem.replace('_model', '')}.md"
        
        # 保存Markdown文件
        with console.status("[bold green]保存Markdown文件...[/bold green]"):
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
        
        console.print(f"\n[bold green]✓ 处理完成！[/bold green]")
        console.print(f"输出文件：[cyan]{output_path}[/cyan]")
        
        # 显示统计信息
        total_pages = len(model_data)
        console.print(f"\n[bold]统计信息:[/bold]")
        console.print(f"- 总页数: {total_pages}")
        
    except Exception as e:
        console.print(f"\n[bold red]✗ 处理失败[/bold red]")
        console.print(f"[red]{str(e)}[/red]")
        import traceback
        console.print(traceback.format_exc())

if __name__ == '__main__':
    main() 