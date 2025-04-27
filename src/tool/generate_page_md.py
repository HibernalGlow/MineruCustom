import json
import re
import argparse
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tqdm import tqdm
import logging
from datetime import datetime

from nodes.record.logger_config import setup_logger

# 获取logger实例
config = {
    'script_name': 'generate_page_md',
    "console_enabled": False,
}
logger, config_info = setup_logger(config)

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
    @staticmethod
    def find_insertion_point(official_md, target_text, window=100, similarity_threshold=0.6):
        """在官方MD中找到目标文本的位置"""
        # 预处理文本，去除空白字符
        target_text = ''.join(target_text.split())
        official_md_no_space = ''.join(official_md.split())
        
        if not target_text:
            return -1
        
        # 1. 首先尝试完全匹配（忽略空格）
        index = official_md_no_space.find(target_text)
        if index != -1:
            # 找到匹配位置后，需要将无空格索引转换回原始索引
            original_index = 0
            no_space_index = 0
            while no_space_index < index:
                if not official_md[original_index].isspace():
                    no_space_index += 1
                original_index += 1
            return original_index
        
        # 2. 尝试分段匹配
        segments = target_text.split('。')
        if len(segments) > 1:
            # 选择最长的非空段落
            longest_segment = max((s.strip() for s in segments if len(s.strip()) > 10), 
                                key=len, default='')
            if longest_segment:
                # 对最长段落也进行无空格匹配
                longest_segment = ''.join(longest_segment.split())
                index = official_md_no_space.find(longest_segment)
                if index != -1:
                    # 转换回原始索引
                    original_index = 0
                    no_space_index = 0
                    while no_space_index < index:
                        if not official_md[original_index].isspace():
                            no_space_index += 1
                        original_index += 1
                    return original_index
        
        # 3. 使用关键词匹配
        # 提取目标文本中的关键词（去除停用词和短词）
        words = [w for w in target_text.split() if len(w) > 2]
        if not words:
            return len(official_md)
        
        # 选择最长的几个词作为关键词
        keywords = sorted(words, key=len, reverse=True)[:3]
        
        # 找到所有关键词的位置
        positions = []
        for keyword in keywords:
            keyword = ''.join(keyword.split())  # 去除关键词中的空格
            pos = official_md_no_space.find(keyword)
            if pos != -1:
                # 转换回原始索引
                original_index = 0
                no_space_index = 0
                while no_space_index < pos:
                    if not official_md[original_index].isspace():
                        no_space_index += 1
                    original_index += 1
                positions.append(original_index)
        
        if positions:
            # 返回找到的第一个关键词位置
            return min(positions)
        
        return len(official_md)  # 如果都找不到，返回文档末尾


