import json
import re
from pathlib import Path
import copy # 用于深拷贝数据，避免修改原始输入数据
from typing import Dict, List, Any, Optional
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskID
from rich.table import Table
from rich.syntax import Syntax
from rich import print as rprint
from rich.markup import escape

# 创建Rich控制台对象
console = Console()

def reprocess_middle_interactive():
    """
    交互式地处理 middle.json 文件，将页面底部指定比例的 discarded_blocks
    移动到 para_blocks 的末尾，并保存为新的 middle.json 文件。
    """
    console.print(Panel.fit("[bold cyan]Middle.json Discarded Blocks 重处理工具[/bold cyan]", 
                          border_style="blue"))
    
    # --- 获取输入文件路径 ---
    while True:
        middle_json_path_str = Prompt.ask("请输入原始 middle.json 文件的完整路径", default="")
        if not middle_json_path_str:
            console.print("[red]输入不能为空，请重新输入。[/red]")
            continue
        middle_json_path = Path(middle_json_path_str)
        if middle_json_path.is_file():
            console.print(f"[green]找到文件: [/green][bold]{escape(str(middle_json_path))}[/bold]")
            break
        else:
            console.print(f"[red]错误: 文件 '{escape(middle_json_path_str)}' 不存在或不是一个文件。请重试。[/red]")

    # --- 获取输出文件路径 ---
    while True:
        output_middle_path_str = Prompt.ask("请输入要保存的新 middle.json 文件的完整路径", default=str(middle_json_path).replace(".json", "_processed.json"))
        if not output_middle_path_str:
            console.print("[red]输入不能为空，请重新输入。[/red]")
            continue
        output_middle_path = Path(output_middle_path_str)
        # 检查父目录是否存在，如果不存在则尝试创建
        try:
            output_middle_path.parent.mkdir(parents=True, exist_ok=True)
            if output_middle_path.parent.exists() and output_middle_path.parent.is_dir():
                if output_middle_path.name:
                    # 防止覆盖输入文件
                    if output_middle_path.resolve() == middle_json_path.resolve():
                         console.print("[red]错误: 输出文件不能与输入文件相同。请指定不同的输出路径。[/red]")
                         continue
                    break
                else:
                    console.print(f"[red]错误: 输出路径 '{escape(output_middle_path_str)}' 必须包含文件名。[/red]")
            else:
                 console.print(f"[red]错误: 无法创建或访问目录 '{escape(str(output_middle_path.parent))}'。请检查路径和权限。[/red]")
        except OSError as e:
             console.print(f"[red]错误: 无法创建或写入路径 '{escape(output_middle_path_str)}'。错误信息: {e}。请检查路径和权限。[/red]")
        except Exception as e:
            console.print(f"[red]发生未知路径错误: {e}。请检查路径。[/red]")

    # --- 询问是否处理 discarded_blocks ---
    process_discarded = Confirm.ask("是否处理并将页面底部的 discarded_blocks 移至 para_blocks?", default=True)

    # --- 如果处理，获取底部阈值 ---
    bottom_threshold_percent = 20 # 默认值
    if process_discarded:
        bottom_threshold_percent = Prompt.ask(
            "请输入要移动的页面底部内容的百分比", 
            default=str(bottom_threshold_percent),
            show_default=True
        )
        try:
            bottom_threshold_percent = float(bottom_threshold_percent)
            if not (0 < bottom_threshold_percent <= 100):
                console.print("[yellow]警告: 百分比超出范围，将使用默认值 20%[/yellow]")
                bottom_threshold_percent = 20
        except ValueError:
            console.print("[yellow]无效输入，将使用默认值 20%[/yellow]")
            bottom_threshold_percent = 20

    try:
        # --- 读取 middle.json ---
        with console.status("[bold green]正在读取 middle.json 文件...[/]", spinner="dots"):
            with open(middle_json_path, 'r', encoding='utf-8') as f:
                original_middle_data = json.load(f)

        # 深拷贝数据以进行修改
        modified_middle_data = copy.deepcopy(original_middle_data)

        # --- 检查 pdf_info ---
        if 'pdf_info' not in modified_middle_data:
            console.print(f"[bold red]错误:[/] '{escape(str(middle_json_path))}' 文件中缺少 'pdf_info' 键。请确保这是一个有效的 middle.json 文件。")
            return

        pdf_info_list = modified_middle_data['pdf_info']
        if not isinstance(pdf_info_list, list):
            console.print(f"[bold red]错误:[/] '{escape(str(middle_json_path))}' 文件中的 'pdf_info' 值不是一个列表。")
            return

        moved_blocks_count = 0
        fixed_pages_count = 0
        
        # --- 如果需要，处理 discarded_blocks ---
        if process_discarded:
            console.print(Panel(f"[bold cyan]开始处理 discarded_blocks[/] (移动底部 [yellow]{bottom_threshold_percent}%[/yellow] 区域)", border_style="blue"))
            threshold_ratio = 1.0 - (bottom_threshold_percent / 100.0)

            # 使用进度条显示处理过程
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TextColumn("[cyan]{task.completed}/{task.total} 页"),
                console=console
            ) as progress:
                task = progress.add_task("[green]处理页面...", total=len(pdf_info_list))
                
                for page_idx, page_data in enumerate(pdf_info_list):
                    progress.update(task, description=f"[green]处理第 {page_idx+1} 页...", advance=1)
                    
                    # 跳过空的页面数据
                    if not page_data:
                        continue
                        
                    # 检查并修复不完整的页面数据结构
                    if fix_incomplete_page_data(page_data, page_idx):
                        fixed_pages_count += 1
                        
                    page_size = page_data.get('page_size')
                    if not page_size or len(page_size) < 2:
                        progress.console.print(f"[yellow]警告: 第 {page_idx+1} 页缺少有效的 'page_size' 信息，无法处理 discarded_blocks。[/yellow]")
                        continue
                    page_height = page_size[1]
                    y_threshold = page_height * threshold_ratio # 计算阈值 Y 坐标

                    discarded_blocks = page_data.get('discarded_blocks')
                    para_blocks = page_data.get('para_blocks')

                    if not isinstance(discarded_blocks, list):
                        # 如果页面没有 discarded_blocks 或格式不正确，跳过该页面
                        continue
                    if not isinstance(para_blocks, list):
                        # 如果页面没有 para_blocks 列表，创建一个空列表
                        page_data['para_blocks'] = []
                        para_blocks = page_data['para_blocks']

                    blocks_to_move = []
                    remaining_discarded = []

                    for block in discarded_blocks:
                        bbox = block.get("bbox")
                        # 检查 bbox 是否存在且有效，并且块的顶部是否在阈值之下
                        if bbox and len(bbox) >= 4 and bbox[1] >= y_threshold:
                            # 记录将移动的块
                            content_preview = get_block_content_preview(block)
                            if content_preview:
                                progress.console.print(f"  [magenta]移动块[/magenta] [位置: {bbox}] [内容: {content_preview[:50]}...]")
                            
                            # 转换为 para_block 兼容格式
                            converted_block = convert_to_para_block_format(block)
                            if converted_block:
                                blocks_to_move.append(converted_block)
                                moved_blocks_count += 1
                            else:
                                remaining_discarded.append(block)
                        else:
                            remaining_discarded.append(block)

                    if blocks_to_move:
                        # 将筛选出的块追加到 para_blocks 末尾
                        para_blocks.extend(blocks_to_move)
                        # 更新 discarded_blocks 列表为剩余的块
                        page_data['discarded_blocks'] = remaining_discarded
                        progress.console.print(f"  [green]✓ 第 {page_idx+1} 页移动了 {len(blocks_to_move)} 个 discarded_blocks 到 para_blocks。[/green]")

            # 显示处理结果统计
            stats_table = Table(title="处理结果统计", show_header=True, header_style="bold cyan")
            stats_table.add_column("项目", style="dim")
            stats_table.add_column("数量")
            stats_table.add_row("修复的页数据结构", f"[green]{fixed_pages_count}[/green]")
            stats_table.add_row("移动的 discarded_blocks", f"[green]{moved_blocks_count}[/green]")
            console.print(stats_table)
        else:
            console.print("[yellow]未选择处理 discarded_blocks，将直接保存原始 middle.json 结构。[/yellow]")

        # --- 写入新的 middle.json ---
        with console.status("[bold green]正在写入新的 middle.json 文件...[/]", spinner="dots"):
            with open(output_middle_path, 'w', encoding='utf-8') as f:
                json.dump(modified_middle_data, f, ensure_ascii=False, indent=4)

        console.print(Panel.fit(f"[bold green]处理成功！[/bold green]\n新文件已保存至: [cyan]{escape(str(output_middle_path.resolve()))}[/cyan]", 
                               border_style="green", title="完成"))

    except json.JSONDecodeError:
        console.print(f"[bold red]错误:[/] '{escape(str(middle_json_path))}' 不是有效的 JSON 文件。请检查文件内容。")
    except FileNotFoundError:
        console.print(f"[bold red]错误:[/] 文件 '{escape(str(middle_json_path))}' 未找到。")
    except Exception as e:
        console.print(f"[bold red]处理过程中发生错误:[/] {e}")
        import traceback
        console.print(Syntax(traceback.format_exc(), "python", theme="monokai", line_numbers=True))

