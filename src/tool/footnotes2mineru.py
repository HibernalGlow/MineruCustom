import json
import re
import argparse
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tqdm import tqdm
from rapidfuzz import fuzz, process
from difflib import SequenceMatcher
import logging
from datetime import datetime

from nodes.record.logger_config import setup_logger

# 获取logger实例
config = {
    'script_name': 'mineru_footnotes',
    "console_enabled": False,
}
logger, config_info = setup_logger(config)

# ================= 文本处理模块 =================

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


# ================= 脚注过滤模块 =================

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


# ================= Markdown格式转换模块 =================

class MarkdownConverter:
    @staticmethod
    def merge_continuous_blocks(markdown_text):
        """合并连续的脚注代码块"""
        # 分割成行
        lines = markdown_text.split('\n')
        result_lines = []
        current_block = []
        in_block = False
        block_type = None  # 用于区分footnote和page块
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # 检测代码块开始
            if line.strip() in ['```footnote', '```page']:
                block_type = 'footnote' if line.strip() == '```footnote' else 'page'
                if not in_block:
                    # 新代码块开始
                    in_block = True
                    current_block = [line]
                else:
                    # 连续的代码块，跳过开始标记
                    pass
            # 检测代码块结束
            elif line.strip() == '```':
                if in_block:
                    if block_type == 'footnote':
                        # 检查后面是否有连续的脚注块（允许中间有4行以内的空行）
                        next_block_start = -1
                        empty_lines = 0
                        j = i + 1
                        while j < min(i + 6, len(lines)):  # 最多往后看5行（4行空行+1行代码块开始）
                            if lines[j].strip() == '```footnote':
                                next_block_start = j
                                break
                            elif not lines[j].strip():
                                empty_lines += 1
                            elif lines[j].strip() == '```page':  # 如果遇到page块，不合并
                                break
                            else:
                                break
                            j += 1
                        
                        if next_block_start != -1 and empty_lines <= 4:
                            # 跳过结束标记和空行，继续收集下一个块的内容
                            i = next_block_start
                        else:
                            # 添加结束标记并结束当前块
                            current_block.append(line)
                            result_lines.extend(current_block)
                            current_block = []
                            in_block = False
                    else:
                        # page块直接结束
                        current_block.append(line)
                        result_lines.extend(current_block)
                        current_block = []
                        in_block = False
                else:
                    result_lines.append(line)
            else:
                if in_block:
                    if line.strip():  # 只添加非空行
                        current_block.append(line)
                else:
                    result_lines.append(line)
            i += 1
        
        # 如果还有未处理的块
        if current_block:
            result_lines.extend(current_block)
        
        return '\n'.join(result_lines)
    
    @staticmethod
    def convert_to_quote_format(markdown_text):
        """将脚注代码块转换为引述格式，保持page块不变"""
        lines = markdown_text.split('\n')
        result_lines = []
        in_block = False
        block_type = None
        last_was_footnote = False
        
        for i, line in enumerate(lines):
            if line.strip() in ['```footnote', '```page']:
                block_type = 'footnote' if line.strip() == '```footnote' else 'page'
                in_block = True
                if block_type == 'footnote':
                    # 如果上一个是脚注块，确保有两个空行分隔
                    if last_was_footnote and result_lines and result_lines[-1].strip():
                        result_lines.extend([''])
                    result_lines.append('> ---')
                    result_lines.append('>')
                else:
                    result_lines.append(line)
            elif line.strip() == '```' and in_block:
                if block_type == 'page':
                    result_lines.append(line)
                else:
                    # 脚注块结束后添加两个空行
                    result_lines.extend([''])
                in_block = False
                last_was_footnote = (block_type == 'footnote')
                block_type = None
            elif in_block:
                if line.strip():
                    if block_type == 'footnote':
                        result_lines.append('> * ' + line.strip())
                    else:
                        result_lines.append(line)
            else:
                result_lines.append(line)
        
        # 移除末尾多余的空行
        while result_lines and not result_lines[-1].strip():
            result_lines.pop()
        
        return '\n'.join(result_lines)


# ================= 脚注处理核心模块 =================

