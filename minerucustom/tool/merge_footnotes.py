import re
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt

def parse_page_blocks(markdown_text):
    """解析MD文件中的页码块"""
    page_blocks = []
    current_page = None
    current_content = []
    current_footnotes = []
    
    lines = markdown_text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # 检测页码块开始
        if line.strip() == '```page':
            # 保存之前的块
            if current_page is not None:
                page_blocks.append({
                    'page': current_page,
                    'content': '\n'.join(current_content),
                    'footnotes': current_footnotes
                })
            
            # 开始新的块
            i += 1
            if i < len(lines):
                page_match = re.match(r'第(\d+)页', lines[i].strip())
                if page_match:
                    current_page = int(page_match.group(1))
                    current_content = []
                    current_footnotes = []
            
            # 跳过结束标记
            i += 1
            while i < len(lines) and lines[i].strip() != '```':
                i += 1
            i += 1
            continue
        
        # 检测脚注块
        elif line.strip() == '```footnote':
            i += 1
            footnote_content = []
            while i < len(lines) and lines[i].strip() != '```':
                footnote_content.append(lines[i])
                i += 1
            if footnote_content:
                current_footnotes.append('\n'.join(footnote_content))
            i += 1
            continue
        
        # 普通内容
        elif current_page is not None:
            current_content.append(line)
        
        i += 1
    
    # 保存最后一个块
    if current_page is not None:
        page_blocks.append({
            'page': current_page,
            'content': '\n'.join(current_content),
            'footnotes': current_footnotes
        })
    
    return page_blocks

def merge_page_blocks(page_blocks1, page_blocks2):
    """合并两个页面的块"""
    # 创建页码到块的映射
    page_map1 = {block['page']: block for block in page_blocks1}
    page_map2 = {block['page']: block for block in page_blocks2}
    
    # 获取所有页码
    all_pages = sorted(set(page_map1.keys()) | set(page_map2.keys()))
    
    # 合并块
    merged_blocks = []
    for page in all_pages:
        block1 = page_map1.get(page)
        block2 = page_map2.get(page)
        
        if block1 and block2:
            # 合并内容和脚注
            merged_block = {
                'page': page,
                'content': block1['content'],
                'footnotes': block1['footnotes'] + block2['footnotes']
            }
        elif block1:
            merged_block = block1
        else:
            merged_block = block2
        
        merged_blocks.append(merged_block)
    
    return merged_blocks

def build_merged_md(merged_blocks):
    """构建合并后的MD文件"""
    md_lines = []
    
    for block in merged_blocks:
        # 添加页码标记
        md_lines.append('```page')
        md_lines.append(f'第{block["page"]}页')
        md_lines.append('```')
        
        # 添加内容
        if block['content'].strip():
            md_lines.append(block['content'])
        
        # 添加脚注
        if block['footnotes']:
            for footnote in block['footnotes']:
                md_lines.append('```footnote')
                md_lines.append(footnote)
                md_lines.append('```')
        
        # 添加空行分隔
        md_lines.append('')
    
    return '\n'.join(md_lines)

def find_matching_files(directory='.'):
    """查找目录下的page.md和footnotes.md文件"""
    directory = Path(directory)
    pairs = []
    
    # 查找所有page.md文件
    for page_file in directory.glob('*_page.md'):
        # 找到对应的footnotes.md文件
        footnotes_file = page_file.parent / f"{page_file.stem.replace('_page', '_footnotes')}.md"
        if footnotes_file.exists():
            pairs.append((page_file, footnotes_file))
    
    return pairs

def main():
    console = Console()
    
    # 获取工作目录
    work_dir = Prompt.ask("请输入工作目录", default=".").strip().strip('"')
    if not work_dir:
        work_dir = "."
    
    # 查找匹配的文件
    with console.status("[bold green]查找匹配的文件...[/bold green]"):
        file_pairs = find_matching_files(work_dir)
    
    if not file_pairs:
        console.print(f"\n[red]在目录 {work_dir} 中没有找到匹配的文件对[/red]")
        return
    
    console.print("\n[bold]找到以下文件对:[/bold]")
    for i, (page_file, footnotes_file) in enumerate(file_pairs, 1):
        console.print(f"{i}. [cyan]{page_file.name}[/cyan] + [green]{footnotes_file.name}[/green]")
    
    # 选择文件对
    file_choice = Prompt.ask("选择要处理的文件对编号", default="1")
    try:
        file_index = int(file_choice) - 1
        if not (0 <= file_index < len(file_pairs)):
            console.print("[red]无效的文件编号，使用第一个文件对[/red]")
            file_index = 0
    except ValueError:
        console.print("[red]无效的输入，使用第一个文件对[/red]")
        file_index = 0
    
    selected_files = file_pairs[file_index]
    page_file, footnotes_file = selected_files
    
    try:
        # 读取文件
        with console.status("[bold green]读取文件...[/bold green]"):
            with open(page_file, 'r', encoding='utf-8') as f:
                page_md = f.read()
            with open(footnotes_file, 'r', encoding='utf-8') as f:
                footnotes_md = f.read()
        
        # 解析页码块
        with console.status("[bold green]解析页码块...[/bold green]"):
            page_blocks1 = parse_page_blocks(page_md)
            page_blocks2 = parse_page_blocks(footnotes_md)
        
        # 合并块
        with console.status("[bold green]合并页码块...[/bold green]"):
            merged_blocks = merge_page_blocks(page_blocks1, page_blocks2)
        
        # 构建合并后的MD文件
        with console.status("[bold green]构建合并文件...[/bold green]"):
            merged_md = build_merged_md(merged_blocks)
        
        # 生成输出文件路径
        output_path = page_file.parent / f"{page_file.stem.replace('_page', '_merged')}.md"
        
        # 写入输出文件
        with console.status("[bold green]写入输出文件...[/bold green]"):
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(merged_md)
        
        console.print(f"\n[bold green]✓ 处理完成！[/bold green]")
        console.print(f"输出文件：[cyan]{output_path}[/cyan]")
        
    except Exception as e:
        console.print(f"\n[bold red]✗ 处理失败[/bold red]")
        console.print(f"[red]{str(e)}[/red]")
        import traceback
        console.print(traceback.format_exc())

if __name__ == '__main__':
    main() 