import json
import re
from pathlib import Path
import copy # 用于深拷贝数据，避免修改原始输入数据
from typing import Dict, List, Any, Optional

def reprocess_middle_interactive():
    """
    交互式地处理 middle.json 文件，将页面底部指定比例的 discarded_blocks
    移动到 para_blocks 的末尾，并保存为新的 middle.json 文件。
    """
    # --- 获取输入文件路径 ---
    while True:
        middle_json_path_str = input("请输入原始 middle.json 文件的完整路径: ").strip()
        if not middle_json_path_str:
            print("输入不能为空，请重新输入。")
            continue
        middle_json_path = Path(middle_json_path_str)
        if middle_json_path.is_file():
            break
        else:
            print(f"错误: 文件 '{middle_json_path_str}' 不存在或不是一个文件。请重试。")

    # --- 获取输出文件路径 ---
    while True:
        output_middle_path_str = input("请输入要保存的新 middle.json 文件的完整路径: ").strip()
        if not output_middle_path_str:
            print("输入不能为空，请重新输入。")
            continue
        output_middle_path = Path(output_middle_path_str)
        # 检查父目录是否存在，如果不存在则尝试创建
        try:
            output_middle_path.parent.mkdir(parents=True, exist_ok=True)
            if output_middle_path.parent.exists() and output_middle_path.parent.is_dir():
                if output_middle_path.name:
                    # 防止覆盖输入文件
                    if output_middle_path.resolve() == middle_json_path.resolve():
                         print("错误: 输出文件不能与输入文件相同。请指定不同的输出路径。")
                         continue
                    break
                else:
                    print(f"错误: 输出路径 '{output_middle_path_str}' 必须包含文件名。")
            else:
                 print(f"错误: 无法创建或访问目录 '{output_middle_path.parent}'。请检查路径和权限。")
        except OSError as e:
             print(f"错误: 无法创建或写入路径 '{output_middle_path_str}'。错误信息: {e}。请检查路径和权限。")
        except Exception as e:
            print(f"发生未知路径错误: {e}。请检查路径。")

    # --- 询问是否处理 discarded_blocks ---
    while True:
        process_discarded_input = input("是否处理并将页面底部的 discarded_blocks 移至 para_blocks? (y/n): ").strip().lower()
        if process_discarded_input in ['y', 'yes']:
            process_discarded = True
            break
        elif process_discarded_input in ['n', 'no']:
            process_discarded = False
            break
        else:
            print("无效输入，请输入 'y' 或 'n'。")

    # --- 如果处理，获取底部阈值 ---
    bottom_threshold_percent = 20 # 默认值
    if process_discarded:
        while True:
            try:
                threshold_input = input(f"请输入要移动的页面底部内容的百分比 (例如 20 表示底部 20%，默认为 {bottom_threshold_percent}): ").strip()
                if not threshold_input: # 用户直接回车，使用默认值
                    break
                threshold_val = float(threshold_input)
                if 0 < threshold_val <= 100:
                    bottom_threshold_percent = threshold_val
                    break
                else:
                    print("百分比必须在 0 到 100 之间。")
            except ValueError:
                print("无效输入，请输入一个数字。")

    try:
        # --- 读取 middle.json ---
        print(f"\n正在读取 '{middle_json_path}'...")
        with open(middle_json_path, 'r', encoding='utf-8') as f:
            original_middle_data = json.load(f)

        # 深拷贝数据以进行修改
        modified_middle_data = copy.deepcopy(original_middle_data)

        # --- 检查 pdf_info ---
        if 'pdf_info' not in modified_middle_data:
            print(f"错误: '{middle_json_path}' 文件中缺少 'pdf_info' 键。请确保这是一个有效的 middle.json 文件。")
            return

        pdf_info_list = modified_middle_data['pdf_info']
        if not isinstance(pdf_info_list, list):
             print(f"错误: '{middle_json_path}' 文件中的 'pdf_info' 值不是一个列表。")
             return

        moved_blocks_count = 0
        fixed_pages_count = 0
        # --- 如果需要，处理 discarded_blocks ---
        if process_discarded:
            print(f"正在处理 discarded_blocks (移动底部 {bottom_threshold_percent}%)...")
            threshold_ratio = 1.0 - (bottom_threshold_percent / 100.0)

            for page_idx, page_data in enumerate(pdf_info_list):
                # 跳过空的页面数据
                if not page_data:
                    continue
                    
                # 检查并修复不完整的页面数据结构
                if fix_incomplete_page_data(page_data, page_idx):
                    fixed_pages_count += 1
                    
                page_size = page_data.get('page_size')
                if not page_size or len(page_size) < 2:
                    print(f"警告: 第 {page_idx} 页缺少有效的 'page_size' 信息，无法处理 discarded_blocks。")
                    continue
                page_height = page_size[1]
                y_threshold = page_height * threshold_ratio # 计算阈值 Y 坐标

                discarded_blocks = page_data.get('discarded_blocks')
                para_blocks = page_data.get('para_blocks')

                if not isinstance(discarded_blocks, list):
                    # 如果页面没有 discarded_blocks 或格式不正确，跳过该页面
                    continue
                if not isinstance(para_blocks, list):
                    # 如果页面没有 para_blocks 列表，创建一个空列表
                    page_data['para_blocks'] = []
                    para_blocks = page_data['para_blocks']

                blocks_to_move = []
                remaining_discarded = []

                for block in discarded_blocks:
                    bbox = block.get("bbox")
                    # 检查 bbox 是否存在且有效，并且块的顶部是否在阈值之下
                    if bbox and len(bbox) >= 4 and bbox[1] >= y_threshold:
                        # 转换为 para_block 兼容格式
                        converted_block = convert_to_para_block_format(block)
                        if converted_block:
                            blocks_to_move.append(converted_block)
                        else:
                            remaining_discarded.append(block)
                    else:
                        remaining_discarded.append(block)

                if blocks_to_move:
                    # 将筛选出的块追加到 para_blocks 末尾
                    para_blocks.extend(blocks_to_move)
                    # 更新 discarded_blocks 列表为剩余的块
                    page_data['discarded_blocks'] = remaining_discarded
                    print(f"第 {page_idx} 页移动了 {len(blocks_to_move)} 个 discarded_blocks 到 para_blocks。")

            print(f"处理完成，共修复了 {fixed_pages_count} 页数据结构，移动了 {moved_blocks_count} 个 discarded_blocks。")
        else:
            print("未选择处理 discarded_blocks，将直接保存原始 middle.json 结构。")


        # --- 写入新的 middle.json ---
        print(f"正在写入 '{output_middle_path}'...")
        with open(output_middle_path, 'w', encoding='utf-8') as f:
            json.dump(modified_middle_data, f, ensure_ascii=False, indent=4)

        print("\n处理成功！")
        print(f"新的 middle.json 文件已保存至: {output_middle_path.resolve()}")

    except json.JSONDecodeError:
        print(f"错误: '{middle_json_path}' 不是有效的 JSON 文件。请检查文件内容。")
    except FileNotFoundError:
        print(f"错误: 文件 '{middle_json_path}' 未找到。")
    except Exception as e:
        print(f"\n处理过程中发生错误: {e}")
        import traceback
        traceback.print_exc() # 打印详细错误堆栈

