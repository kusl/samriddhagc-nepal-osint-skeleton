#!/usr/bin/env python3
"""Create demo analyst user for testing."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import AsyncSessionLocal
from app.services.auth_service import AuthService
from app.schemas.auth import UserCreate
from app.models.user import UserRole


async def main():
    async with AsyncSessionLocal() as db:
        auth_service = AuthService(db)

        # Check if demo analyst already exists
        existing = await auth_service.get_user_by_email("demo@analyst.narada.dev")
        if existing:
            print("✅ Demo analyst already exists")
            print(f"   Email: demo@analyst.narada.dev")
            print(f"   Password: demo123")
            return

        # Create demo analyst
        user_data = UserCreate(
            email="demo@analyst.narada.dev",
            password="demo123",
            full_name="Demo Analyst",
            username="demo_analyst",
            auth_provider="local",
            role=UserRole.ANALYST,
        )

        user = await auth_service.create_user(user_data)

        print("✅ Demo analyst created successfully!")
        print()
        print(f"   Email: demo@analyst.narada.dev")
        print(f"   Password: demo123")
        print(f"   Role: ANALYST")
        print()


if __name__ == "__main__":
    asyncio.run(main())
