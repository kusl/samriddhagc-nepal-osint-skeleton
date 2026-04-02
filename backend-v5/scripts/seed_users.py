#!/usr/bin/env python3
"""
Seed initial users for the Nepal OSINT Platform.

Creates three default users:
- dev@narada.local (dev role) - Full access
- analyst@narada.local (analyst role) - Feedback and entity management
- consumer@narada.local (consumer role) - Read-only access

Usage:
    cd backend-v5
    python scripts/seed_users.py
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.user import User, UserRole
from app.services.auth_service import AuthService


# Default users to create
# Using @narada.dev domain (.dev is a valid TLD)
DEFAULT_USERS = [
    {
        "email": "dev@narada.dev",
        "password": "devpassword123",
        "full_name": "Dev User",
        "role": UserRole.DEV,
    },
    {
        "email": "analyst@narada.dev",
        "password": "analystpassword123",
        "full_name": "Analyst User",
        "role": UserRole.ANALYST,
    },
    {
        "email": "consumer@narada.dev",
        "password": "consumerpassword123",
        "full_name": "Consumer User",
        "role": UserRole.CONSUMER,
    },
]


async def seed_users():
    """Create default users if they don't exist."""
    print("=" * 60)
    print("Seeding Users for Nepal OSINT Platform")
    print("=" * 60)

    async with AsyncSessionLocal() as db:
        for user_data in DEFAULT_USERS:
            # Check if user exists
            result = await db.execute(
                select(User).where(User.email == user_data["email"])
            )
            existing = result.scalar_one_or_none()

            if existing:
                print(f"  [SKIP] {user_data['email']} already exists (role: {existing.role.value})")
                continue

            # Create user
            user = User(
                email=user_data["email"],
                password_hash=AuthService.hash_password(user_data["password"]),
                full_name=user_data["full_name"],
                role=user_data["role"],
            )
            db.add(user)
            await db.commit()
            print(f"  [CREATE] {user_data['email']} (role: {user_data['role'].value})")

    print("\n" + "=" * 60)
    print("Default Credentials:")
    print("=" * 60)
    for user_data in DEFAULT_USERS:
        print(f"  {user_data['role'].value.upper():8} | {user_data['email']:25} | {user_data['password']}")
    print("=" * 60)
    print("\nIMPORTANT: Change these passwords in production!")
    print()


if __name__ == "__main__":
    asyncio.run(seed_users())
