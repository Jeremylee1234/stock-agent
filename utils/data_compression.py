"""
大数据处理模块 - 避免截断数据，使用智能压缩和分块处理
提供多种策略来处理超过模型token限制的数据：
1. 智能摘要/压缩
2. 分块处理
3. 分层总结
4. 数据存储与按需检索
"""
import json
import hashlib
import os
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import pickle


class DataCompressor:
    """数据压缩器 - 智能处理超长数据"""
    
    def __init__(
        self, 
        storage_dir: str = "./data_cache", 
        max_chunk_size: int = 10000,
        compression_threshold_tokens: int = 20000,
        chars_per_token: float = 3.5
    ):
        """
        Args:
            storage_dir: 数据存储目录
            max_chunk_size: 每个数据块的最大字符数
            compression_threshold_tokens: 触发压缩的token阈值
            chars_per_token: 每个token的平均字符数（用于估算）
        """
        self.storage_dir = storage_dir
        self.max_chunk_size = max_chunk_size
        self.compression_threshold_tokens = compression_threshold_tokens
        self.chars_per_token = chars_per_token
        os.makedirs(storage_dir, exist_ok=True)
        self._data_registry: Dict[str, Dict[str, Any]] = {}
        
        # 压缩统计信息
        self._compression_stats = {
            "total_compressions": 0,
            "total_original_size": 0,
            "total_compressed_size": 0,
            "compression_ratio": 0.0,
            "compressions_by_tool": {},
            "last_reset": datetime.now().isoformat()
        }
    
    def _get_data_id(self, data: Any) -> str:
        """生成数据的唯一ID"""
        data_str = json.dumps(data, ensure_ascii=False, default=str, sort_keys=True)
        return hashlib.md5(data_str.encode('utf-8')).hexdigest()
    
    def store_full_data(self, data: Any, metadata: Optional[Dict] = None) -> str:
        """存储完整数据到磁盘，返回数据ID
        
        Args:
            data: 要存储的数据
            metadata: 元数据（如工具名、时间等）
        
        Returns:
            data_id: 数据的唯一标识符
        """
        data_id = self._get_data_id(data)
        file_path = os.path.join(self.storage_dir, f"{data_id}.pkl")
        
        # 如果已存在，直接返回
        if os.path.exists(file_path):
            return data_id
        
        # 存储数据
        store_obj = {
            "data": data,
            "metadata": metadata or {},
            "stored_at": datetime.now().isoformat(),
            "data_id": data_id
        }
        
        with open(file_path, 'wb') as f:
            pickle.dump(store_obj, f)
        
        # 注册到内存
        self._data_registry[data_id] = {
            "file_path": file_path,
            "metadata": metadata or {},
            "size": len(json.dumps(data, ensure_ascii=False, default=str))
        }
        
        return data_id
    
    def retrieve_full_data(self, data_id: str) -> Optional[Any]:
        """根据ID检索完整数据"""
        if data_id in self._data_registry:
            file_path = self._data_registry[data_id]["file_path"]
        else:
            file_path = os.path.join(self.storage_dir, f"{data_id}.pkl")
        
        if not os.path.exists(file_path):
            return None
        
        try:
            with open(file_path, 'rb') as f:
                store_obj = pickle.load(f)
                return store_obj.get("data")
        except Exception as e:
            print(f"检索数据失败 {data_id}: {e}")
            return None
    
    def chunk_data(self, data: Any, chunk_size: Optional[int] = None) -> List[Dict[str, Any]]:
        """将数据分块处理
        
        Args:
            data: 要分块的数据
            chunk_size: 每块的大小（字符数），默认使用self.max_chunk_size
        
        Returns:
            chunks: 分块列表，每个块包含数据和元信息
        """
        if chunk_size is None:
            chunk_size = self.max_chunk_size
        
        # 如果是列表，按列表项分块
        if isinstance(data, list):
            chunks = []
            current_chunk = []
            current_size = 0
            
            for item in data:
                item_str = json.dumps(item, ensure_ascii=False, default=str)
                item_size = len(item_str)
                
                if current_size + item_size > chunk_size and current_chunk:
                    chunks.append({
                        "chunk_id": len(chunks),
                        "data": current_chunk,
                        "size": current_size,
                        "type": "list_chunk"
                    })
                    current_chunk = []
                    current_size = 0
                
                current_chunk.append(item)
                current_size += item_size
            
            if current_chunk:
                chunks.append({
                    "chunk_id": len(chunks),
                    "data": current_chunk,
                    "size": current_size,
                    "type": "list_chunk"
                })
            
            return chunks
        
        # 如果是字典，尝试按键分块
        elif isinstance(data, dict):
            data_str = json.dumps(data, ensure_ascii=False, default=str)
            if len(data_str) <= chunk_size:
                return [{"chunk_id": 0, "data": data, "size": len(data_str), "type": "dict"}]
            
            # 按键分组
            chunks = []
            current_chunk = {}
            current_size = 0
            
            for key, value in data.items():
                item_str = json.dumps({key: value}, ensure_ascii=False, default=str)
                item_size = len(item_str)
                
                if current_size + item_size > chunk_size and current_chunk:
                    chunks.append({
                        "chunk_id": len(chunks),
                        "data": current_chunk,
                        "size": current_size,
                        "type": "dict_chunk"
                    })
                    current_chunk = {}
                    current_size = 0
                
                current_chunk[key] = value
                current_size += item_size
            
            if current_chunk:
                chunks.append({
                    "chunk_id": len(chunks),
                    "data": current_chunk,
                    "size": current_size,
                    "type": "dict_chunk"
                })
            
            return chunks
        
        # 其他类型，按字符串分块
        else:
            data_str = str(data)
            if len(data_str) <= chunk_size:
                return [{"chunk_id": 0, "data": data, "size": len(data_str), "type": "string"}]
            
            chunks = []
            for i in range(0, len(data_str), chunk_size):
                chunk_data = data_str[i:i + chunk_size]
                chunks.append({
                    "chunk_id": len(chunks),
                    "data": chunk_data,
                    "size": len(chunk_data),
                    "type": "string_chunk"
                })
            
            return chunks
    
    def create_smart_summary(
        self, 
        data: Any, 
        user_query: str,
        model,
        max_summary_length: int = 2000,
        focus_points: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """创建智能摘要，保留关键信息
        
        Args:
            data: 要摘要的数据
            user_query: 用户查询，用于指导摘要重点
            model: LLM模型实例
            max_summary_length: 摘要最大长度
            focus_points: 需要重点关注的点
        
        Returns:
            summary_dict: 包含摘要、统计信息、关键数据等的字典
        """
        from langchain_core.messages import HumanMessage
        
        # 先做数据统计
        stats = self._extract_statistics(data)
        
        # 构建摘要提示
        data_preview = self._create_data_preview(data, max_length=5000)
        
        focus_text = ""
        if focus_points:
            focus_text = f"\n请特别关注以下方面：{', '.join(focus_points)}"
        
        summary_prompt = f"""你是一个专业的金融数据分析助手。用户的问题是：
《{user_query}》

下面是一段工具返回的数据（可能包含历史价格、财务指标、新闻等），数据可能很长，请创建一份**精炼但完整**的摘要：

数据预览：
{data_preview}

数据统计信息：
{json.dumps(stats, ensure_ascii=False, indent=2)}{focus_text}

请创建摘要，要求：
1. **保留所有关键数值**：价格、指标、日期、代码等具体数字
2. **保留趋势信息**：涨跌、变化方向、时间序列趋势
3. **保留异常值**：最大值、最小值、异常波动
4. **保留结构信息**：数据的时间范围、样本数量、数据类型
5. **去除冗余**：重复信息、不重要的细节、格式化字符

摘要格式：
- 数据概览（时间范围、样本数、数据类型）
- 关键数值（最重要的数字和指标）
- 趋势分析（如有时间序列数据）
- 异常发现（如有异常值或特殊情况）
- 数据完整性（缺失数据、数据质量）

请确保摘要不超过 {max_summary_length} 字符，但包含所有关键信息。"""
        
        try:
            response = model.invoke([HumanMessage(content=summary_prompt)])
            summary_text = getattr(response, "content", "")
            
            # 如果摘要太长，再次压缩
            if len(summary_text) > max_summary_length:
                summary_text = summary_text[:max_summary_length] + "...(已压缩)"
        except Exception as e:
            summary_text = f"[摘要生成失败: {type(e).__name__}: {e}]\n数据统计: {json.dumps(stats, ensure_ascii=False)}"
        
        return {
            "summary": summary_text,
            "statistics": stats,
            "data_size": len(json.dumps(data, ensure_ascii=False, default=str)),
            "summary_length": len(summary_text),
            "has_full_data": True  # 表示完整数据已存储，可随时检索
        }
    
    def _extract_statistics(self, data: Any) -> Dict[str, Any]:
        """提取数据的统计信息"""
        stats = {
            "type": type(data).__name__,
            "size": 0,
            "item_count": 0
        }
        
        if isinstance(data, list):
            stats["item_count"] = len(data)
            if data:
                stats["first_item_type"] = type(data[0]).__name__
                stats["last_item_type"] = type(data[-1]).__name__
                # 如果是字典列表，提取键信息
                if isinstance(data[0], dict):
                    stats["keys"] = list(data[0].keys())[:10]  # 最多显示10个键
        
        elif isinstance(data, dict):
            stats["item_count"] = len(data)
            stats["keys"] = list(data.keys())[:20]  # 最多显示20个键
        
        try:
            data_str = json.dumps(data, ensure_ascii=False, default=str)
            stats["size"] = len(data_str)
        except:
            stats["size"] = len(str(data))
        
        return stats
    
    def _create_data_preview(self, data: Any, max_length: int = 5000) -> str:
        """创建数据预览（不截断，而是智能采样）"""
        if isinstance(data, list):
            if len(data) <= 10:
                # 数据不多，全部显示
                preview = json.dumps(data, ensure_ascii=False, default=str, indent=2)
            else:
                # 显示前3条、中间1条、后3条
                preview_parts = [
                    json.dumps(data[:3], ensure_ascii=False, default=str, indent=2),
                    "\n... (省略中间数据，共{}条记录) ...\n".format(len(data)),
                    json.dumps(data[-3:], ensure_ascii=False, default=str, indent=2)
                ]
                preview = "\n".join(preview_parts)
        
        elif isinstance(data, dict):
            preview = json.dumps(data, ensure_ascii=False, default=str, indent=2)
        else:
            preview = str(data)
        
        # 如果还是太长，截断
        if len(preview) > max_length:
            preview = preview[:max_length] + "\n...(数据预览已截断，完整数据已存储)..."
        
        return preview


    def get_compression_stats(self) -> Dict[str, Any]:
        """获取压缩统计信息
        
        Returns:
            包含压缩统计的字典
        """
        stats = self._compression_stats.copy()
        stats["savings_bytes"] = stats["total_original_size"] - stats["total_compressed_size"]
        stats["savings_percentage"] = stats["compression_ratio"] * 100
        return stats
    
    def reset_compression_stats(self):
        """重置压缩统计信息"""
        self._compression_stats = {
            "total_compressions": 0,
            "total_original_size": 0,
            "total_compressed_size": 0,
            "compression_ratio": 0.0,
            "compressions_by_tool": {},
            "last_reset": datetime.now().isoformat()
        }
    
    def should_compress_data(self, data: Any) -> Tuple[bool, int]:
        """判断数据是否需要压缩
        
        Args:
            data: 要检查的数据
        
        Returns:
            (should_compress, estimated_tokens): 是否需要压缩和估算的token数
        """
        try:
            data_str = json.dumps(data, ensure_ascii=False, default=str)
            estimated_tokens = estimate_tokens(data_str, self.chars_per_token)
            should_compress = estimated_tokens > self.compression_threshold_tokens
            return should_compress, estimated_tokens
        except:
            # 如果无法序列化，保守估计需要压缩
            return True, self.compression_threshold_tokens + 1
    
    def process_large_data(
        self,
        data: Any,
        user_query: str,
        model,
        tool_name: str = "unknown",
        strategy: str = "smart_summary"
    ) -> Dict[str, Any]:
        """处理大数据的主入口
        
        Args:
            data: 要处理的数据
            tool_name: 工具名称
            strategy: 处理策略
                - "smart_summary": 智能摘要（推荐）
                - "chunk": 分块处理
                - "store_and_summary": 存储+摘要
                - "hybrid": 混合策略
        
        Returns:
            处理结果字典，包含摘要、数据ID、统计信息等
        """
        data_str = json.dumps(data, ensure_ascii=False, default=str)
        data_size = len(data_str)
        
        result = {
            "tool_name": tool_name,
            "original_size": data_size,
            "strategy": strategy,
            "processed_at": datetime.now().isoformat()
        }
        
        # 更新压缩统计
        self._compression_stats["total_compressions"] += 1
        self._compression_stats["total_original_size"] += data_size
        
        # 按工具统计
        if tool_name not in self._compression_stats["compressions_by_tool"]:
            self._compression_stats["compressions_by_tool"][tool_name] = {
                "count": 0,
                "total_original_size": 0,
                "total_compressed_size": 0
            }
        
        self._compression_stats["compressions_by_tool"][tool_name]["count"] += 1
        self._compression_stats["compressions_by_tool"][tool_name]["total_original_size"] += data_size
        
        if strategy == "smart_summary" or strategy == "hybrid":
            # 存储完整数据
            data_id = self.store_full_data(data, metadata={"tool_name": tool_name, "user_query": user_query})
            result["data_id"] = data_id
            result["full_data_stored"] = True
            
            # 创建智能摘要
            summary_result = self.create_smart_summary(data, user_query, model)
            result.update(summary_result)
            
            # 更新压缩后大小统计
            compressed_size = len(summary_result.get("summary", ""))
            self._compression_stats["total_compressed_size"] += compressed_size
            self._compression_stats["compressions_by_tool"][tool_name]["total_compressed_size"] += compressed_size
        
        elif strategy == "chunk":
            # 分块处理
            chunks = self.chunk_data(data)
            result["chunks"] = []
            result["chunk_count"] = len(chunks)
            
            # 存储每个块
            for chunk in chunks:
                chunk_id = self.store_full_data(chunk["data"], metadata={
                    "tool_name": tool_name,
                    "chunk_id": chunk["chunk_id"],
                    "chunk_type": chunk["type"]
                })
                chunk["data_id"] = chunk_id
                result["chunks"].append(chunk)
            
            # 更新压缩后大小统计（分块策略不压缩，只是分割）
            self._compression_stats["total_compressed_size"] += data_size
            self._compression_stats["compressions_by_tool"][tool_name]["total_compressed_size"] += data_size
        
        elif strategy == "store_and_summary":
            # 只存储，创建简单摘要
            data_id = self.store_full_data(data, metadata={"tool_name": tool_name})
            result["data_id"] = data_id
            result["full_data_stored"] = True
            result["summary"] = f"数据已存储（ID: {data_id}），大小: {data_size} 字符"
            result["statistics"] = self._extract_statistics(data)
            
            # 更新压缩后大小统计
            compressed_size = len(result["summary"])
            self._compression_stats["total_compressed_size"] += compressed_size
            self._compression_stats["compressions_by_tool"][tool_name]["total_compressed_size"] += compressed_size
        
        # 计算总体压缩比
        if self._compression_stats["total_original_size"] > 0:
            self._compression_stats["compression_ratio"] = (
                1.0 - self._compression_stats["total_compressed_size"] / 
                self._compression_stats["total_original_size"]
            )
        
        return result


def estimate_tokens(text: str, chars_per_token: float = 3.5) -> int:
    """估算文本的token数量（粗略估算）"""
    return int(len(text) / chars_per_token)


def should_compress(data: Any, max_tokens: int = 30000, chars_per_token: float = 3.5) -> bool:
    """判断数据是否需要压缩"""
    try:
        data_str = json.dumps(data, ensure_ascii=False, default=str)
        estimated_tokens = estimate_tokens(data_str, chars_per_token)
        return estimated_tokens > max_tokens
    except:
        # 如果无法序列化，保守估计需要压缩
        return True


class CompressionStats:
    """压缩统计信息类"""
    
    def __init__(self):
        self.total_compressions = 0
        self.total_original_size = 0
        self.total_compressed_size = 0
        self.compression_ratio = 0.0
        self.compressions_by_tool = {}
        self.last_reset = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "total_compressions": self.total_compressions,
            "total_original_size": self.total_original_size,
            "total_compressed_size": self.total_compressed_size,
            "compression_ratio": self.compression_ratio,
            "compressions_by_tool": self.compressions_by_tool,
            "last_reset": self.last_reset,
            "savings_bytes": self.total_original_size - self.total_compressed_size,
            "savings_percentage": self.compression_ratio * 100
        }
    
    def reset(self):
        """重置统计信息"""
        self.total_compressions = 0
        self.total_original_size = 0
        self.total_compressed_size = 0
        self.compression_ratio = 0.0
        self.compressions_by_tool = {}
        self.last_reset = datetime.now().isoformat()
