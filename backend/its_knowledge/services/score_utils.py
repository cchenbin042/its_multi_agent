# backend/its_knowledge/services/score_utils.py
def normalize_vector_score(distance: float) -> float:
    """
    将L2距离转换为相似度分数（范围0-1，越大越好）

    Args:
        distance: L2距离值

    Returns:
        float: 相似度分数，范围[0, 1]
    """
    if distance < 0:
        distance = 0
    return 1.0 / (1.0 + distance)