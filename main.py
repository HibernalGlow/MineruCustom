import os
import json
import traceback
import copy
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.syntax import Syntax
from rich.markup import escape

# 导入其他模块的功能
from src.core.reprocess_discarded import reprocess_middle_interactive
from magic_pdf.dict2md.ocr_mkcontent import ocr_mk_mm_markdown_with_para_and_pagination
from src.utils.common_utils import find_middle_json_files, save_markdown

# 创建Rich控制台对象
console = Console()

def process_middle_json(middle_json_path):
    """处理middle.json文件并返回处理后的文件路径"""
    # 提示用户是否需要重处理
    process_needed = Confirm.ask(
        f"是否需要预处理 [cyan]{middle_json_path.name}[/cyan] 中的废弃块?",
        default=True
    )
    
    if not process_needed:
        return middle_json_path
    
    # 设置默认输出路径
    default_output_path = middle_json_path.with_name(f"{middle_json_path.stem}_processed.json")
    output_path_str = Prompt.ask(
        "请输入处理后的middle.json保存路径",
        default=str(default_output_path)
    )
    output_path = Path(output_path_str)
    
    # 获取底部阈值
    bottom_threshold_percent = Prompt.ask(
        "请输入要移动的页面底部内容的百分比",
        default="20"
    )
    try:
        bottom_threshold_percent = float(bottom_threshold_percent)
    except ValueError:
        console.print("[yellow]输入的不是有效数字，使用默认值 20%[/yellow]")
        bottom_threshold_percent = 20
    
    try:
        # 读取原始JSON文件
        with console.status("[bold green]正在读取原始middle.json...[/]", spinner="dots"):
            with open(middle_json_path, 'r', encoding='utf-8') as f:
                original_data = json.load(f)
        
        # 深拷贝数据
        modified_data = copy.deepcopy(original_data)
        
        # 检查PDF信息
        if 'pdf_info' not in modified_data:
            console.print("[red]错误: 未找到 'pdf_info' 字段[/red]")
            return middle_json_path
        
        pdf_info_list = modified_data['pdf_info']
        if not isinstance(pdf_info_list, list):
            console.print("[red]错误: 'pdf_info' 不是列表类型[/red]")
            return middle_json_path
        
        # 处理每一页的废弃块
        moved_blocks_count = 0
        fixed_pages_count = 0
        
        with console.status("[bold green]正在处理废弃块...[/]", spinner="dots"):
            for page_idx, page_data in enumerate(pdf_info_list):
                # 修复不完整的页面数据
                fixed = fix_incomplete_page_data(page_data, page_idx)
                if fixed:
                    fixed_pages_count += 1
                
                # 处理废弃块
                if 'discarded_blocks' in page_data and isinstance(page_data['discarded_blocks'], list) and \
                   'para_blocks' in page_data and isinstance(page_data['para_blocks'], list) and \
                   'page_size' in page_data and page_data['page_size']:
                    
                    page_height = page_data['page_size'][1]
                    threshold_y = page_height * (1 - bottom_threshold_percent / 100)
                    
                    blocks_to_move = []
                    for block in page_data['discarded_blocks']:
                        if 'bbox' in block and len(block['bbox']) == 4:
                            # 获取块的y坐标 (bbox格式通常为 [x0, y0, x1, y1])
                            y0 = block['bbox'][1]
                            if y0 >= threshold_y:
                                para_block = convert_to_para_block_format(block)
                                if para_block:
                                    blocks_to_move.append(block)
                                    page_data['para_blocks'].append(para_block)
                                    moved_blocks_count += 1
                    
                    # 从废弃块列表中移除已移动的块
                    for block in blocks_to_move:
                        page_data['discarded_blocks'].remove(block)
        
        # 保存处理后的文件
        with console.status("[bold green]正在保存处理后的middle.json...[/]", spinner="dots"):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(modified_data, f, ensure_ascii=False, indent=2)
        
        console.print(Panel.fit(
            f"[bold green]处理完成！[/]\n"
            f"- 移动了 [bold]{moved_blocks_count}[/] 个废弃块\n"
            f"- 修复了 [bold]{fixed_pages_count}[/] 个页面数据\n"
            f"- 文件已保存至: [cyan]{escape(str(output_path))}[/]",
            title="预处理结果",
            border_style="green"
        ))
        
        return output_path
    
    except Exception as e:
        console.print(f"[bold red]处理middle.json时出错: {e}[/]")
        console.print(Syntax(traceback.format_exc(), "python", theme="monokai", line_numbers=True))
        return middle_json_path  # 出错时返回原始文件路径

