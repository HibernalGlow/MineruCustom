import json
import re
import argparse
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tqdm import tqdm
import logging
from datetime import datetime

# from nodes.record.logging_config import setup_logging
from .utils.common_utils import find_middle_json_files, save_markdown

# 获取logging实例
# config = {
#     'script_name': 'generate_footnote_md',
#     "console_enabled": False,
# }
# logging, config_info = setup_logging(config)

class TextProcessor:
    @staticmethod
    def extract_text_from_spans(spans):
        """从spans中提取文本内容"""
        text = ''
        for span in spans:
            if span['type'] == 'text':
                text += span['content']
            elif span['type'] == 'inline_equation':
                content = span['content']
                text += f'${content}$'
        return text

class FootnoteFilter:
    @staticmethod
    def should_exclude_footnote(text):
        """判断是否应该排除这个脚注"""
        # 去除首尾空白
        text = text.strip()
        
        # 排除纯数字（包括·包裹的数字）
        if text.isdigit() or text.replace('·', '').isdigit():
            return True
        
        # 排除特定关键词
        exclude_keywords = [
            '解密', '加微'
        ]
        
        for keyword in exclude_keywords:
            if keyword in text:
                return True
        
        # 排除特定格式
        patterns = [
            r'^·\d+·$',      # ·数字· 格式，如 ·418·
            r'^·\d+N·$',     # ·数字N· 格式，如 ·418N·
            r'^·\d+[A-Z]$',  # ·数字字母 格式，如 ·418N
            r'^·\d+$',       # ·数字 格式，如 ·418
        ]
        
        for pattern in patterns:
            if re.match(pattern, text):
                return True
        
        return False

class FootnoteProcessor:
    def __init__(self, json_data=None):
        self.json_data = json_data
        self.text_processor = TextProcessor()
        self.footnote_filter = FootnoteFilter()
        
        # 统计变量
        self.stats = {
            'total_footnotes': 0,
            'inserted_footnotes': 0,
            'excluded_footnotes': 0
        }
        
        # 存储处理结果的变量
        self.page_footnote_counts = {}  # 记录每页脚注数量
        self.footnotes = []
        self.page_info = []
    
    def process_footnote(self, args):
        """处理单个脚注任务"""
        page_idx, y_pos, lines = args
        results = []
        for line in lines:
            text = self.text_processor.extract_text_from_spans(line['spans'])
            # 只处理非空且不应该排除的脚注
            if text.strip() and not self.footnote_filter.should_exclude_footnote(text):
                results.append((text, y_pos))
        return page_idx, results
    
    def collect_footnotes(self):
        """收集脚注"""
        logging.info("\n收集脚注...")
        footnote_tasks = []
        self.page_footnote_counts = {}  # 重置计数器
        
        for page_idx, page in enumerate(self.json_data['pdf_info']):
            if 'page_size' in page:
                page_height = page['page_size'][1]
                bottom_threshold = page_height * 0.7
                
                # 初始化每页脚注计数
                self.page_footnote_counts[page_idx] = 0
                
                # 从discarded_blocks中收集脚注
                for block in page.get('discarded_blocks', []):
                    # 跳过lines为空的block
                    if len(block['lines']) == 0:
                        continue
                        
                    if block['bbox'][1] > bottom_threshold:
                        footnote_tasks.append((page_idx, block['bbox'][1], block['lines']))
        
        with ThreadPoolExecutor(max_workers=multiprocessing.cpu_count()) as executor:
            with tqdm(total=len(footnote_tasks), desc="脚注处理") as pbar:
                for page_idx, footnote_results in executor.map(self.process_footnote, footnote_tasks):
                    # 统计有效的线条总数（排除空lines的block）
                    valid_lines_count = sum(len(task[2]) for task in footnote_tasks if task[0] == page_idx)
                    self.stats['total_footnotes'] += valid_lines_count
                    self.stats['inserted_footnotes'] += len(footnote_results)
                    self.page_footnote_counts[page_idx] += len(footnote_results)
                    
                    for text, y_pos in footnote_results:
                        self.footnotes.append({
                            'text': text,
                            'position': f"{page_idx}_{y_pos}",
                            'page': page_idx
                        })
                        logging.info(f"找到脚注 [第{page_idx + 1}页]: {text}")
                    pbar.update(1)
        
        # 按页码和位置排序脚注
        logging.info("\n整理脚注...")
        self.footnotes.sort(key=lambda x: (x['page'], float(x['position'].split('_')[1])))
    
    def build_footnote_md(self):
        """构建脚注MD文件"""
        # 按页码分组脚注
        page_footnotes = {}
        for footnote in self.footnotes:
            page = footnote['page']
            if page not in page_footnotes:
                page_footnotes[page] = []
            page_footnotes[page].append(footnote)
        
        # 构建MD文本
        md_lines = []
        for page in sorted(page_footnotes.keys()):
            # 添加页码标记
            md_lines.append(f'```page\n第{page + 1}页\n```\n')
            
            # 添加该页的脚注
            for footnote in page_footnotes[page]:
                md_lines.append(f'```footnote\n{footnote["text"]}\n```\n')
            
            # 添加空行分隔
            md_lines.append('\n')
        
        return ''.join(md_lines)
    
    def process(self):
        """处理整个文档"""
        logging.info("开始处理脚注...")
        
        # 收集脚注
        self.collect_footnotes()
        
        # 构建脚注MD文件
        markdown_text = self.build_footnote_md()
        
        # 输出统计信息
        logging.info("\n脚注处理统计:")
        logging.info(f"总脚注数: {self.stats['total_footnotes']}")
        logging.info(f"有效脚注数: {self.stats['inserted_footnotes']}")
        logging.info(f"被排除脚注数: {self.stats['total_footnotes'] - self.stats['inserted_footnotes']}")
        
        logging.info("\n处理完成")
        
        return markdown_text


def main():
    import json
    from pathlib import Path
    from rich.console import Console
    from rich.prompt import Prompt
    
    console = Console()
    
    # 获取工作目录
    work_dir = Prompt.ask("请输入工作目录", default=".").strip().strip('"')
    if not work_dir:
        work_dir = "."
    
    # 查找匹配的文件
    with console.status("[bold green]查找匹配的文件...[/bold green]"):
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
    
    json_file = json_files[file_index]
    
    try:
        # 读取JSON文件
        with console.status("[bold green]读取JSON文件...[/bold green]"):
            with open(json_file, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
        
        # 创建处理器实例
        processor = FootnoteProcessor(json_data=json_data)
        
        # 处理脚注
        markdown_text = processor.process()
        
        # 生成输出文件路径
        output_path = json_file.parent / f"{json_file.stem.replace('_middle', '_footnotes')}.md"
        
        # 写入输出文件
        with console.status("[bold green]写入输出文件...[/bold green]"):
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(markdown_text)
        
        console.print(f"\n[bold green]✓ 处理完成！[/bold green]")
        console.print(f"输出文件：[cyan]{output_path}[/cyan]")
        
    except Exception as e:
        console.print(f"\n[bold red]✗ 处理失败[/bold red]")
        console.print(f"[red]{str(e)}[/red]")
        import traceback
        console.print(traceback.format_exc())

if __name__ == '__main__':
    main() 