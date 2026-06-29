from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ── User schemas ──────────────────────────────────────────


class UserRegister(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=50)


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse | None = None
    message: str | None = None


class TokenData(BaseModel):
    username: str | None = None


# ── Post schemas ──────────────────────────────────────────


class PostUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=100)
    content: str | None = None


class PostImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    url: str


class PostResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content: str
    user: UserResponse
    created_at: datetime
    updated_at: datetime
    images: list[PostImageResponse] = []
    comment_count: int = 0


class PostListResponse(BaseModel):
    posts: list[PostResponse]
    total: int
    page: int
    page_size: int


# ── Comment schemas ───────────────────────────────────────


class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=1000, description="评论内容")


class CommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    content: str
    user: UserResponse
    created_at: datetime
