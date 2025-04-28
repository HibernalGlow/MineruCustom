import re
import argparse
from pathlib import Path
import urllib.parse
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.markup import escape
from rich.prompt import Prompt, Confirm

console = Console()

def get_file_url_interactive():
    """Interactively asks for a base path and a relative path, then returns the file:/// URL."""
    console.print(Panel("[bold cyan]Path to file:/// URL Converter[/bold cyan]", border_style="blue"))

    while True:
        # Get base directory path
        while True:
            base_dir_str = Prompt.ask("请输入基础目录路径 (例如: D:\\folder\\images)").strip()
            if not base_dir_str:
                console.print("[red]基础目录路径不能为空。[/red]")
                continue
            base_dir = Path(base_dir_str)
            if base_dir.is_dir():
                console.print(f"[green]基础目录:[/green] [cyan]{escape(str(base_dir.resolve()))}[/cyan]")
                break
            else:
                console.print(f"[red]错误: 路径 '{escape(base_dir_str)}' 不是一个有效的目录。[/red]")

        # Get relative file path
        while True:
            relative_path_str = Prompt.ask("请输入相对于基础目录的文件路径 (例如: subfolder/image.jpg)").strip()
            if not relative_path_str:
                console.print("[red]文件路径不能为空。[/red]")
                continue
            # Basic check if it looks like a relative path (doesn't start with drive letter or / or \)
            # This is a simple check and might not cover all edge cases
            if Path(relative_path_str).is_absolute():
                 console.print("[yellow]警告: 输入的看起来像绝对路径，将尝试直接转换为 URL。[/yellow]")
                 absolute_image_path = Path(relative_path_str)
            else:
                # Combine base and relative path
                absolute_image_path = base_dir / relative_path_str

            # Check if the combined path exists (optional but good practice)
            if not absolute_image_path.exists():
                 confirm_continue = Confirm.ask(f"[yellow]警告: 文件 '{escape(str(absolute_image_path))}' 不存在。是否仍要生成 URL？[/yellow]", default=True)
                 if not confirm_continue:
                     continue # Ask for relative path again

            # Convert to file:/// URL
            try:
                # Resolve to handle '..' etc. and get the canonical absolute path
                resolved_path = absolute_image_path.resolve()
                file_url = resolved_path.as_uri()
                console.print(Panel(f"[bold green]生成的 URL:[/bold green]\n[link={file_url}]{escape(file_url)}[/link]",
                                    title="结果", border_style="green", expand=False))
                break # Path processed, break inner loop
            except Exception as e:
                console.print(f"[red]错误: 无法将路径 '{escape(str(absolute_image_path))}' 转换为 URL: {e}[/red]")
                # Stay in the inner loop to ask for relative path again

        # Ask to continue
        if not Confirm.ask("\n是否要转换另一个路径?", default=True):
            break

# --- Functions below are no longer used by the interactive mode ---

def convert_md_image_paths_to_file_urls(md_content: str, base_dir: Path) -> str:
    """
    (No longer used by interactive mode)
    Converts relative image paths in Markdown content to absolute file:/// URLs.
    """
    # ... (implementation remains the same but is not called in interactive mode) ...
    images_base_dir = base_dir

    def replace_image_path(match):
        alt_text = match.group(1)
        relative_path = match.group(2)
        clean_relative_path = relative_path.lstrip('./').lstrip('.\\')
        absolute_image_path = images_base_dir / clean_relative_path
        try:
            file_url = absolute_image_path.resolve().as_uri()
            return f'![{alt_text}]({file_url})'
        except Exception as e:
            console.print(f"[yellow]Warning: Could not resolve or convert path '{escape(str(absolute_image_path))}' to URL: {e}[/yellow]")
            return match.group(0)

    modified_md_content = re.sub(r'!\[(.*?)\]\(((?!https?://|file:///)[^)]+)\)', replace_image_path, md_content)
    return modified_md_content

def process_markdown_file(input_path: Path, output_path: Path, images_dir: Optional[Path] = None):
    """(No longer used by interactive mode) Reads a Markdown file, converts image paths, and saves to the output path."""
    # ... (implementation remains the same but is not called in interactive mode) ...
    if not input_path.is_file():
        console.print(f"[red]Error: Input file not found: {escape(str(input_path))}[/red]")
        return
    # ... rest of the function ...


if __name__ == "__main__":
    # Run the interactive URL generator
    try:
        get_file_url_interactive()
        console.print("\n[bold cyan]--- 转换器结束 ---[/bold cyan]")
    except KeyboardInterrupt:
        console.print("\n[yellow]操作已被用户中断[/yellow]")
    except Exception as e:
        console.print(f"[bold red]程序运行出错: {e}[/bold red]")
        import traceback
        console.print(traceback.format_exc())

    # --- Command-line argument parsing is removed for interactive mode ---
    # parser = argparse.ArgumentParser(...)
    # args = parser.parse_args()
    # ... (rest of the old __main__ block) ...