def fix_incomplete_page_data(page_data: Dict[str, Any], page_idx: int) -> bool:
    """
    检查并修复页面数据中缺失的必要字段
    
    Args:
        page_data: 页面数据字典
        page_idx: 页面索引，用于日志记录
        
    Returns:
        bool: 如果修复了任何字段，返回 True，否则返回 False
    """
    fixed = False
    
    # 确保必需字段存在
    required_fields = [
        'preproc_blocks', 'layout_bboxes', 'page_idx', 'page_size', '_layout_tree',
        'images', 'tables', 'interline_equations', 'discarded_blocks', 'para_blocks'
    ]
    
    for field in required_fields:
        if field not in page_data:
            if field in ['preproc_blocks', 'layout_bboxes', 'images', 'tables', 
                         'interline_equations', 'discarded_blocks', 'para_blocks']:
                page_data[field] = []
            elif field == '_layout_tree':
                page_data[field] = []
            elif field == 'page_idx':
                page_data[field] = page_idx
            elif field == 'page_size' and 'page_size' not in page_data:
                # 如果没有 page_size，设置默认值 [1000.0, 1000.0]
                page_data[field] = [1000.0, 1000.0]
            fixed = True
    
    # 确保 page_size 有两个元素 [width, height]
    if 'page_size' in page_data and isinstance(page_data['page_size'], list):
        if len(page_data['page_size']) == 1:
            # 只有宽度，添加默认高度
            page_data['page_size'].append(1400.0)
            fixed = True
        elif len(page_data['page_size']) == 0:
            # 空列表，设置默认值
            page_data['page_size'] = [1000.0, 1400.0]
            fixed = True
            
    # 添加或确保其他可选字段
    if 'need_drop' not in page_data:
        page_data['need_drop'] = False
        fixed = True
    if 'drop_reason' not in page_data:
        page_data['drop_reason'] = []
        fixed = True
    
    return fixed