class PageProcessor:
    def __init__(self, json_data=None, official_md_path=None):
        self.json_data = json_data
        self.official_md_path = official_md_path
        self.text_processor = TextProcessor()
        self.official_md = ""
        self.page_info = []
        self.page_contexts = {}
    
    def preprocess_pages(self):
        """预处理页面信息"""
        logger.info("预处理页面信息...")
        total_pages = len(self.json_data['pdf_info'])
        
        # 初始化变量
        unmatched_pages = set()  # 存储未匹配的页面
        matched_points = {}      # 存储已匹配页面的插入点
        
        with tqdm(total=total_pages, desc="页面预处理") as pbar:
            for page_idx, page in enumerate(self.json_data['pdf_info']):
                if 'page_size' in page:
                    self.page_info.append({
                        'height': page['page_size'][1],
                        'para_blocks': page.get('para_blocks', []),
                        'discarded_blocks': page.get('discarded_blocks', [])
                    })
                    
                    # 找到每页最后一个文本块的位置
                    last_block = None
                    last_text = ''
                    max_y = -1  # 记录最大的y坐标
                    
                    # 遍历para_blocks找到最后一个块（包括文本块和表格块）
                    for block in page.get('para_blocks', []):
                        # 获取块的y坐标（底部）
                        block_bottom = block['bbox'][3]
                        
                        # 如果是文本块或表格块，且位置更靠下
                        if block['type'] in ['text', 'table_body', 'table_caption', 'table_footnote'] and block_bottom > max_y:
                            block_text = ''
                            # 根据块类型提取文本
                            if block['type'] == 'text':
                                block_text = '\n'.join(self.text_processor.extract_text_from_spans(line['spans']) for line in block['lines'])
                            elif block['type'].startswith('table'):
                                # 对于表格相关的块，也提取其中的文本
                                block_text = '\n'.join(
                                    self.text_processor.extract_text_from_spans(line['spans']) 
                                    for line in block['lines'] 
                                    if line.get('spans')
                                )
                            
                            if block_text.strip():
                                last_block = block
                                last_text = block_text
                                max_y = block_bottom
                                logger.info(f"更新第{page_idx + 1}页的最后块: 类型={block['type']}, y={max_y}")
                    
                    if last_block:
                        self.page_contexts[page_idx] = {
                            'text': last_text,
                            'bbox': last_block['bbox'],
                            'type': last_block['type']
                        }
                        logger.info(f"找到第{page_idx + 1}页的最后块: 类型={last_block['type']}, 文本={last_text[:50]}...")
                pbar.update(1)
        
        return total_pages, unmatched_pages, matched_points
    
    def process_pages(self, total_pages, unmatched_pages, matched_points):
        """处理页面插入点"""
        logger.info("\n查找页码标记插入点...")
        
        # 收集所有插入点
        insert_points = []  # [(position, mark_text), ...]
        processed_pages = set()  # 记录已处理的页码
        
        # 一页一页处理，确保连续性
        current_page = 0
        while current_page < total_pages:
            if current_page in self.page_contexts:
                context = self.page_contexts[current_page]
                # 获取当前页面的所有文本块，按y坐标从下到上排序
                page_blocks = []
                for block in self.page_info[current_page]['para_blocks']:
                    if block['type'] in ['text', 'table_body', 'table_caption', 'table_footnote']:
                        block_text = ''
                        if block['type'] == 'text':
                            block_text = '\n'.join(self.text_processor.extract_text_from_spans(line['spans']) for line in block['lines'])
                        elif block['type'].startswith('table'):
                            block_text = '\n'.join(
                                self.text_processor.extract_text_from_spans(line['spans']) 
                                for line in block['lines'] 
                                if line.get('spans')
                            )
                        if block_text.strip():
                            page_blocks.append((block_text, block['bbox'][3]))  # (文本, y坐标)
                
                # 按y坐标降序排序（从下到上）
                page_blocks.sort(key=lambda x: x[1], reverse=True)
                
                # 尝试匹配，从最后一个文本块开始
                insert_point = -1
                used_block = None
                
                # 首先尝试最后一个文本块
                if page_blocks:
                    block_text, _ = page_blocks[0]
                    insert_point = self.text_processor.find_insertion_point(self.official_md, block_text)
                    if insert_point != -1:
                        used_block = block_text
                        logger.info(f"在第{current_page + 1}页使用最后一个文本块匹配成功")
                    # 如果最后一个文本块匹配失败，尝试倒数第二个
                    elif len(page_blocks) > 1:
                        block_text, _ = page_blocks[1]
                        insert_point = self.text_processor.find_insertion_point(self.official_md, block_text)
                        if insert_point != -1:
                            used_block = block_text
                            logger.info(f"在第{current_page + 1}页使用倒数第二个文本块匹配成功")
                        else:
                            # 如果倒数第二个也失败，继续尝试其他块
                            for i, (block_text, _) in enumerate(page_blocks[2:], 3):
                                insert_point = self.text_processor.find_insertion_point(self.official_md, block_text)
                                if insert_point != -1:
                                    used_block = block_text
                                    logger.info(f"在第{current_page + 1}页使用第{i}个文本块匹配成功")
                                    break
                
                if insert_point != -1:
                    # 生成页码标记
                    page_mark = f'\n\n```page\n第{current_page + 1}页\n```\n\n'
                    insert_points.append((insert_point, page_mark))
                    processed_pages.add(current_page)
                    matched_points[current_page] = insert_point  # 记录匹配页面的插入点
                    logger.info(f"找到第{current_page + 1}页的插入点: {insert_point}, 使用文本: {used_block[:50]}...")
                else:
                    # 记录未匹配的页面
                    unmatched_pages.add(current_page)
                    logger.warning(f"无法找到第{current_page + 1}页的匹配位置")
            
            current_page += 1
        
        return insert_points, processed_pages, matched_points
    
    def process_unmatched_pages(self, unmatched_pages, matched_points, total_pages):
        """处理未匹配的页面"""
        insert_points = []
        
        if unmatched_pages:
            logger.info("\n处理未匹配页面...")
            unmatched_pages = sorted(unmatched_pages, reverse=True)  # 降序排序
            
            for page_idx in unmatched_pages:
                prev_page = None
                next_page = None
                
                # 向前查找最近的已匹配页面
                for i in range(page_idx - 1, -1, -1):
                    if i in matched_points:
                        prev_page = i
                        break
                
                # 向后查找最近的已匹配页面
                for i in range(page_idx + 1, total_pages):
                    if i in matched_points:
                        next_page = i
                        break
                
                # 根据前后页面决定插入位置
                if prev_page is not None and next_page is not None:
                    # 在两个页面之间插入
                    prev_point = matched_points[prev_page]
                    next_point = matched_points[next_page]
                    insert_point = prev_point + (next_point - prev_point) // 2
                    logger.info(f"将第{page_idx + 1}页插入到第{prev_page + 1}页和第{next_page + 1}页之间")
                elif prev_page is not None:
                    # 在前一页之后插入
                    insert_point = matched_points[prev_page] + 1
                    logger.info(f"将第{page_idx + 1}页插入到第{prev_page + 1}页之后")
                elif next_page is not None:
                    # 在后一页之前插入
                    insert_point = matched_points[next_page] - 1
                    logger.info(f"将第{page_idx + 1}页插入到第{next_page + 1}页之前")
                else:
                    # 找不到相邻页面，插入到文档末尾
                    insert_point = len(self.official_md)
                    logger.warning(f"找不到第{page_idx + 1}页的相邻页面，插入到文档末尾")
                
                # 生成页码标记
                page_mark = f'\n\n```page\n第{page_idx + 1}页\n```\n\n'
                insert_points.append((insert_point, page_mark))
                matched_points[page_idx] = insert_point  # 更新已匹配页面的位置
        
        return insert_points
    
    def build_final_text(self, all_insert_points):
        """构建最终文本"""
        # 按位置降序排序插入点，这样从后往前插入
        all_insert_points.sort(key=lambda x: x[0], reverse=True)
        
        # 构建最终文本
        final_text = self.official_md
        
        # 从后往前插入，这样不需要维护offset
        for pos, mark in all_insert_points:
            final_text = final_text[:pos] + mark + final_text[pos:]
        
        return final_text
    
    def process(self):
        """处理整个文档"""
        logger.info(f"开始处理文档: {self.official_md_path}")
        
        # 读取官方MD文件
        with open(self.official_md_path, 'r', encoding='utf-8') as f:
            self.official_md = f.read()
        
        # 1. 预处理页面信息
        total_pages, unmatched_pages, matched_points = self.preprocess_pages()
        
        # 2. 处理页面，找到插入点
        page_insert_points, processed_pages, matched_points = self.process_pages(total_pages, unmatched_pages, matched_points)
        
        # 3. 处理未匹配的页面
        unmatched_insert_points = self.process_unmatched_pages(unmatched_pages, matched_points, total_pages)
        
        # 4. 合并所有插入点并构建最终文本
        all_insert_points = page_insert_points + unmatched_insert_points
        final_text = self.build_final_text(all_insert_points)
        
        logger.info("\n处理完成")
        
        return final_text

