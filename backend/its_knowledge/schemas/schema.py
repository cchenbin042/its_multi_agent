from pydantic import BaseModel
from typing import Optional


class UploadResponse(BaseModel):
    """
     文件上传的响应数据模型
    """
    status:str  # 响应状态
    message:str # 响应的消息内容
    file_name:str # 上传的文件名
    chunks_added:int # 上传文档切分之后的文档块数量

class QueryResponse(BaseModel):
    """
     查询的响应数据模型
    """
    question:str # 用户问题
    answer:str # 回答内容

class QueryRequest(BaseModel):
    """
     查询的请求数据模型
    """
    question: str  # 用户问题
    session_id: Optional[str] = None  # 可选Session ID，用于多轮对话


class FeedbackRequest(BaseModel):
    """
     用户反馈的请求数据模型
    """
    message_id: str
    session_id: Optional[str] = None
    question: str
    rating: str              # "positive" | "negative"
    comment: Optional[str] = None
    sources: Optional[list] = None


class DocumentListItem(BaseModel):
    id: str
    title: str
    path: str


class DocumentPreviewResponse(BaseModel):
    title: str
    content_preview: str


class ErrorResponse(BaseModel):
    error: str
    detail: str
    request_id: str = ""
    timestamp: str = ""