class FootnoteProcessor:
    def __init__(self, json_data=None, official_md_path=None, similarity_threshold=0.6, 
                 add_page_marks=False, insert_by_page=True):
        self.json_data = json_data
        self.official_md_path = official_md_path
        self.similarity_threshold = similarity_threshold
        self.add_page_marks = add_page_marks
        self.insert_by_page = insert_by_page
        self.text_processor = TextProcessor()
        self.footnote_filter = FootnoteFilter()
        self.markdown_converter = MarkdownConverter()
        
        # 统计变量
        self.stats = {
            'total_footnotes': 0,
            'inserted_footnotes': 0,
            'excluded_footnotes': 0,
            'matched_footnotes': 0,
            'unmatched_footnotes': 0
        }
        
        # 存储处理结果的变量
        self.page_footnote_counts = {}  # 记录每页脚注数量
        self.official_md = ""
        self.footnotes = []
        self.page_info = []
        self.page_contexts = {}
    
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
    # 在FootnoteProcessor类中添加一个新方法来收集详细的脚注信息
# 增强FootnoteProcessor的collect_footnote_details方法
    def collect_footnote_details(self):
        """收集所有脚注的详细信息，用于显示"""
        details = []
        
        for i, footnote in enumerate(self.footnotes):
            # 提取页码和位置信息
            page_num = footnote['page'] + 1
            position = footnote['position'].split('_')[1]
            
            # 为每个脚注添加状态标记
            status = "待处理"
            
            # 收集上下文信息（截取适当长度）
            context = footnote['context']
            context_preview = context[:100] + "..." if len(context) > 100 else context
            
            details.append({
                'id': i + 1,
                'text': footnote['text'],
                'page': page_num,
                'position': position,
                'context': context_preview,
                'status': status,
                'match_position': None
            })
        
        return details    
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
    
    def collect_footnotes(self):
        """收集脚注"""

        logger.info("\n收集脚注...")
        footnote_tasks = []
        self.page_footnote_counts = {}  # 重置计数器
        
        for page_idx, page in enumerate(self.page_info):
            page_height = page['height']
            bottom_threshold = page_height * 0.7
            
            # 初始化每页脚注计数
            self.page_footnote_counts[page_idx] = 0
            
            # 从discarded_blocks中收集脚注
            for block in page['discarded_blocks']:
                # 跳过lines为空的block
                if len(block['lines']) == 0:
                    continue
                    
                if block['bbox'][1] > bottom_threshold:
                    footnote_tasks.append((page_idx, block['bbox'][1], block['lines']))
        
        context_map = {}  # 上下文映射
        
        with ThreadPoolExecutor(max_workers=multiprocessing.cpu_count()) as executor:
            with tqdm(total=len(footnote_tasks), desc="脚注处理") as pbar:
                for page_idx, footnote_results in executor.map(self.process_footnote, footnote_tasks):
                    # 统计有效的线条总数（排除空lines的block）
                    valid_lines_count = sum(len(task[2]) for task in footnote_tasks if task[0] == page_idx)
                    self.stats['total_footnotes'] += valid_lines_count
                    self.stats['inserted_footnotes'] += len(footnote_results)
                    self.page_footnote_counts[page_idx] += len(footnote_results)
                    
                    # 预先获取当前页面的上下文
                    current_page_contexts = {
                        pos: ctx for pos, ctx in context_map.items()
                        if ctx['page'] == page_idx
                    }
                    
                    for text, y_pos in footnote_results:
                        # 找到最近的上下文
                        closest_context = None
                        min_distance = float('inf')
                        
                        # 遍历当前页的所有文本块
                        for block in self.page_info[page_idx]['para_blocks']:
                            if block['type'] == 'text':
                                block_y = block['bbox'][3]
                                # 只考虑在脚注上方的文本块
                                if block_y < y_pos:
                                    distance = y_pos - block_y
                                    if distance < min_distance:
                                        min_distance = distance
                                        closest_context = '\n'.join(
                                            self.text_processor.extract_text_from_spans(line['spans'])
                                            for line in block['lines']
                                        )
                        
                        self.footnotes.append({
                            'text': text,
                            'position': f"{page_idx}_{y_pos}",
                            'context': closest_context if closest_context else '',
                            'page': page_idx
                        })
                        logger.info(f"找到脚注 [第{page_idx + 1}页]: {text}")
                        if closest_context:
                            logger.info(f"上下文: {closest_context[:100]}...")
                        else:
                            logger.warning(f"未找到上下文 [第{page_idx + 1}页]")
                    pbar.update(1)
        
        # 按页码和位置排序脚注
        logger.info("\n整理脚注...")
        self.footnotes.sort(key=lambda x: (x['page'], float(x['position'].split('_')[1])))
    
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
                    
                    # 如果是按页码插入，先收集该页的脚注
                    if self.insert_by_page:
                        page_footnotes = [f for f in self.footnotes if f['page'] == current_page]
                        footnote_marks = []
                        
                        # 添加详细输出
                        logger.info(f"\n--- 正在处理第{current_page + 1}页脚注 ---")
                        logger.info(f"该页共有 {self.page_footnote_counts[current_page]} 个脚注")
                        
                        # 添加统计信息
                        inserted_count = 0
                        
                        for footnote in page_footnotes:
                            footnote_marks.append(f'\n```footnote\n{footnote["text"]}\n```\n')
                            self.stats['matched_footnotes'] += 1
                            inserted_count += 1
                            logger.info(f"[{inserted_count}/{self.page_footnote_counts[current_page]}] 插入脚注: " + 
                                       (f"{footnote['text'][:50]}..." if len(footnote['text']) > 50 else f"{footnote['text']}"))
                        
                        # 添加详细日志
                        if inserted_count > 0:
                            success_rate = inserted_count / self.page_footnote_counts[current_page] * 100 if self.page_footnote_counts[current_page] > 0 else 0
                            logger.info(f"第{current_page + 1}页脚注处理完成: 成功插入 {inserted_count}/{self.page_footnote_counts[current_page]} 个脚注 (成功率: {success_rate:.1f}%)")
                        else:
                            logger.warning(f"第{current_page + 1}页未插入任何脚注")
                        
                        # 将脚注和页码标记组合
                        mark_text = ''.join(footnote_marks) + page_mark
                    else:
                        mark_text = page_mark
                    
                    insert_points.append((insert_point, mark_text))
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
                if self.insert_by_page:
                    page_footnotes = [f for f in self.footnotes if f['page'] == page_idx]
                    footnote_marks = []
                    
                    # 添加详细输出
                    logger.info(f"\n--- 处理未匹配页面: 第{page_idx + 1}页脚注 ---")
                    logger.info(f"该页共有 {self.page_footnote_counts[page_idx]} 个脚注")
                    
                    # 添加统计信息
                    inserted_count = 0
                    
                    for footnote in page_footnotes:
                        footnote_marks.append(f'\n```footnote\n{footnote["text"]}\n```\n')
                        self.stats['matched_footnotes'] += 1
                        inserted_count += 1
                        logger.info(f"[{inserted_count}/{self.page_footnote_counts[page_idx]}] 插入脚注: " + 
                                   (f"{footnote['text'][:50]}..." if len(footnote['text']) > 50 else f"{footnote['text']}"))
                    
                    # 添加详细日志
                    if inserted_count > 0:
                        success_rate = inserted_count / self.page_footnote_counts[page_idx] * 100 if self.page_footnote_counts[page_idx] > 0 else 0
                        logger.info(f"未匹配页面(第{page_idx + 1}页)处理完成: 成功插入 {inserted_count}/{self.page_footnote_counts[page_idx]} 个脚注 (成功率: {success_rate:.1f}%)")
                    else:
                        logger.warning(f"未匹配页面(第{page_idx + 1}页)未插入任何脚注")
                    
                    mark_text = ''.join(footnote_marks) + page_mark
                else:
                    mark_text = page_mark
                
                insert_points.append((insert_point, mark_text))
                matched_points[page_idx] = insert_point  # 更新已匹配页面的位置
        
        return insert_points
    
    def process_keyword_footnotes(self, matched_points):
        """按关键词匹配处理脚注"""
        insert_points = []
        
        if not self.insert_by_page:
            logger.info("\n按关键词匹配插入脚注...")
            processed_footnotes = set()  # 初始化已处理脚注集合
            
            with tqdm(total=len(self.footnotes), desc="插入脚注") as pbar:
                for footnote in self.footnotes:
                    if not footnote['context']:
                        pbar.update(1)
                        continue
                    
                    footnote_id = f"{footnote['text']}_{footnote['page']}"
                    if footnote_id in processed_footnotes:
                        logger.info(f"跳过重复脚注 [第{footnote['page'] + 1}页]: {footnote['text']}")
                        pbar.update(1)
                        continue
                    
                    insert_point = self.text_processor.find_insertion_point(
                        self.official_md,
                        footnote['context'],
                        similarity_threshold=self.similarity_threshold
                    )
                    
                    if insert_point != -1:
                        # 生成脚注标记
                        footnote_mark = f'\n```footnote\n{footnote["text"]}\n```\n'
                        insert_points.append((insert_point, footnote_mark))
                        processed_footnotes.add(footnote_id)
                        self.stats['matched_footnotes'] += 1
                        # 添加详细日志输出
                        logger.info(f"[第{footnote['page']+1}页] 成功匹配脚注: " + 
                                   (f"{footnote['text'][:50]}..." if len(footnote['text']) > 50 else f"{footnote['text']}"))
                    else:
                        logger.warning(f"未找到匹配位置 [第{footnote['page'] + 1}页]: {footnote['text']}")
                        self.stats['unmatched_footnotes'] += 1
                        # 将未匹配的脚注插入到对应页码标记前
                        page_points = [(p, m) for p, m in insert_points if f'第{footnote["page"] + 1}页' in m]
                        page_point = page_points[0][0] if page_points else None
                        if page_point is not None:
                            footnote_mark = f'\n```footnote\n{footnote["text"]}\n```\n'
                            insert_points.append((page_point, footnote_mark))
                            logger.info(f"将未匹配脚注插入到第{footnote['page'] + 1}页页码标记前")
                    
                    pbar.update(1)
        
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
        
        # 如果不需要页码标记，移除它们
        if not self.add_page_marks:
            logger.info("\n移除页码标记...")
            lines = final_text.split('\n')
            filtered_lines = []
            skip_block = False
            
            for line in lines:
                if line.strip() == '```page':
                    skip_block = True
                    continue
                elif skip_block and line.strip() == '```':
                    skip_block = False
                    continue
                elif not skip_block:
                    filtered_lines.append(line)
            
            final_text = '\n'.join(filtered_lines)
        
        # 合并连续的脚注代码块
        final_text = self.markdown_converter.merge_continuous_blocks(final_text)
        
        # 转换为引述格式
        final_text = self.markdown_converter.convert_to_quote_format(final_text)
        
        return final_text
    
    def process(self):
        """处理整个文档"""
        logger.info(f"开始处理文档: {self.official_md_path}")
        logger.info(f"相似度阈值: {self.similarity_threshold}")
        
        # 读取官方MD文件
        with open(self.official_md_path, 'r', encoding='utf-8') as f:
            self.official_md = f.read()
        
        # 1. 预处理页面信息
        total_pages, unmatched_pages, matched_points = self.preprocess_pages()
        
        # 2. 收集脚注
        self.collect_footnotes()
        
        # 3. 处理页面，找到插入点
        page_insert_points, processed_pages, matched_points = self.process_pages(total_pages, unmatched_pages, matched_points)
        
        # 4. 处理未匹配的页面
        unmatched_insert_points = self.process_unmatched_pages(unmatched_pages, matched_points, total_pages)
        
        # 5. 如果是按关键词匹配，处理脚注
        keyword_insert_points = self.process_keyword_footnotes(matched_points)
        
        # 6. 合并所有插入点并构建最终文本
        all_insert_points = page_insert_points + unmatched_insert_points + keyword_insert_points
        final_text = self.build_final_text(all_insert_points)
        
        # 输出统计信息
        logger.info("\n脚注处理统计:")
        logger.info(f"总脚注数: {self.stats['total_footnotes']}")
        logger.info(f"有效脚注数: {self.stats['inserted_footnotes']}")
        logger.info(f"被排除脚注数: {self.stats['total_footnotes'] - self.stats['inserted_footnotes']}")
        if self.insert_by_page:
            logger.info(f"成功插入脚注数: {self.stats['matched_footnotes']}")
            success_rate = self.stats['matched_footnotes'] / self.stats['inserted_footnotes'] * 100 if self.stats['inserted_footnotes'] > 0 else 0
            logger.info(f"插入成功率: {success_rate:.1f}%")
        else:
            logger.info(f"成功匹配位置数: {self.stats['matched_footnotes']}")
            logger.info(f"未匹配位置数: {self.stats['unmatched_footnotes']}")
            match_rate = self.stats['matched_footnotes'] / self.stats['inserted_footnotes'] * 100 if self.stats['inserted_footnotes'] > 0 else 0
            logger.info(f"位置匹配率: {match_rate:.1f}%")
        
        logger.info("\n处理完成")
        
        return final_text, self.stats, self.page_footnote_counts


