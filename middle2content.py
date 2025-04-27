import json
from pathlib import Path
from collections import defaultdict

# 确保从正确的位置导入所需的函数和枚举
try:
    # 导入 union_make 和相关配置
    from magic_pdf.dict2md.ocr_mkcontent import union_make, merge_para_with_text
    from magic_pdf.config.make_content_config import MakeMode, DropMode
except ImportError:
    print("错误：无法导入 magic_pdf 库。请确保您已正确安装 MinerU 及其依赖项，")
    print("并且正在项目的根目录或已设置好 Python 环境路径。")
    exit(1)

def convert_interactive():
    """
    交互式地将 middle.json 文件转换为 content_list.json 文件，
    并可选择性地包含页面底部指定比例的 discarded_blocks。
    """
    # --- 获取输入文件路径 ---
    while True:
        middle_json_path_str = input("请输入 middle.json 文件的完整路径: ").strip()
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
        content_list_path_str = input("请输入要保存的 content_list.json 文件的完整路径: ").strip()
        if not content_list_path_str:
            print("输入不能为空，请重新输入。")
            continue
        content_list_path = Path(content_list_path_str)
        # 检查父目录是否存在，如果不存在则尝试创建
        try:
            content_list_path.parent.mkdir(parents=True, exist_ok=True)
            # 简单的路径有效性检查（不是完全的权限检查）
            if content_list_path.parent.exists() and content_list_path.parent.is_dir():
                 # 检查文件名是否有效 (基本检查)
                if content_list_path.name:
                    break
                else:
                    print(f"错误: 输出路径 '{content_list_path_str}' 必须包含文件名。")
            else:
                 print(f"错误: 无法创建或访问目录 '{content_list_path.parent}'。请检查路径和权限。")

        except OSError as e:
             print(f"错误: 无法创建或写入路径 '{content_list_path_str}'。错误信息: {e}。请检查路径和权限。")
        except Exception as e:
            print(f"发生未知路径错误: {e}。请检查路径。")


    # --- 获取图片目录/前缀 ---
    image_dir_or_prefix = input("请输入图片目录或S3存储桶前缀 (用于图片路径拼接，可留空): ").strip()

    # --- 询问是否保留 discarded_blocks ---
    while True:
        keep_discarded_input = input("是否处理并保留页面底部的 discarded_blocks? (y/n): ").strip().lower()
        if keep_discarded_input in ['y', 'yes']:
            keep_discarded = True
            break
        elif keep_discarded_input in ['n', 'no']:
            keep_discarded = False
            break
        else:
            print("无效输入，请输入 'y' 或 'n'。")

    # --- 如果保留，获取底部阈值 ---
    bottom_threshold_percent = 20 # 默认值
    if keep_discarded:
        while True:
            try:
                threshold_input = input(f"请输入要保留的页面底部内容的百分比 (例如 20 表示底部 20%，默认为 {bottom_threshold_percent}): ").strip()
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
            middle_data = json.load(f)

        # --- 提取 pdf_info ---
        if 'pdf_info' not in middle_data:
            print(f"错误: '{middle_json_path}' 文件中缺少 'pdf_info' 键。请确保这是一个有效的 middle.json 文件。")
            return

        pdf_info_list = middle_data['pdf_info']
        if not isinstance(pdf_info_list, list):
             print(f"错误: '{middle_json_path}' 文件中的 'pdf_info' 值不是一个列表。")
             return

        # --- 调用转换函数 (获取基础 content_list) ---
        print("正在转换主要内容...")
        # 使用 union_make 进行转换，指定输出为 STANDARD_FORMAT (content_list)
        # union_make 返回的是一个扁平化的列表
        base_content_list_data = union_make(
            pdf_info_list,
            MakeMode.STANDARD_FORMAT,
            DropMode.NONE, # 通常使用 NONE，除非有特殊需求
            image_dir_or_prefix,
        )

        # --- 按页面分组基础内容 ---
        grouped_base_content = defaultdict(list)
        max_page_idx = -1
        for item in base_content_list_data:
            page_idx = item.get('page_idx', -1)
            if page_idx != -1:
                grouped_base_content[page_idx].append(item)
                if page_idx > max_page_idx:
                    max_page_idx = page_idx

        # --- 如果需要，处理 discarded_blocks ---
        grouped_discarded_content = defaultdict(list)
        if keep_discarded:
            print(f"正在处理 discarded_blocks (保留底部 {bottom_threshold_percent}%)...")
            threshold_ratio = 1.0 - (bottom_threshold_percent / 100.0)
            processed_discarded_count = 0

            for page_idx, page_data in enumerate(pdf_info_list):
                page_size = page_data.get('page_size')
                if not page_size or len(page_size) < 2:
                    print(f"警告: 第 {page_idx} 页缺少有效的 'page_size' 信息，无法处理 discarded_blocks。")
                    continue
                page_height = page_size[1]
                y_threshold = page_height * threshold_ratio # 计算阈值 Y 坐标

                discarded_blocks = page_data.get('discarded_blocks')
                if discarded_blocks and isinstance(discarded_blocks, list):
                    for block in discarded_blocks:
                        bbox = block.get("bbox")
                        # 检查 bbox 是否存在且有效，并且块的顶部是否在阈值之下
                        if bbox and len(bbox) >= 4 and bbox[1] >= y_threshold:
                            try:
                                # 尝试合并文本
                                merged_text = merge_para_with_text(block)
                                discarded_item = {
                                    "type": "text", # 默认类型为 text
                                    "text": merged_text,
                                    # "status": "discarded", # 添加状态标识
                                    "page_idx": page_idx
                                    # 不包含 bbox
                                }
                                grouped_discarded_content[page_idx].append(discarded_item)
                                processed_discarded_count += 1
                            except Exception as e:
                                print(f"警告: 处理第 {page_idx} 页的 discarded_block 时出错: {e}。跳过此块。块内容: {str(block)[:100]}...") # 打印部分块内容以供调试

            print(f"已提取并筛选 {processed_discarded_count} 个 discarded_blocks。")

        # --- 组合最终结果 ---
        final_content_list = []
        print("正在组合最终输出...")
        for page_idx in range(max_page_idx + 1):
            # 添加基础内容
            if page_idx in grouped_base_content:
                final_content_list.extend(grouped_base_content[page_idx])
            # 添加符合条件的 discarded 内容
            if keep_discarded and page_idx in grouped_discarded_content:
                final_content_list.extend(grouped_discarded_content[page_idx])

        # --- 写入 content_list.json ---
        print(f"正在写入 '{content_list_path}'...")
        with open(content_list_path, 'w', encoding='utf-8') as f:
            json.dump(final_content_list, f, ensure_ascii=False, indent=4)

        print("\n转换成功！")
        print(f"content_list.json 文件已保存至: {content_list_path.resolve()}")

    except json.JSONDecodeError:
        print(f"错误: '{middle_json_path}' 不是有效的 JSON 文件。请检查文件内容。")
    except FileNotFoundError:
        # 这个理论上不会发生，因为前面已经检查过了，但为了健壮性保留
        print(f"错误: 文件 '{middle_json_path}' 未找到。")
    except ImportError:
         # 这个理论上也不会发生，因为前面检查了，但为了健壮性保留
        print("错误：无法导入 magic_pdf 库。请确保环境设置正确。")
    except Exception as e:
        print(f"\n转换过程中发生错误: {e}")
        import traceback
        traceback.print_exc() # 打印详细错误堆栈

if __name__ == "__main__":
    print("--- Middle.json 到 Content_list.json 转换工具 ---")
    convert_interactive()
    print("\n--- 转换结束 ---")