import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from rich.console import Console # 保持 Console 导入，以防未来需要日志记录

# 创建Rich控制台对象 (如果需要在此文件中打印)
# console = Console()

def find_middle_json_files(directory='.'):
    """查找目录下的JSON文件，按指定关键词优先级排序"""
    directory = Path(directory)
    json_files = []
    
    # 定义关键词优先级列表（可扩展）
    priority_keywords = ['middle', 'layout']
    
    # 查找所有JSON文件
    all_json_files = list(directory.glob('*.json'))
    
    # 按关键词优先级排序
    def get_priority(file_path):
        file_name = file_path.name.lower()
        for i, keyword in enumerate(priority_keywords):
            if keyword in file_name:
                return i
        return len(priority_keywords)  # 其他JSON文件放最后
    
    # 排序文件列表
    sorted_json_files = sorted(all_json_files, key=get_priority)
    
    return sorted_json_files

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