def find_matching_files(directory='.'):
    """查找目录下的middle.json和对应的md文件"""
    directory = Path(directory)
    pairs = []
    
    # 查找所有middle.json文件
    for json_file in directory.glob('*middle.json'):
        # 找到对应的md文件（去掉_middle.json后缀）
        md_file = json_file.parent / f"{json_file.name.replace('_middle.json', '.md')}"
        if md_file.exists():
            pairs.append((json_file, md_file))
    
    return pairs

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
        file_pairs = find_matching_files(work_dir)
    
    if not file_pairs:
        console.print(f"\n[red]在目录 {work_dir} 中没有找到匹配的文件对[/red]")
        return
    
    console.print("\n[bold]找到以下文件对:[/bold]")
    for i, (json_file, md_file) in enumerate(file_pairs, 1):
        console.print(f"{i}. [cyan]{json_file.name}[/cyan] -> [green]{md_file.name}[/green]")
    
    # 选择文件对
    file_choice = Prompt.ask("选择要处理的文件对编号", default="1")
    try:
        file_index = int(file_choice) - 1
        if not (0 <= file_index < len(file_pairs)):
            console.print("[red]无效的文件编号，使用第一个文件对[/red]")
            file_index = 0
    except ValueError:
        console.print("[red]无效的输入，使用第一个文件对[/red]")
        file_index = 0
    
    selected_files = file_pairs[file_index]
    json_file, md_file = selected_files
    
    try:
        # 读取JSON文件
        with console.status("[bold green]读取JSON文件...[/bold green]"):
            with open(json_file, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
        
        # 创建处理器实例
        processor = PageProcessor(
            json_data=json_data,
            official_md_path=str(md_file)
        )
        
        # 处理文档
        markdown_text = processor.process()
        
        # 生成输出文件路径
        output_path = md_file.parent / f"{md_file.stem}_page{md_file.suffix}"
        
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