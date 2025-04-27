import json
import argparse
import os
# Corrected import based on code structure
from magic_pdf.dict2md.ocr_mkcontent import union_make 
# Import necessary config constants
from magic_pdf.config.make_content_config import MakeMode, DropMode
# Import Prompt from rich
from rich.prompt import Prompt
from rich import print # Use rich print for styled output

def convert_json_to_md(json_path, md_path):
    """
    Reads a content_list.json file and converts it to a Markdown file using union_make.

    Args:
        json_path (str): Path to the input content_list.json file.
        md_path (str): Path to the output Markdown file.
    """
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            # union_make expects a list (pdf_info_dict)
            pdf_info_dict = json.load(f)
        
        # Ensure pdf_info_dict is a list
        if not isinstance(pdf_info_dict, list):
            # If the root is a dict with a key like 'pdf_info', extract the list
            if isinstance(pdf_info_dict, dict) and 'pdf_info' in pdf_info_dict and isinstance(pdf_info_dict['pdf_info'], list):
                pdf_info_dict = pdf_info_dict['pdf_info']
            else:
                raise ValueError("Invalid content_list.json format: Expected a list or a dict with a 'pdf_info' list.")

        # Call union_make with appropriate parameters
        # Assuming default modes. Adjust if needed.
        markdown_content = union_make(
            pdf_info_dict=pdf_info_dict,
            make_mode=MakeMode.MM_MD,  # Or MakeMode.NLP_MD, MakeMode.STANDARD_FORMAT
            drop_mode=DropMode.NONE,   # Or other DropMode options
            img_buket_path='' # Optional: Specify path/prefix for images if needed
        )

        os.makedirs(os.path.dirname(md_path), exist_ok=True)
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
            
        print(f"[bold green]成功:[/bold green] 已将 '{json_path}' 转换为 '{md_path}'")

    except FileNotFoundError:
        print(f"[bold red]错误:[/bold red] 输入文件未找到 '{json_path}'")
    except json.JSONDecodeError:
        print(f"[bold red]错误:[/bold red] 无法从 '{json_path}' 解码 JSON")
    except ValueError as ve:
         print(f"[bold red]错误:[/bold red] {ve}")
    except ImportError as ie:
        print(f"[bold red]错误:[/bold red] 导入必需模块失败。请确保 magic_pdf 已正确安装。详细信息: {ie}")
    except Exception as e:
        print(f"[bold red]发生意外错误:[/bold red] {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert content_list.json (or similar structure) to Markdown format.")
    # Remove the positional argument for json_file
    # parser.add_argument("json_file", help="Path to the input JSON file (e.g., content_list.json).")
    parser.add_argument("-o", "--output", help="Path to the output Markdown file. Defaults to replacing .json with .md in the input filename.")
    # Optional: Add arguments for make_mode, drop_mode, img_buket_path if needed
    
    args = parser.parse_args()

    # Prompt the user for the JSON file path
    json_input_path = Prompt.ask("请输入 JSON 文件路径")

    # Validate if the file exists
    while not os.path.exists(json_input_path):
        print(f"[bold red]错误:[/bold red] 文件 '{json_input_path}' 不存在。")
        json_input_path = Prompt.ask("请重新输入 JSON 文件路径")

    
    if args.output:
        md_output_path = args.output
    else:
        # Default output path: replace .json with .md
        base_name = os.path.splitext(json_input_path)[0]
        md_output_path = base_name + ".md"

    convert_json_to_md(json_input_path, md_output_path)