def convert_to_markdown(json_file_path):
    """将middle.json转换为Markdown"""
    try:
        # 读取JSON文件
        with console.status("[bold green]读取JSON文件...[/bold green]"):
            with open(json_file_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
        
        # 获取PDF信息
        pdf_info_dict = json_data['pdf_info']
        
        # 转换为Markdown
        images_base_path_str = json_file_path.parent / "images"
        images_base_path = Path(images_base_path_str)
        resolved_path = images_base_path.resolve(strict=False) # 处理相对路径
        # 将路径转换为 file:/// URL     
        images_base_url = resolved_path.as_uri()
        console.print(f"\n[bold green]图片基础路径:[/bold green] [cyan]{images_base_url}[/cyan]")
        # 转换为Markdown
        with console.status("[bold green]转换为Markdown...[/bold green]"):
            markdown_content = ocr_mk_mm_markdown_with_para_and_pagination(
                pdf_info_dict,
                img_buket_path=images_base_url # 使用 file:/// URL 作为基础路径
            )
        
        # 生成输出文件路径
        output_path = json_file_path.parent / f"{json_file_path.stem.replace('_middle', '').replace('_processed', '')}.md"
        
        # 保存Markdown文件
        with console.status("[bold green]保存Markdown文件...[/bold green]"):
            save_markdown(markdown_content, output_path)
        
        console.print(f"\n[bold green]✓ Markdown生成完成！[/bold green]")
        console.print(f"输出文件：[cyan]{output_path}[/cyan]")
        
        # 显示统计信息
        total_pages = len(markdown_content)
        non_empty_pages = sum(1 for page in markdown_content if page['md_content'].strip())
        console.print(f"\n[bold]统计信息:[/bold]")
        console.print(f"- 总页数: {total_pages}")
        console.print(f"- 非空页数: {non_empty_pages}")
        
        return output_path
    
    except Exception as e:
        console.print(f"\n[bold red]✗ Markdown生成失败[/bold red]")
        console.print(f"[red]{str(e)}[/red]")
        console.print(Syntax(traceback.format_exc(), "python", theme="monokai", line_numbers=True))
        return None

def fix_incomplete_page_data(page_data, page_idx):
    """
    检查并修复页面数据中缺失的必要字段
    
    Args:
        page_data: 页面数据字典
        page_idx: 页面索引
        
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
            page_data[field] = [] if field in ['preproc_blocks', 'layout_bboxes', 'images', 
                                             'tables', 'interline_equations', 
                                             'discarded_blocks', 'para_blocks'] else {}
            if field == 'page_idx':
                page_data[field] = page_idx
            elif field == 'page_size':
                page_data[field] = [612, 792]  # 默认A4
            fixed = True
    
    # 确保 page_size 有两个元素 [width, height]
    if 'page_size' in page_data and isinstance(page_data['page_size'], list):
        if len(page_data['page_size']) == 1:
            page_data['page_size'].append(792)  # 默认高度
            fixed = True
        elif len(page_data['page_size']) == 0:
            page_data['page_size'] = [612, 792]  # 默认A4
            fixed = True
            
    # 添加或确保其他可选字段
    if 'need_drop' not in page_data:
        page_data['need_drop'] = False
        fixed = True
    if 'drop_reason' not in page_data:
        page_data['drop_reason'] = []
        fixed = True
    
    return fixed

def convert_to_para_block_format(discarded_block):
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
            return None
            
        # 尝试从各种可能的字段提取文本内容
        text_content = ""
        for field in ['text', 'content', 'caption', 'description']:
            if field in discarded_block and discarded_block[field]:
                text_content = discarded_block[field]
                break
        
        # 如果没有找到文本，尝试从lines中提取
        if not text_content and 'lines' in discarded_block and isinstance(discarded_block['lines'], list):
            contents = []
            for line in discarded_block['lines']:
                if 'spans' in line and isinstance(line['spans'], list):
                    for span in line['spans']:
                        if 'content' in span:
                            contents.append(span['content'])
            if contents:
                text_content = ' '.join(contents)
        
        # 如果还是没有找到文本内容，使用默认文本
        if not text_content:
            text_content = "(原废弃块内容)"
        
        # 创建一个新的符合 para_blocks 格式要求的块
        new_block = {
            'type': 'text',
            'bbox': discarded_block['bbox'],
            'lines': [
                {
                    'bbox': discarded_block['bbox'],
                    'spans': [
                        {
                            'bbox': discarded_block['bbox'],
                            'type': 'text',
                            'content': text_content
                        }
                    ]
                }
            ]
        }
        
        return new_block
    except Exception as e:
        console.print(f"[yellow]转换块时发生错误: {e}[/yellow]")
        return None

def main():
    console.print(Panel.fit(
        "[bold cyan]Middle.json处理与Markdown转换工具[/bold cyan]", 
        border_style="blue"
    ))
    
    try:
        # 获取工作目录
        work_dir = Prompt.ask("请输入工作目录", default=".").strip().strip('"')
        if not work_dir:
            work_dir = "."
        
        # 查找middle.json文件
        with console.status("[bold green]查找middle.json文件...[/bold green]"):
            json_files = find_middle_json_files(work_dir)
        
        if not json_files:
            console.print(f"\n[red]在目录 {work_dir} 中没有找到middle.json文件[/red]")
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
        
        json_file_path = json_files[file_index]
        
        # 步骤1: 预处理middle.json
        console.print("\n[bold cyan]第一步: 预处理Middle.json文件[/bold cyan]")
        processed_json_path = process_middle_json(json_file_path)
        
        # 询问是否继续处理
        continue_processing = Confirm.ask("是否将处理后的middle.json转换为Markdown?", default=True)
        
        if continue_processing:
            # 步骤2: 转换为Markdown
            console.print("\n[bold cyan]第二步: 转换为Markdown[/bold cyan]")
            markdown_path = convert_to_markdown(processed_json_path)
            
            if markdown_path:
                # 显示处理完成信息
                console.print(Panel.fit(
                    f"[bold green]全部处理完成！[/]\n"
                    f"- 处理后的middle.json: [cyan]{escape(str(processed_json_path))}[/]\n"
                    f"- 生成的Markdown文件: [cyan]{escape(str(markdown_path))}[/]",
                    title="处理结果",
                    border_style="green"
                ))
                
                # 询问是否打开生成的Markdown文件
                if Confirm.ask("是否打开生成的Markdown文件?", default=True):
                    try:
                        os.startfile(markdown_path)
                    except Exception as e:
                        console.print(f"[yellow]无法打开文件: {e}[/yellow]")
        
        console.print("\n[bold cyan]--- 程序结束 ---[/bold cyan]")
        
    except KeyboardInterrupt:
        console.print("\n[yellow]操作已被用户中断[/yellow]")
    except Exception as e:
        console.print(f"[bold red]程序运行出错: {e}[/bold red]")
        console.print(Syntax(traceback.format_exc(), "python", theme="monokai", line_numbers=True))

if __name__ == "__main__":
    main()