# ================= 工具函数 =================

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


# ================= 主程序 =================

# 解耦后的主函数组件

def setup_rich_console():
    """初始化Rich控制台和相关组件"""
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn
    from rich.markdown import Markdown
    from rich.table import Table
    from rich import print as rprint
    
    console = Console()
    
    return {
        'console': console,
        'Panel': Panel,
        'Prompt': Prompt,
        'Confirm': Confirm,
        'Progress': Progress,
        'TextColumn': TextColumn,
        'BarColumn': BarColumn,
        'TaskProgressColumn': TaskProgressColumn,
        'Markdown': Markdown,
        'Table': Table,
        'rprint': rprint
    }

def manage_presets(rich_comps):
    """预设管理功能"""
    import json
    from pathlib import Path
    
    console = rich_comps['console']
    Prompt = rich_comps['Prompt']
    
    # 预设配置管理
    presets_dir = Path.home() / ".glowtoolbox" / "presets"
    presets_dir.mkdir(parents=True, exist_ok=True)
    presets_file = presets_dir / "footnotes2mineru_presets.json"
    
    # 加载预设
    def load_presets():
        if presets_file.exists():
            try:
                with open(presets_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                console.print(f"[yellow]加载预设失败: {e}[/yellow]")
        return {}
    
    # 保存预设
    def save_preset(name, config):
        presets = load_presets()
        presets[name] = config
        try:
            with open(presets_file, 'w', encoding='utf-8') as f:
                json.dump(presets, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            console.print(f"[red]保存预设失败: {e}[/red]")
            return False
    
    # 显示预设列表
    def show_presets():
        presets = load_presets()
        if not presets:
            console.print("[yellow]暂无保存的预设[/yellow]")
            return None
        
        console.print("\n[bold]已保存的预设:[/bold]")
        for i, (name, config) in enumerate(presets.items(), 1):
            console.print(f"{i}. [cyan]{name}[/cyan]")
            for key, value in config.items():
                if isinstance(value, bool):
                    value_display = "是" if value else "否"
                elif key == "similarity_threshold":
                    value_display = f"{value:.2f}"
                else:
                    value_display = value
                console.print(f"   [dim]- {key}: {value_display}[/dim]")
        
        choice = Prompt.ask("\n选择预设编号，或按回车跳过", default="")
        if not choice:
            return None
        
        try:
            index = int(choice) - 1
            if 0 <= index < len(presets):
                preset_name = list(presets.keys())[index]
                return preset_name, presets[preset_name]
            else:
                console.print("[red]无效的预设编号[/red]")
                return None
        except ValueError:
            console.print("[red]请输入有效的数字[/red]")
            return None
    
    return {
        'load_presets': load_presets,
        'save_preset': save_preset,
        'show_presets': show_presets
    }

def select_files(rich_comps, config):
    """文件选择功能"""
    from pathlib import Path
    
    console = rich_comps['console']
    Prompt = rich_comps['Prompt']
    
    # 获取工作目录
    default_dir = config.get("work_dir", ".")
    work_dir = Prompt.ask(
        "请输入工作目录", 
        default=default_dir
    ).strip().strip('"')
    
    if not work_dir:
        work_dir = "."
    
    # 查找匹配的文件
    with console.status("[bold green]查找匹配的文件...[/bold green]"):
        file_pairs = find_matching_files(work_dir)
    
    if not file_pairs:
        console.print(f"\n[red]在目录 {work_dir} 中没有找到匹配的文件对[/red]")
        return None, work_dir
    
    console.print("\n[bold]找到以下文件对:[/bold]")
    for i, (json_file, md_file) in enumerate(file_pairs, 1):
        console.print(f"{i}. [cyan]{json_file.name}[/cyan] -> [green]{md_file.name}[/green]")
    
    # 选择文件对
    file_choice = Prompt.ask(
        "选择要处理的文件对编号",
        default="1"
    )
    try:
        file_index = int(file_choice) - 1
        if not (0 <= file_index < len(file_pairs)):
            console.print("[red]无效的文件编号，使用第一个文件对[/red]")
            file_index = 0
    except ValueError:
        console.print("[red]无效的输入，使用第一个文件对[/red]")
        file_index = 0
    
    selected_files = file_pairs[file_index]
    return selected_files, work_dir

def get_processing_params(rich_comps, config):
    """获取处理参数"""
    console = rich_comps['console']
    Prompt = rich_comps['Prompt']
    Confirm = rich_comps['Confirm']
    
    # 获取相似度阈值
    default_threshold = config.get("similarity_threshold", 0.8)
    threshold_input = Prompt.ask(
        "请输入文本匹配相似度阈值(0-1)",
        default=str(default_threshold)
    )
    try:
        threshold = float(threshold_input)
        if not (0 <= threshold <= 1):
            console.print("[yellow]阈值超出范围，使用默认值0.8[/yellow]")
            threshold = 0.8
    except ValueError:
        console.print("[yellow]无效的阈值，使用默认值0.8[/yellow]")
        threshold = 0.8
    
    # 获取是否添加页码标记
    default_add_page = "y" if config.get("add_page_marks", False) else "n"
    add_page = Confirm.ask(
        "是否添加页码标记?",
        default=True if default_add_page == "y" else False
    )
    
    # 获取脚注插入方式
    default_insert_mode = "1" if config.get("insert_by_page", True) else "2"
    insert_mode = Prompt.ask(
        "选择脚注插入方式 [1:按页码插入 2:按关键词匹配插入]",
        choices=["1", "2"],
        default=default_insert_mode
    )
    insert_by_page = insert_mode == "1"
    
    return {
        "similarity_threshold": threshold,
        "add_page_marks": add_page,
        "insert_by_page": insert_by_page
    }

def display_footnote_details(rich_comps, footnotes_details):
    """显示脚注详细信息"""
    console = rich_comps['console']
    Table = rich_comps['Table']
    
    # 创建脚注表格
    table = Table(
        title="脚注详细信息",
        show_header=True,
        header_style="bold cyan"
    )
    
    # 添加表格列
    table.add_column("ID", style="dim", width=4)
    table.add_column("页码", width=5)
    table.add_column("内容预览", width=40)
    table.add_column("上下文预览", width=40)
    
    # 添加表格行
    for detail in footnotes_details:
        # 截断过长的文本
        footnote_text = detail["text"]
        footnote_preview = footnote_text[:35] + "..." if len(footnote_text) > 35 else footnote_text
        context_preview = detail["context"][:35] + "..." if len(detail["context"]) > 35 else detail["context"]
        
        table.add_row(
            str(detail["id"]),
            str(detail["page"]),
            footnote_preview,
            context_preview
        )
    
    # 显示表格
    console.print("\n[bold]脚注详细信息[/bold]")
    console.print(table)
    console.print(f"总计: [cyan]{len(footnotes_details)}[/cyan] 个脚注\n")

def process_document(rich_comps, files, params):
    """处理文档并显示详细信息"""
    import json
    from pathlib import Path
    
    console = rich_comps['console']
    Progress = rich_comps['Progress']
    TextColumn = rich_comps['TextColumn']
    BarColumn = rich_comps['BarColumn']
    TaskProgressColumn = rich_comps['TaskProgressColumn']
    Markdown = rich_comps['Markdown']
    
    json_file, md_file = files
    
    try:
        # 获取原始文件大小
        original_size = md_file.stat().st_size
        
        # 读取JSON文件
        with console.status("[bold green]读取JSON文件...[/bold green]"):
            with open(json_file, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
        
        # 创建处理器实例
        processor = FootnoteProcessor(
            json_data=json_data,
            official_md_path=str(md_file),
            similarity_threshold=params["similarity_threshold"],
            add_page_marks=params["add_page_marks"],
            insert_by_page=params["insert_by_page"]
        )
        
        # 预处理阶段 - 收集脚注
        with Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            # 步骤1: 预处理页面
            preprocess_task = progress.add_task("[bold blue]预处理页面...", total=1)
            total_pages, unmatched_pages, matched_points = processor.preprocess_pages()
            progress.update(preprocess_task, completed=1)
            
            # 步骤2: 收集脚注
            collect_task = progress.add_task("[bold blue]收集脚注...", total=1)
            processor.collect_footnotes()
            progress.update(collect_task, completed=1)
            
            # 显示脚注详细信息
            footnotes_details = processor.collect_footnote_details()
            progress.stop()
        
        # 显示收集到的脚注详情
        display_footnote_details(rich_comps, footnotes_details)
        
        # 询问是否继续处理
        if rich_comps['Confirm'].ask("是否继续处理脚注?", default=True):
            with Progress(
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console
            ) as progress:
                # 步骤3: 处理页面，找到插入点
                process_task = progress.add_task("[bold green]处理文档...", total=3)
                page_insert_points, processed_pages, matched_points = processor.process_pages(total_pages, unmatched_pages, matched_points)
                progress.update(process_task, advance=1)
                
                # 步骤4: 处理未匹配的页面
                unmatched_insert_points = processor.process_unmatched_pages(unmatched_pages, matched_points, total_pages)
                progress.update(process_task, advance=1)
                
                # 步骤5: 如果是按关键词匹配，处理脚注
                keyword_insert_points = processor.process_keyword_footnotes(matched_points)
                
                # 步骤6: 合并所有插入点并构建最终文本
                all_insert_points = page_insert_points + unmatched_insert_points + keyword_insert_points
                markdown_text = processor.build_final_text(all_insert_points)
                progress.update(process_task, advance=1)
            
            # 生成输出文件路径
            output_path = md_file.parent / f"{md_file.stem}_footnotes{md_file.suffix}"
            
            # 写入输出文件
            with console.status("[bold green]写入输出文件...[/bold green]"):
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(markdown_text)
            
            # 检查文件大小变化
            new_size = output_path.stat().st_size
            size_increase = (new_size - original_size) / original_size * 100
            
            console.print(f"\n[bold green]✓ 处理完成！[/bold green]")
            console.print(f"输出文件：[cyan]{output_path}[/cyan]")
            console.print(f"原始文件大小: [yellow]{original_size / 1024:.2f} KB[/yellow]")
            console.print(f"新文件大小: [yellow]{new_size / 1024:.2f} KB[/yellow]")
            
            if size_increase > 10:
                console.print(f"\n[bold yellow]⚠️ 警告：文件大小增加了 {size_increase:.1f}%，超过了10%的阈值[/bold yellow]")
            else:
                console.print(f"文件大小增加: [green]{size_increase:.1f}%[/green]")
            
            # 添加页面脚注统计信息
            console.print("\n[bold]脚注插入统计:[/bold]")
            
            # 创建按页脚注统计表格
            footnote_table = rich_comps['Table'](title="脚注插入统计", show_header=True)
            footnote_table.add_column("页码", style="cyan")
            footnote_table.add_column("脚注数量", style="green")
            footnote_table.add_column("成功率", style="yellow")
            
            if params["insert_by_page"]:
                console.print("[yellow]按页码插入模式[/yellow]")
                # 从处理结果中提取页面统计数据
                for page_idx in sorted(processor.page_footnote_counts.keys()):
                    if processor.page_footnote_counts[page_idx] > 0:
                        # 计算该页的脚注成功率
                        page_footnotes = [f for f in processor.footnotes if f['page'] == page_idx]
                        success_count = len(page_footnotes)
                        success_rate = success_count / processor.page_footnote_counts[page_idx] * 100
                        
                        footnote_table.add_row(
                            f"第{page_idx + 1}页", 
                            str(processor.page_footnote_counts[page_idx]),
                            f"{success_rate:.1f}%"
                        )
            else:
                console.print("[yellow]按关键词匹配插入模式[/yellow]")
                # 可以提供匹配成功率等信息
                match_rate = processor.stats.get('matched_footnotes', 0) / processor.stats.get('inserted_footnotes', 1) * 100
                console.print(f"- 总体匹配成功率: [cyan]{match_rate:.1f}%[/cyan]")
                console.print(f"- 成功匹配: [green]{processor.stats.get('matched_footnotes', 0)}[/green] 个")
                console.print(f"- 未能匹配: [yellow]{processor.stats.get('unmatched_footnotes', 0)}[/yellow] 个")
                
                # 按页显示脚注匹配情况
                for page_idx in sorted(processor.page_footnote_counts.keys()):
                    if processor.page_footnote_counts[page_idx] > 0:
                        # 计算该页的关键词匹配成功率
                        page_footnotes = [f for f in processor.footnotes if f['page'] == page_idx]
                        matched_count = sum(1 for f in page_footnotes if hasattr(f, 'matched') and f.matched)
                        success_rate = matched_count / len(page_footnotes) * 100 if page_footnotes else 0
                        
                        footnote_table.add_row(
                            f"第{page_idx + 1}页", 
                            str(processor.page_footnote_counts[page_idx]),
                            f"{success_rate:.1f}%"
                        )
            
            # 显示脚注统计表格
            console.print(footnote_table)
            
            return {
                "work_dir": str(md_file.parent), 
                "similarity_threshold": params["similarity_threshold"],
                "add_page_marks": params["add_page_marks"],
                "insert_by_page": params["insert_by_page"]
            }
        else:
            console.print("[yellow]已取消处理[/yellow]")
            return None
        
    except Exception as e:
        console.print(f"\n[bold red]✗ 处理失败[/bold red]")
        console.print(f"[red]{str(e)}[/red]")
        import traceback
        console.print(Markdown("```\n" + traceback.format_exc() + "\n```"))
        return None

def main():
    # 初始化Rich组件
    rich_comps = setup_rich_console()
    console = rich_comps['console']
    
    # 绘制标题
    console.print(rich_comps['Panel'].fit(
        "[bold blue]脚注处理工具[/bold blue] - 将脚注添加到Markdown文档中",
        border_style="blue"
    ))
    
    # 初始化预设管理
    preset_manager = manage_presets(rich_comps)
    
    # 显示并选择预设
    preset_result = preset_manager['show_presets']()
    config = {}
    
    if preset_result:
        preset_name, config = preset_result
        console.print(f"\n[green]已加载预设: [bold]{preset_name}[/bold][/green]")
    
    # 选择文件
    selection_result = select_files(rich_comps, config)
    if not selection_result:
        console.print("\n[dim]按回车键退出...[/dim]")
        input()
        return
    
    selected_files, work_dir = selection_result
    
    # 获取处理参数
    processing_params = get_processing_params(rich_comps, config)
    
    # 确认处理
    json_file, md_file = selected_files
    console.print(f"\n[bold]即将处理:[/bold]")
    console.print(f"- JSON文件: [cyan]{json_file}[/cyan]")
    console.print(f"- MD文件: [green]{md_file}[/green]")
    console.print(f"- 相似度阈值: [yellow]{processing_params['similarity_threshold']}[/yellow]")
    console.print(f"- 添加页码标记: [yellow]{'是' if processing_params['add_page_marks'] else '否'}[/yellow]")
    console.print(f"- 插入方式: [yellow]{'按页码插入' if processing_params['insert_by_page'] else '按关键词匹配插入'}[/yellow]")
    
    if not rich_comps['Confirm'].ask("是否继续?", default=True):
        console.print("[yellow]已取消操作[/yellow]")
        console.print("\n[dim]按回车键退出...[/dim]")
        input()
        return
    
    # 处理文档
    result_config = process_document(rich_comps, selected_files, processing_params)
    
    # 询问是否保存为预设
    if result_config and rich_comps['Confirm'].ask("是否保存当前配置为预设?", default=False):
        preset_name = rich_comps['Prompt'].ask("输入预设名称", default="默认预设")
        result_config["work_dir"] = work_dir  # 使用选择的工作目录
        if preset_manager['save_preset'](preset_name, result_config):
            console.print(f"[green]预设 [bold]{preset_name}[/bold] 已保存[/green]")
    
    console.print("\n[dim]按回车键退出...[/dim]")
    input()
if __name__ == '__main__':
    main()