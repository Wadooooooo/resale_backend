# app/security.py

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession # <--- ИЗМЕНЕНО: Импорт AsyncSession
from sqlalchemy.orm import selectinload

from . import crud, schemas, models
from .database import get_db



# --- Настройки безопасности ---

# Генерируйте этот ключ командой: openssl rand -hex 32
# И храните его в секрете (лучше в переменных окружения)
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
REFRESH_TOKEN_EXPIRE_DAYS = 30 
ACCESS_TOKEN_EXPIRE_MINUTES = 15

# Контекст для хеширования паролей
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Схема аутентификации
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/token")


# --- Функции ---

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверяет, соответствует ли пароль хешу."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Создает хеш из пароля."""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Создает JWT токен."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = schemas.TokenData(username=username)
    except JWTError:
        raise credentials_exception
    
    # Загружаем пользователя вместе с его ролью и всеми правами этой роли
    user = await crud.get_user_by_username(
        db, 
        username=token_data.username
    )
    
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(current_user: models.Users = Depends(get_current_user)):
    if not current_user.active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

def require_permission(permission_code: str):
    """
    Фабрика зависимостей, которая проверяет, есть ли у пользователя нужное право.
    """
    # --- НАЧАЛО ИЗМЕНЕНИЙ ---
    async def _check_permission(user: models.Users = Depends(get_current_active_user)):
        # Теперь user - это объект модели SQLAlchemy, а не Pydantic-схема.
        # Мы должны обращаться к его реальным атрибутам из models.py

        if not user.role or not hasattr(user.role, 'role_permissions'):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions (role is not configured)"
            )

        # Извлекаем коды прав из правильного, вложенного атрибута
        user_permissions = {
            rp.permission.code
            for rp in user.role.role_permissions if rp.permission
        }

        if permission_code not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required permission '{permission_code}' is missing"
            )
    # --- КОНЕЦ ИЗМЕНЕНИЙ ---

    return _check_permission

def user_has_permission(user: models.Users, permission_code: str) -> bool:
    """Проверяет, есть ли у пользователя указанное право."""
    if not user.role or not hasattr(user.role, 'role_permissions'):
        return False

    user_permissions = {
        rp.permission.code
        for rp in user.role.role_permissions if rp.permission
    }
    return permission_code in user_permissions

def require_any_permission(*permission_codes: str):
    """
    Фабрика зависимостей, которая проверяет, есть ли у пользователя ХОТЯ БЫ ОДНО из нужных прав.
    """
    async def _check_any_permission(user: models.Users = Depends(get_current_active_user)):
        if not user.role or not hasattr(user.role, 'role_permissions'):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions (role is not configured)"
            )

        user_permissions = {
            rp.permission.code
            for rp in user.role.role_permissions if rp.permission
        }
        
        # Проверяем, есть ли пересечение между правами пользователя и требуемыми правами
        if not user_permissions.intersection(permission_codes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required any of permissions: {', '.join(permission_codes)}"
            )
    return _check_any_permission

def create_refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt, expire

def decode_token(token: str):
    """Декодирует любой токен и возвращает payload."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None