import os
import re
import shutil
import json
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, TaskID
from rich.text import Text
from rich import print as rprint

# 初始化Rich控制台
console = Console()

def process_markdown(main_md_path, ocr_dir_path, recursive=True):
    """
    处理主markdown文件，替换图片引用为OCR内容，并合并图片文件夹
    
    Args:
        main_md_path: 主markdown文件的路径
        ocr_dir_path: 包含OCR内容的文件夹路径
        recursive: 是否递归查找OCR文件夹中的MD文件
    """
    # 将路径转换为Path对象
    main_md_path = Path(main_md_path)
    ocr_dir = Path(ocr_dir_path)
    
    # 检查文件和目录是否存在
    if not main_md_path.exists():
        console.print(f"[bold red]错误：无法找到文件[/] {main_md_path}")
        return False
    
    if not ocr_dir.exists() or not ocr_dir.is_dir():
        console.print(f"[bold red]错误：无法找到OCR文件夹[/] {ocr_dir}")
        return False
    
    # 获取主MD文件所在目录和文件名
    main_dir = main_md_path.parent
    main_md_name = main_md_path.stem
    
    # 找到主images文件夹
    main_images_dir = main_dir / "images"
    if not main_images_dir.exists():
        console.print(f"[bold red]错误：无法找到主images文件夹[/] {main_images_dir}")
        return False
    
    console.print(f"使用OCR文件夹：[cyan]{ocr_dir}[/]")
    
    # 查找OCR文件夹中的images文件夹（可能在子目录中）
    ocr_images_dir = None
    
    # 首先检查直接子文件夹
    potential_image_dir = ocr_dir / "images"
    if potential_image_dir.exists():
        ocr_images_dir = potential_image_dir
        console.print(f"找到OCR images文件夹：[green]{ocr_images_dir}[/]")
    else:
        # 递归查找images文件夹
        with console.status("[cyan]正在查找OCR images文件夹...[/]"):
            for root, dirs, files in os.walk(ocr_dir):
                for dir_name in dirs:
                    if dir_name.lower() == "images":
                        found_dir = Path(root) / dir_name
                        ocr_images_dir = found_dir
                        console.print(f"在子目录中找到OCR images文件夹：[green]{ocr_images_dir}[/]")
                        break
                if ocr_images_dir:
                    break
    
    if not ocr_images_dir:
        console.print(f"[yellow]警告：在OCR文件夹及其子目录中没有找到images文件夹[/]")
    
    # 创建图片名称到OCR内容的映射
    image_to_ocr = {}
    
    # 读取OCR文件夹中的MD文件
    md_files_count = 0
    
    # 根据recursive参数决定如何查找MD文件
    console.print(f"\n[bold cyan]{'递归' if recursive else '仅当前目录'}查找MD文件...[/]")
    
    with console.status("[cyan]正在搜索MD文件...[/]"):
        if recursive:
            # 递归查找所有MD文件
            md_files = []
            for root, dirs, files in os.walk(ocr_dir):
                for file in files:
                    if file.lower().endswith('.md'):
                        md_files.append(Path(root) / file)
        else:
            # 只查找直接子目录中的MD文件
            md_files = list(ocr_dir.glob("*.md"))
    
    # 处理找到的MD文件
    ocr_files_table = Table(title="OCR文件列表")
    ocr_files_table.add_column("序号", style="cyan")
    ocr_files_table.add_column("文件名", style="green")
    ocr_files_table.add_column("OCR内容预览", style="yellow")
    
    with console.status("[cyan]正在读取OCR内容...[/]"):
        for md_file in md_files:
            md_files_count += 1
            image_name = md_file.stem
            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    ocr_content = f.read().strip()
                image_to_ocr[image_name] = ocr_content
                # 添加到表格，显示内容预览(最多50个字符)
                preview = ocr_content[:50] + "..." if len(ocr_content) > 50 else ocr_content
                ocr_files_table.add_row(str(md_files_count), image_name, preview)
            except Exception as e:
                console.print(f"[red]警告：读取文件 {md_file} 时出错: {e}[/]")
    
    if md_files_count == 0:
        console.print(f"[bold yellow]警告：在OCR文件夹中没有找到任何MD文件[/]")
        
        # 额外检查：列出文件夹内容以帮助调试
        console.print("\n[bold]文件夹内容:[/]")
        dir_table = Table()
        dir_table.add_column("类型")
        dir_table.add_column("名称")
        dir_table.add_column("内容预览")
        
        for item in ocr_dir.iterdir():
            if item.is_file():
                dir_table.add_row("📄 文件", item.name, "")
            elif item.is_dir():
                # 列出子目录中的部分文件
                subfiles = list(item.glob("*"))[:5]  # 只显示5个
                subfiles_preview = ", ".join(f.name for f in subfiles) if subfiles else "空目录"
                dir_table.add_row("📁 目录", item.name, subfiles_preview)
        
        console.print(dir_table)
        
        # 提示用户是否继续
        continue_process = console.input("\n[yellow]未找到MD文件，是否仍要继续处理？[/]([green]y[/]/[red]n[/]): ").strip().lower()
        if continue_process != 'y':
            console.print("[yellow]已取消处理[/]")
            return False
    else:
        console.print(f"[green]从OCR文件夹加载了 {md_files_count} 个MD文件[/]")
        console.print(ocr_files_table)
    
    # 读取主MD文件内容
    with console.status("[cyan]正在读取主Markdown文件...[/]"):
        with open(main_md_path, 'r', encoding='utf-8') as f:
            main_content = f.read()
    
    # 使用正则表达式查找并替换图片引用
    # Markdown图片语法: ![alt](path)
    image_pattern = r'!\[(.*?)\]\((.*?/)?images/(.*?)\)'
    
    # 先找出所有匹配的图片
    all_matches = list(re.finditer(image_pattern, main_content))
    total_images = len(all_matches)
    
    if total_images == 0:
        console.print("[yellow]警告：在主Markdown文件中没有找到任何图片引用[/]")
        return False
    
    console.print(f"\n[bold]在主Markdown中找到 [cyan]{total_images}[/] 个图片引用[/]")
    
    # 创建替换结果表格
    replace_table = Table(title="图片替换结果")
    replace_table.add_column("序号", style="dim")
    replace_table.add_column("图片名称", style="cyan")
    replace_table.add_column("替换状态", style="bold")
    replace_table.add_column("OCR内容预览", style="yellow")
    
    # 计数器，用于记录替换的图片数量
    replaced_count = 0
    not_found_count = 0
    
    # 构建一个新的内容字符串和当前位置
    new_content = ""
    last_end = 0
    
    # 使用进度条显示替换进度
    with Progress() as progress:
        task = progress.add_task("[cyan]替换图片引用...", total=total_images)
        
        # 对每个匹配进行替换
        for i, match in enumerate(all_matches):
            # 更新进度条
            progress.update(task, advance=1)
            
            # 添加匹配前的文本
            new_content += main_content[last_end:match.start()]
            
            # 提取匹配信息
            alt_text = match.group(1)
            prefix = match.group(2) or ""
            image_file = match.group(3)
            image_name = Path(image_file).stem
            
            # 判断是否替换
            if image_name in image_to_ocr:
                ocr_content = image_to_ocr[image_name]
                new_content += ocr_content
                replaced_count += 1
                status = "[green]已替换[/]"
                preview = ocr_content[:50] + "..." if len(ocr_content) > 50 else ocr_content
            else:
                new_content += f"![{alt_text}]({prefix}images/{image_file})"
                not_found_count += 1
                status = "[red]未找到OCR[/]"
                preview = f"![{alt_text}]({prefix}images/{image_file})"
            
            # 添加到表格
            replace_table.add_row(str(i+1), image_name, status, preview)
            
            # 更新last_end
            last_end = match.end()
    
    # 添加剩余文本
    new_content += main_content[last_end:]
    
    # 显示替换结果摘要
    console.print(f"\n[bold]替换结果:[/] [green]{replaced_count}[/] 个成功，[red]{not_found_count}[/] 个失败")
    
    # 显示详细替换表格
    console.print(replace_table)
    
    # 保存修改后的主MD文件
    with console.status("[cyan]保存文件...[/]"):
        backup_path = main_md_path.with_suffix(f".backup{main_md_path.suffix}")
        shutil.copy2(main_md_path, backup_path)
        
    console.print(f"[green]已创建原文件备份：[/]{backup_path}")
    
    with open(main_md_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    console.print(f"[green]已更新主MD文件：[/]{main_md_path}")
    
    # 如果OCR文件夹中有images文件夹，则合并到主images文件夹
    if ocr_images_dir:
        console.print(f"\n[bold]合并图片文件...[/]")
        
        # 获取所有图片文件
        image_files = list(ocr_images_dir.glob("*"))
        
        if not image_files:
            console.print("[yellow]OCR images文件夹为空，无图片需要合并[/]")
        else:
            # 创建图片复制表格
            image_table = Table(title="图片合并结果")
            image_table.add_column("序号")
            image_table.add_column("图片名称", style="cyan")
            image_table.add_column("状态", style="bold")
            
            copied_count = 0
            skipped_count = 0
            
            with Progress() as progress:
                copy_task = progress.add_task("[cyan]复制图片...", total=len(image_files))
                
                for i, img_file in enumerate(image_files):
                    progress.update(copy_task, advance=1)
                    
                    dest_path = main_images_dir / img_file.name
                    if not dest_path.exists():
                        shutil.copy2(img_file, dest_path)
                        copied_count += 1
                        status = "[green]已复制[/]"
                    else:
                        skipped_count += 1
                        status = "[yellow]已跳过(存在)[/]"
                    
                    image_table.add_row(str(i+1), img_file.name, status)
            
            console.print(f"[green]复制了 {copied_count} 个图片[/]，[yellow]跳过了 {skipped_count} 个已存在的图片[/]")
            console.print(image_table)
    
    console.print(Panel("[bold green]处理完成！[/]", title="操作结果"))
    return True

def save_history(md_path, ocr_path):
    """保存输入历史到文件"""
    history_file = Path(__file__).parent / "image2mineru_history.json"
    history = {
        "md_path": md_path,
        "ocr_path": ocr_path,
        "timestamp": str(import_time())
    }
    
    try:
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        console.print("[green]已保存历史记录[/]")
    except Exception as e:
        console.print(f"[yellow]警告：保存历史记录失败: {e}[/]")

def load_history():
    """加载历史输入记录"""
    history_file = Path(__file__).parent / "image2mineru_history.json"
    if history_file.exists():
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            console.print(f"[yellow]警告：读取历史记录失败: {e}[/]")
    return None

def import_time():
    """获取当前时间，用于历史记录"""
    from datetime import datetime
    return datetime.now()

if __name__ == "__main__":
    # 显示欢迎标题
    console.print(Panel.fit(
        "[bold cyan]Markdown图片OCR内容替换工具[/]\n"
        "[dim]将Markdown文件中的图片引用替换为OCR文本内容[/]",
        border_style="green"
    ))
    
    # 加载历史记录
    history = load_history()
    
    # 主MD文件路径输入
    default_md = history.get("md_path", "") if history else ""
    if default_md:
        md_path = console.input(f"请输入主Markdown文件的路径 [dim][回车使用上次路径: {default_md}][/]: ").strip()
        if not md_path:
            md_path = default_md
            console.print(f"[dim]使用上次路径: {default_md}[/]")
    else:
        md_path = console.input("请输入主Markdown文件的路径: ").strip()
    
    # 处理输入路径（移除引号）
    md_path = md_path.strip('"\'')
    
    # OCR文件夹路径输入
    default_ocr = history.get("ocr_path", "") if history else ""
    if default_ocr:
        ocr_path = console.input(f"请输入包含OCR内容的文件夹路径 [dim][回车使用上次路径: {default_ocr}][/]: ").strip()
        if not ocr_path:
            ocr_path = default_ocr
            console.print(f"[dim]使用上次路径: {default_ocr}[/]")
    else:
        ocr_path = console.input("请输入包含OCR内容的文件夹路径: ").strip()
    
    # 处理输入路径（移除引号）
    ocr_path = ocr_path.strip('"\'')
    
    # 询问是否递归查找
    recursive_input = console.input("是否在OCR文件夹的子目录中递归查找MD文件？([green]y[/]/[red]n[/]) [dim][默认:y][/]: ").strip().lower()
    recursive = recursive_input != 'n'
    
    console.print("\n[bold]开始处理...[/]")
    
    # 处理Markdown文件
    success = process_markdown(md_path, ocr_path, recursive)
    
    # 如果处理成功，保存历史记录
    if success:
        save_history(md_path, ocr_path)