def convert_to_para_block_format(discarded_block: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    将 discarded_block 转换为 para_blocks 兼容的格式
    
    Args:
        discarded_block: 从 discarded_blocks 中获取的块
        
    Returns:
        转换后的块，如果无法转换则返回 None
    """
    try:
        # 检查 discarded_block 是否有必要的属性
        if 'bbox' not in discarded_block:
            print(f"警告: discarded_block 缺少 bbox 属性，无法转换")
            return None
            
        # 如果 discarded_block 已经有 lines 和 type，确保它们符合要求
        if 'lines' in discarded_block:
            converted_block = discarded_block.copy()
            
            # 强制将类型设为 text
            converted_block['type'] = 'text'
                
            # 确保每个 line 中的每个 span 有 type 和 content 属性
            for line in converted_block.get('lines', []):
                if 'spans' not in line or not isinstance(line['spans'], list):
                    line['spans'] = []
                    
                for span in line.get('spans', []):
                    if 'type' not in span:
                        if 'content' in span:
                            span['type'] = 'text'
                        else:
                            span['type'] = 'text'
                            span['content'] = ''
                    elif span['type'] not in ['text', 'inline_equation', 'interline_equation', 'image', 'table']:
                        # 确保 span['type'] 是有效的 ContentType 值
                        span['type'] = 'text'
            
            return converted_block
            
        # 如果 discarded_block 没有 lines 属性，需要创建完整的结构
        text_content = ""
        
        # 尝试从各种可能的字段提取文本内容
        for field in ['text', 'content', 'caption', 'description']:
            if field in discarded_block and discarded_block[field]:
                text_content = discarded_block[field]
                break
        
        # 创建一个新的符合 para_blocks 格式要求的块
        new_block = {
            'type': 'text',  # 默认类型为 text (BlockType.Text)
            'bbox': discarded_block['bbox'],
            'lines': [
                {
                    'bbox': discarded_block['bbox'],  # 使用同样的 bbox
                    'spans': [
                        {
                            'bbox': discarded_block['bbox'],  # 使用同样的 bbox
                            'type': 'text',  # ContentType.Text
                            'content': text_content
                        }
                    ]
                }
            ]
        }
        
        return new_block
    except Exception as e:
        print(f"转换块时发生错误: {e}")
        return None

if __name__ == "__main__":
    print("--- Middle.json Discarded Blocks Reprocessing Tool ---")
    reprocess_middle_interactive()
    print("\n--- 处理结束 ---")