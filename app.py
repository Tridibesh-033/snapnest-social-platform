from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from imagekitio import ImageKit
from imagekitio.models.UploadFileRequestOptions import UploadFileRequestOptions
import tempfile
import shutil
import os
import uuid

from db import Post, create_db_and_tables, get_async_session, User, Like, Comment
from users import auth_backend, current_active_user, fastapi_users
from schemas import UserCreate, UserRead, UserUpdate


load_dotenv()

# ImageKit setup
imagekit = ImageKit(
    public_key=os.getenv("IMAGEKIT_PUBLIC_KEY"),
    private_key=os.getenv("IMAGEKIT_PRIVATE_KEY"),
    url_endpoint=os.getenv("IMAGEKIT_URL"),
)

# Lifespan (DB init)
@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db_and_tables()
    yield

app = FastAPI(lifespan=lifespan)

# Auth routers
app.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"]
)
app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"]
)
app.include_router(
    fastapi_users.get_reset_password_router(),
    prefix="/auth",
    tags=["auth"]
)
app.include_router(
    fastapi_users.get_verify_router(UserRead),
    prefix="/auth",
    tags=["auth"]
)
app.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"]
)


@app.post("/upload", tags=["posts"])
async def upload_file(
    file: UploadFile = File(...),
    caption: str = Form(""),
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    temp_path = None

    try:
        # validate file type
        if not file.content_type.startswith(("image/", "video/")):
            raise HTTPException(status_code=400, detail="Only image or video allowed")

        suffix = os.path.splitext(file.filename)[1]

        # save temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(file.file, tmp)
            temp_path = tmp.name

        options = UploadFileRequestOptions(
            folder="/fastapi_uploads",
            use_unique_file_name=True,
        )

        # Upload to ImageKit
        with open(temp_path, "rb") as f:
            uploaded = imagekit.upload_file(
                file=f,
                file_name=file.filename,
                options=options,
            )

        post = Post(
            caption=caption,
            url=uploaded.url,
            file_type="video" if file.content_type.startswith("video") else "image",
            file_name=uploaded.name,
            user_id=user.id,
        )

        session.add(post)
        await session.commit()
        await session.refresh(post)

        return {
            "id": str(post.id),
            "caption": post.caption,
            "url": post.url,
            "file_type": post.file_type,
            "file_name": post.file_name,
            "created_at": post.created_at.isoformat(),
        }

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Upload failed")

    finally:
        await file.close()
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

# api endpoints
@app.get("/home", tags=["posts"])
async def get_home(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    result = await session.execute(
        select(Post)
        .options(selectinload(Post.user))
        .order_by(Post.created_at.desc())
    )

    posts = result.scalars().all()

    posts_data = []

    for post in posts:
        # like count
        like_count = await session.scalar(
            select(func.count(Like.id))
            .where(Like.post_id == post.id)
        )

        # USER LIKED OR NOT
        user_liked = await session.scalar(
            select(func.count(Like.id))
            .where(
                Like.post_id == post.id,
                Like.user_id == user.id
            )
        )

        # comments
        comments_result = await session.execute(
            select(Comment)
            .where(Comment.post_id == post.id)
            .options(selectinload(Comment.user))
            .order_by(Comment.created_at)
        )

        comments = comments_result.scalars().all()

        posts_data.append(
            {
                "id": str(post.id),
                "user_id": str(post.user_id),
                "username": post.user.username, 
                "caption": post.caption,
                "url": post.url,
                "file_type": post.file_type,
                "file_name": post.file_name,
                "created_at": post.created_at.isoformat(),

                # like system
                "likes": like_count,
                "liked": user_liked > 0,

                # comments system
                "comments": [
                    {
                        "username": c.user.username,
                        "text": c.text,
                        "created_at": c.created_at.isoformat(),
                    }
                    for c in comments
                ],

                # owner_check
                "is_owner": post.user_id == user.id,
            }
        )

    return {"posts": posts_data}


@app.post("/posts/{post_id}/like", tags=["likes"])
async def like_post(
    post_id: str,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    post_uuid = uuid.UUID(post_id)

    result = await session.execute(
        select(Like).where(
            Like.post_id == post_uuid,
            Like.user_id == user.id
        )
    )
    existing_like = result.scalars().first()

    if existing_like:
        await session.delete(existing_like)
        await session.commit()
        return {"liked": False}

    new_like = Like(user_id=user.id, post_id=post_uuid)
    session.add(new_like)
    await session.commit()
    return {"liked": True}


@app.post("/posts/{post_id}/comment", tags=["comments"])
async def add_comment(
    post_id: str,
    text: str = Form(...),
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    comment = Comment(
        user_id=user.id,
        post_id=uuid.UUID(post_id),
        text=text,
    )

    session.add(comment)
    await session.commit()
    return {"success": True}


@app.delete("/posts/{post_id}", tags=["posts"])
async def delete_post(
    post_id: str,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    try:
        post_uuid = uuid.UUID(post_id)

        result = await session.execute(
            select(Post).where(Post.id == post_uuid)
        )
        post = result.scalars().first()

        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        if post.user_id != user.id:
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to delete this post"
            )

        await session.delete(post)
        await session.commit()

        return {"success": True, "message": "Post deleted successfully"}

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Delete failed")
