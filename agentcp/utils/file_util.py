# -*- coding: utf-8 -*-
import os
def get_file_info(file_path: str) -> dict:
    """
    通过文件路径读取文件信息
    
    Args:
        file_path (str): 文件的完整路径
        
    Returns:
        dict: 包含文件信息的字典，格式为：
              {
                  'file_name': str,     # 文件名
                  'file_size': int,     # 文件大小（字节）
                  'file_type': str,     # 文件类型/扩展名
                  'exists': bool,       # 文件是否存在
                  'error': str          # 错误信息（如果有）
              }
    """
    try:
        # 检查文件是否存在
        if not os.path.exists(file_path):
            return {
                'file_name': '',
                'file_size': 0,
                'file_type': '',
                'exists': False,
                'error': '文件不存在'
            }
        
        # 检查是否为文件（而不是目录）
        if not os.path.isfile(file_path):
            return {
                'file_name': '',
                'file_size': 0,
                'file_type': '',
                'exists': False,
                'error': '路径不是文件'
            }
        
        # 获取文件信息
        file_stats = os.stat(file_path)
        file_name = os.path.basename(file_path)
        file_size = file_stats.st_size
        
        # 获取文件扩展名作为文件类型
        file_type = os.path.splitext(file_path)[1].lower()
        if file_type.startswith('.'):
            file_type = file_type[1:]  # 移除开头的点
        
        # 如果没有扩展名，尝试根据文件内容判断类型
        if not file_type:
            file_type = _detect_file_type(file_path)
        
        return {
            'file_name': file_name,
            'file_size': file_size,
            'file_type': file_type,
            'exists': True,
            'error': ''
        }
        
    except PermissionError:
        return {
            'file_name': '',
            'file_size': 0,
            'file_type': '',
            'exists': False,
            'error': '没有权限访问文件'
        }
    except Exception as e:
        return {
            'file_name': '',
            'file_size': 0,
            'file_type': '',
            'exists': False,
            'error': f'读取文件信息时发生错误: {str(e)}'
        }

def _detect_file_type(file_path: str) -> str:
    """
    当文件没有扩展名时，尝试检测文件类型
    
    Args:
        file_path (str): 文件路径
        
    Returns:
        str: 检测到的文件类型
    """
    try:
        with open(file_path, 'rb') as f:
            # 读取文件头部字节来判断文件类型
            header = f.read(16)
            
            # 常见文件类型的魔数检测
            if header.startswith(b'\x89PNG\r\n\x1a\n'):
                return 'png'
            elif header.startswith(b'\xff\xd8\xff'):
                return 'jpg'
            elif header.startswith(b'GIF8'):
                return 'gif'
            elif header.startswith(b'%PDF'):
                return 'pdf'
            elif header.startswith(b'PK\x03\x04'):
                return 'zip'
            elif header.startswith(b'\x50\x4b\x03\x04'):
                return 'zip'
            else:
                # 尝试作为文本文件读取
                try:
                    f.seek(0)
                    f.read().decode('utf-8')
                    return 'txt'
                except UnicodeDecodeError:
                    return 'binary'
    except Exception:
        return 'unknown'