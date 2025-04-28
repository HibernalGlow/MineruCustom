import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from rich.console import Console # 保持 Console 导入，以防未来需要日志记录

# 创建Rich控制台对象 (如果需要在此文件中打印)
# console = Console()

def find_middle_json_files(directory='.'):
    """查找目录下的middle.json文件"""
    directory = Path(directory)
    json_files = []
    
    # 查找所有middle.json文件
    # 查找所有middle.json文件
    for json_file in directory.glob('*middle.json'):
        json_files.append(json_file)
    
    # 查找所有layout.json文件
    for json_file in directory.glob('*layout.json'):
        json_files.append(json_file)
    
    return json_files

def save_markdown(markdown_content, output_path):
    """保存Markdown内容到文件"""
    with open(output_path, 'w', encoding='utf-8') as f:
        for page in markdown_content:
            # 添加页码标记
            f.write(f'```page\n第{page["page_no"] + 1}页\n```\n\n')
            # 写入页面内容
            f.write(page['md_content'])
            # 添加分隔符
            f.write('\n\n' + '---' + '\n\n')

