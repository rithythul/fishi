"""
文本processservice
"""

from typing import List, Optional
from ..utils.file_parser import FileParser, split_text_into_chunks


class TextProcessor:
    """text processing器"""
    
    @staticmethod
    def extract_from_files(file_paths: List[str]) -> str:
        """from多fileExtract文本"""
        return FileParser.extract_from_multiple(file_paths)
    
    @staticmethod
    def split_text(
        text: str,
        chunk_size: int = 500,
        overlap: int = 50
    ) -> List[str]:
        """
        split文本
        
        Args:
            text: 原始文本
            chunk_size: blockssize
            overlap: 重叠size
            
        Returns:
            文本blockslist
        """
        return split_text_into_chunks(text, chunk_size, overlap)
    
    @staticmethod
    def preprocess_text(text: str) -> str:
        """
        预process文本
        - 移除多余空白
        - 标准化换行
        
        Args:
            text: 原始文本
            
        Returns:
            process后of文本
        """
        import re
        
        # 标准化换行
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        
        # 移除连续空行（保留最多两换行）
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # 移除行首行尾空白
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(lines)
        
        return text.strip()
    
    @staticmethod
    def get_text_stats(text: str) -> dict:
        """get文本statisticsinformation"""
        return {
            "total_chars": len(text),
            "total_lines": text.count('\n') + 1,
            "total_words": len(text.split()),
        }