def get_block_content_preview(block: Dict[str, Any]) -> str:
    """
    从块中提取文本内容的预览
    
    Args:
        block: 块数据
        
    Returns:
        str: 内容预览，如果没有找到内容则返回空字符串
    """
    # 尝试从不同位置提取内容
    if 'lines' in block and isinstance(block['lines'], list):
        contents = []
        for line in block['lines']:
            if 'spans' in line and isinstance(line['spans'], list):
                for span in line['spans']:
                    if 'content' in span and span['content']:
                        contents.append(span['content'])
        if contents:
            return " ".join(contents)
    
    # 尝试其他可能的字段
    for field in ['text', 'content', 'caption', 'description']:
        if field in block and block[field]:
            return block[field]
    
    return ""

def fix_incomplete_page_data(page_data: Dict[str, Any], page_idx: int) -> bool:
    """
    检查并修复页面数据中缺失的必要字段
    
    Args:
        page_data: 页面数据字典
        page_idx: 页面索引，用于日志记录
        
    Returns:
        bool: 如果修复了任何字段，返回 True，否则返回 False
    """
    fixed = False
    
    # 确保必需字段存在
    required_fields = [
        'preproc_blocks', 'layout_bboxes', 'page_idx', 'page_size', '_layout_tree',
        'images', 'tables', 'interline_equations', 'discarded_blocks', 'para_blocks'
    ]
    
    for field in required_fields:
        if field not in page_data:
            if field in ['preproc_blocks', 'layout_bboxes', 'images', 'tables', 
                         'interline_equations', 'discarded_blocks', 'para_blocks']:
                page_data[field] = []
            elif field == '_layout_tree':
                page_data[field] = []
            elif field == 'page_idx':
                page_data[field] = page_idx
            elif field == 'page_size' and 'page_size' not in page_data:
                # 如果没有 page_size，设置默认值 [1000.0, 1000.0]
                page_data[field] = [1000.0, 1000.0]
            fixed = True
    
    # 确保 page_size 有两个元素 [width, height]
    if 'page_size' in page_data and isinstance(page_data['page_size'], list):
        if len(page_data['page_size']) == 1:
            # 只有宽度，添加默认高度
            page_data['page_size'].append(1400.0)
            fixed = True
        elif len(page_data['page_size']) == 0:
            # 空列表，设置默认值
            page_data['page_size'] = [1000.0, 1400.0]
            fixed = True
            
    # 添加或确保其他可选字段
    if 'need_drop' not in page_data:
        page_data['need_drop'] = False
        fixed = True
    if 'drop_reason' not in page_data:
        page_data['drop_reason'] = []
        fixed = True
    
    return fixed

