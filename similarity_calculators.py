#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
电影相似度计算策略模块

该模块实现了不同维度的电影相似度计算策略，遵循策略模式设计模式。
每个策略类负责计算特定维度的相似度（如导演、演员、类型等）。
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Set, Tuple, Any, Optional

# 配置日志
logger = logging.getLogger(__name__)

class SimilarityCalculator(ABC):
    """相似度计算器抽象基类
    
    定义电影相似度计算的接口，所有具体相似度计算策略都实现此接口
    """
    
    @abstractmethod
    def calculate_similarity(self, target_movie: Dict[str, Any], candidate_movie: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """计算两部电影之间的相似度
        
        Args:
            target_movie: 目标电影信息字典
            candidate_movie: 候选电影信息字典
            
        Returns:
            相似度结果字典，包含相似度类型和原因；如果不相似则返回None
        """
        pass
    
    @property
    @abstractmethod
    def priority(self) -> int:
        """获取相似度类型的优先级，数字越小优先级越高"""
        pass


class DirectorSimilarityCalculator(SimilarityCalculator):
    """导演相似度计算策略"""
    
    def calculate_similarity(self, target_movie: Dict[str, Any], candidate_movie: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """计算导演相似度
        
        比较两部电影导演ID是否存在交集，而不是直接比较导演名称
        
        Args:
            target_movie: 目标电影信息字典，包含director_ids和directors_with_ids
            candidate_movie: 候选电影信息字典，包含directors_with_ids
            
        Returns:
            相似度结果字典，包含相似度类型和原因；如果导演不相似则返回None
        """
        # 尝试从不同位置获取导演信息，提高匹配成功率
        target_director_ids_raw = target_movie.get("director_ids", [])
        target_directors_with_ids = target_movie.get("directors_with_ids", {})
        
        candidate_director_ids_raw = candidate_movie.get("director_ids", [])
        candidate_directors_with_ids = candidate_movie.get("directors_with_ids", {})
        
        # 清理并收集所有目标电影的导演ID
        target_director_ids = set()
        for d_id in target_director_ids_raw:
            if d_id and d_id.strip():  # 确保ID不是空字符串
                target_director_ids.add(d_id.strip())
        
        # 如果目标电影或候选电影缺少导演信息，则不能判断导演相似度
        if (not target_director_ids and not target_directors_with_ids) or not candidate_directors_with_ids:
            logger.debug(f"缺少导演信息: 目标电影={target_movie.get('id')}, 候选电影={candidate_movie.get('id')}")
            return None
        
        # 首先尝试基于ID的匹配
        common_director_ids = target_director_ids.intersection(set(candidate_directors_with_ids.keys()))
        
        # 如果没有找到共同ID，尝试基于名称的匹配（备选方案）
        if not common_director_ids and target_directors_with_ids and candidate_director_ids_raw:
            target_director_names = {name.lower() for name in target_directors_with_ids.values() if name}
            name_matched_ids = set()
            
            for d_id in candidate_director_ids_raw:
                if d_id in candidate_directors_with_ids:
                    name = candidate_directors_with_ids[d_id]
                    if name and name.lower() in target_director_names:
                        name_matched_ids.add(d_id)
            
            # 使用名称匹配结果
            if name_matched_ids:
                common_director_ids = name_matched_ids
        
        # 只有在确实有共同导演时，才返回相似度信息
        if common_director_ids:
            # 获取共同导演的名称
            common_director_names = []
            for d_id in common_director_ids:
                if d_id in candidate_directors_with_ids:
                    director_name = candidate_directors_with_ids[d_id]
                    if director_name and director_name.strip():  # 确保名称不是空字符串
                        common_director_names.append(director_name.strip())
            
            # 确保有有效的导演名称
            if common_director_names:
                logger.info(f"找到相同导演: {common_director_names} - 目标电影={target_movie.get('id')}, 候选电影={candidate_movie.get('id')}")
                return {
                    "type": "director",
                    "reason": f"相同导演: {', '.join(common_director_names)}",
                    "common_ids": list(common_director_ids),
                    "common_names": common_director_names
                }
        
        return None
    
    @property
    def priority(self) -> int:
        """导演相似度优先级最高"""
        return 1


class ActorSimilarityCalculator(SimilarityCalculator):
    """演员相似度计算策略"""
    
    def calculate_similarity(self, target_movie: Dict[str, Any], candidate_movie: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """计算演员相似度
        
        比较两部电影演员ID是否存在交集，而不是直接比较演员名称
        
        Args:
            target_movie: 目标电影信息字典，包含actor_ids
            candidate_movie: 候选电影信息字典，包含actors_with_ids
            
        Returns:
            相似度结果字典，包含相似度类型和原因；如果演员不相似则返回None
        """
        # 获取并清理目标电影的演员ID列表，确保所有ID都是有效的
        target_actor_ids_raw = target_movie.get("actor_ids", [])
        target_actor_ids = set()
        for a_id in target_actor_ids_raw:
            if a_id and a_id.strip():  # 确保ID不是空字符串
                target_actor_ids.add(a_id.strip())
        
        # 获取候选电影的演员ID到名称的映射
        candidate_actors_with_ids = candidate_movie.get("actors_with_ids", {})
        
        # 如果任一电影缺少演员信息，则不能判断演员相似度
        if not target_actor_ids or not candidate_actors_with_ids:
            return None
        
        # 查找两部电影的共同演员
        common_actor_ids = target_actor_ids.intersection(set(candidate_actors_with_ids.keys()))
        
        if common_actor_ids:
            # 获取共同演员的名称
            common_actor_names = []
            for a_id in common_actor_ids:
                if a_id in candidate_actors_with_ids:
                    actor_name = candidate_actors_with_ids[a_id]
                    if actor_name and actor_name.strip():  # 确保名称不是空字符串
                        common_actor_names.append(actor_name.strip())
            
            # 确保有有效的演员名称
            if common_actor_names:
                # 只显示前两个名称
                display_names = common_actor_names[:2]
                
                # 如果有超过2个共同演员，添加省略号
                reason_text = f"演员阵容相似: {', '.join(display_names)}"
                if len(common_actor_names) > 2:
                    reason_text += " 等"
                    
                return {
                    "type": "actors",
                    "reason": reason_text,
                    "common_ids": list(common_actor_ids),
                    "common_names": common_actor_names
                }
        
        return None
    
    @property
    def priority(self) -> int:
        """演员相似度优先级第二"""
        return 2


class GenreSimilarityCalculator(SimilarityCalculator):
    """电影类型相似度计算策略"""
    
    def calculate_similarity(self, target_movie: Dict[str, Any], candidate_movie: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """计算电影类型相似度
        
        Args:
            target_movie: 目标电影信息字典，包含genres
            candidate_movie: 候选电影信息字典，包含genres
            
        Returns:
            相似度结果字典，包含相似度类型和原因；如果类型不相似则返回None
        """
        target_genres = set(target_movie.get("genres", []))
        candidate_genres = set(candidate_movie.get("genres", []))
        
        # 如果任一电影缺少类型信息，则不能判断类型相似度
        if not target_genres or not candidate_genres:
            return None
        
        # 查找两部电影的共同类型
        common_genres = target_genres.intersection(candidate_genres)
        
        if common_genres:
            return {
                "type": "genres",
                "reason": f"类型相似: {', '.join(common_genres)}",
                "common_genres": list(common_genres)
            }
        
        return None
    
    @property
    def priority(self) -> int:
        """类型相似度优先级第三"""
        return 3


class YearSimilarityCalculator(SimilarityCalculator):
    """上映年份相似度计算策略"""
    
    def __init__(self, max_year_diff: int = 2):
        """初始化年份相似度计算器
        
        Args:
            max_year_diff: 最大年份差异，超过此差异则认为不相似
        """
        self.max_year_diff = max_year_diff
    
    def calculate_similarity(self, target_movie: Dict[str, Any], candidate_movie: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """计算上映年份相似度
        
        Args:
            target_movie: 目标电影信息字典，包含release_year
            candidate_movie: 候选电影信息字典，包含release_year
            
        Returns:
            相似度结果字典，包含相似度类型和原因；如果年份不相似则返回None
        """
        target_year = target_movie.get("release_year")
        candidate_year = candidate_movie.get("release_year")
        
        # 如果任一电影缺少年份信息，则不能判断年份相似度
        if not target_year or not candidate_year:
            return None
        
        try:
            target_year = int(target_year)
            candidate_year = int(candidate_year)
            
            year_diff = abs(target_year - candidate_year)
            
            if year_diff <= self.max_year_diff:
                if year_diff == 0:
                    return {
                        "type": "year",
                        "reason": f"同年({target_year})上映",
                        "year_diff": 0
                    }
                else:
                    return {
                        "type": "year",
                        "reason": f"相近年份上映({candidate_year})",
                        "year_diff": year_diff
                    }
        except (ValueError, TypeError):
            logger.warning(f"年份转换失败: target_year={target_year}, candidate_year={candidate_year}")
        
        return None
    
    @property
    def priority(self) -> int:
        """年份相似度优先级最低"""
        return 4


class RatingSimilarityCalculator(SimilarityCalculator):
    """评分相似度计算策略（兜底策略）"""
    
    def calculate_similarity(self, target_movie: Dict[str, Any], candidate_movie: Dict[str, Any]) -> Dict[str, Any]:
        """计算评分相似度
        
        此计算器总是返回结果，作为兜底推荐理由
        
        Args:
            target_movie: 目标电影信息字典
            candidate_movie: 候选电影信息字典，包含score
            
        Returns:
            相似度结果字典，包含相似度类型和原因
        """
        score = candidate_movie.get("score", 0)
        
        return {
            "type": "rating",
            "reason": f"好评佳片 (评分{score:.1f}分)",
            "score": score
        }
    
    @property
    def priority(self) -> int:
        """评分相似度优先级最低，仅作为兜底"""
        return 999


class SimilarityCalculatorFactory:
    """相似度计算器工厂类
    
    负责创建和管理各种相似度计算策略
    """
    
    def __init__(self):
        """初始化相似度计算器工厂"""
        self.calculators = [
            DirectorSimilarityCalculator(),
            ActorSimilarityCalculator(),
            GenreSimilarityCalculator(),
            YearSimilarityCalculator(),
            RatingSimilarityCalculator()
        ]
        
        # 按优先级排序
        self.calculators.sort(key=lambda c: c.priority)
    
    def get_best_similarity_reason(self, target_movie: Dict[str, Any], candidate_movie: Dict[str, Any]) -> Dict[str, Any]:
        """获取最佳相似度原因
        
        按优先级依次计算各维度相似度，返回优先级最高的相似度原因
        
        Args:
            target_movie: 目标电影信息字典
            candidate_movie: 候选电影信息字典
            
        Returns:
            最佳相似度原因字典
        """
        for calculator in self.calculators:
            result = calculator.calculate_similarity(target_movie, candidate_movie)
            if result:
                return result
        
        # 如果所有计算器都返回None（不应该发生，因为RatingSimilarityCalculator总是返回结果）
        # 兜底返回一个默认原因
        return {
            "type": "default",
            "reason": "系统推荐"
        } 