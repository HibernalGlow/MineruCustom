import argparse
from pathlib import Path
import urllib.parse # Keep for potential future use, though Path.as_uri() handles most cases
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.markup import escape
from rich.prompt import Prompt, Confirm

console = Console()

def simple_path_to_url_interactive():
    """Interactively asks for a file path and converts it to a file:/// URL."""
    console.print(Panel("[bold cyan]文件路径转 file:/// URL 工具[/bold cyan]", border_style="blue"))

    while True:
        # Get file path from user
        file_path_str = Prompt.ask("请输入文件或目录的完整路径").strip()
        if not file_path_str:
            console.print("[red]路径不能为空。[/red]")
            continue

        try:
            # Create a Path object
            file_path = Path(file_path_str)

            # Resolve the path to get the absolute path and handle '..' etc.
            # Use resolve(strict=False) to allow non-existent paths for URL generation
            resolved_path = file_path.resolve(strict=False)

            # Convert to file:/// URL
            file_url = resolved_path.as_uri()

            console.print(Panel(f"[bold green]生成的 URL:[/bold green]\n[link={file_url}]{escape(file_url)}[/link]",
                                title="结果", border_style="green", expand=False))

        except Exception as e:
            console.print(f"[red]错误: 无法将路径 '{escape(file_path_str)}' 转换为 URL: {e}[/red]")

        # Ask to continue
        if not Confirm.ask("\n是否要转换另一个路径?", default=True):
            break

# --- Removed unused functions: ---
# def convert_md_image_paths_to_file_urls(...)
# def process_markdown_file(...)
# def get_file_url_interactive(...) # Replaced by simpler version


if __name__ == "__main__":
    # Run the simplified interactive URL generator
    try:
        simple_path_to_url_interactive()
        console.print("\n[bold cyan]--- 转换器结束 ---[/bold cyan]")
    except KeyboardInterrupt:
        console.print("\n[yellow]操作已被用户中断[/yellow]")
    except Exception as e:
        console.print(f"[bold red]程序运行出错: {e}[/bold red]")
        import traceback
        console.print(traceback.format_exc())