def convert_to_para_block_format(discarded_block: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    将 discarded_block 转换为 para_blocks 兼容的格式
    
    Args:
        discarded_block: 从 discarded_blocks 中获取的块
        
    Returns:
        转换后的块，如果无法转换则返回 None
    """
    try:
        # 检查 discarded_block 是否有必要的属性
        if 'bbox' not in discarded_block:
            print(f"警告: discarded_block 缺少 bbox 属性，无法转换")
            return None
            
        # 如果 discarded_block 已经有 lines 和 type，确保它们符合要求
        if 'lines' in discarded_block:
            converted_block = discarded_block.copy()
            
            # 强制将类型设为 text
            converted_block['type'] = 'text'
                
            # 确保每个 line 中的每个 span 有 type 和 content 属性
            for line in converted_block.get('lines', []):
                if 'spans' not in line or not isinstance(line['spans'], list):
                    line['spans'] = []
                    
                for span in line.get('spans', []):
                    if 'type' not in span:
                        if 'content' in span:
                            span['type'] = 'text'
                        else:
                            span['type'] = 'text'
                            span['content'] = ''
                    elif span['type'] not in ['text', 'inline_equation', 'interline_equation', 'image', 'table']:
                        # 确保 span['type'] 是有效的 ContentType 值
                        span['type'] = 'text'
            
            return converted_block
            
        # 如果 discarded_block 没有 lines 属性，需要创建完整的结构
        text_content = ""
        
        # 尝试从各种可能的字段提取文本内容
        for field in ['text', 'content', 'caption', 'description']:
            if field in discarded_block and discarded_block[field]:
                text_content = discarded_block[field]
                break
        
        # 创建一个新的符合 para_blocks 格式要求的块
        new_block = {
            'type': 'text',  # 默认类型为 text (BlockType.Text)
            'bbox': discarded_block['bbox'],
            'lines': [
                {
                    'bbox': discarded_block['bbox'],  # 使用同样的 bbox
                    'spans': [
                        {
                            'bbox': discarded_block['bbox'],  # 使用同样的 bbox
                            'type': 'text',  # ContentType.Text
                            'content': text_content
                        }
                    ]
                }
            ]
        }
        
        return new_block
    except Exception as e:
        print(f"转换块时发生错误: {e}")
        return None

if __name__ == "__main__":
    try:
        console.print("[bold cyan]--- Middle.json Discarded Blocks Reprocessing Tool ---[/bold cyan]")
        reprocess_middle_interactive()
        console.print("\n[bold cyan]--- 处理结束 ---[/bold cyan]")
    except KeyboardInterrupt:
        console.print("\n[yellow]操作已被用户中断[/yellow]")
    except Exception as e:
        console.print(f"[bold red]程序运行出错: {e}[/bold red]")
        import traceback
        console.print(Syntax(traceback.format_exc(), "python", theme="monokai", line_numbers=True))