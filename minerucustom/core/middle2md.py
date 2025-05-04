import json
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt
from magic_pdf.dict2md.ocr_mkcontent import ocr_mk_mm_markdown_with_para_and_pagination # layout/middle.json转换为markdown关键函数
# 从 utils 导入共用函数
from minerucustom.utils.common_utils import find_middle_json_files, save_markdown

def main():
    console = Console()
    
    # 获取工作目录
    work_dir = Prompt.ask("请输入工作目录", default=".").strip().strip('"')
    if not work_dir:
        work_dir = "."
    
    # 查找匹配的文件
    with console.status("[bold green]查找middle.json文件...[/bold green]"):
        json_files = find_middle_json_files(work_dir) # 使用导入的函数
    
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
    
    json_file = json_files[file_index]
    
    try:
        # 读取JSON文件
        with console.status("[bold green]读取JSON文件...[/bold green]"):
            with open(json_file, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
        
        # 获取PDF信息
        pdf_info_dict = json_data['pdf_info']
        
        # --- 确定图片基础路径 ---
        # 图片位于 middle.json 文件所在目录下的 images 子目录中
        images_base_path_str = json_file.parent / "images"
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
        output_path = json_file.parent / f"{json_file.stem.replace('_middle', '')}.md"
        
        # 保存Markdown文件
        with console.status("[bold green]保存Markdown文件...[/bold green]"):
            save_markdown(markdown_content, output_path) # 使用导入的函数
        
        console.print(f"\n[bold green]✓ 处理完成！[/bold green]")
        console.print(f"输出文件：[cyan]{output_path}[/cyan]")
        
        # 显示统计信息
        total_pages = len(markdown_content)
        non_empty_pages = sum(1 for page in markdown_content if page['md_content'].strip())
        console.print(f"\n[bold]统计信息:[/bold]")
        console.print(f"- 总页数: {total_pages}")
        console.print(f"- 非空页数: {non_empty_pages}")
        
    except Exception as e:
        console.print(f"\n[bold red]✗ 处理失败[/bold red]")
        console.print(f"[red]{str(e)}[/red]")
        import traceback
        console.print(traceback.format_exc())

if __name__ == '__main__':
    main()