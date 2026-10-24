from datetime import datetime
from importlib import import_module
from types import SimpleNamespace

from fastapi import HTTPException

from app.dtos.user_dtos import UserCreateDto

create_user_service = import_module("app.services.user_services.create_user")


class FakeDB:
    def __init__(self):
        self.committed = 0
        self.refreshed = 0
        self.rolled_back = 0

    def commit(self):
        self.committed += 1

    def refresh(self, _user):
        self.refreshed += 1

    def rollback(self):
        self.rolled_back += 1


def test_register_email_delivery_failure_does_not_disclose_verification_code_in_production(monkeypatch):
    verification_code = "654321"
    payload = UserCreateDto(
        firstname="Test",
        lastname="Account",
        gender="male",
        email="auth-check@example.com",
        phone="+6281234567890",
        password="TestOnly123!",
    )
    user_model = SimpleNamespace(
        id="test-user-id",
        firebase_uid="test-firebase-uid",
        firstname=payload.firstname,
        lastname=payload.lastname,
        gender=payload.gender,
        email=payload.email,
        phone=payload.phone,
        address=None,
        photo_url=None,
        role="customer",
        is_active=False,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )
    db = FakeDB()

    monkeypatch.setenv("APP_DEVELOPMENT", "false")
    monkeypatch.setattr(create_user_service, "validate_user_data", lambda _user: None)
    monkeypatch.setattr(
        create_user_service,
        "create_firebase_user_account",
        lambda _user: SimpleNamespace(uid="test-firebase-uid", email=payload.email),
    )
    monkeypatch.setattr(
        create_user_service,
        "save_user_to_db",
        lambda _db, _user: (user_model, verification_code),
    )

    def fail_email_delivery(*_args, **_kwargs):
        raise HTTPException(
            status_code=502,
            detail="Layanan email sementara belum tersedia. Silakan coba beberapa saat lagi.",
        )

    monkeypatch.setattr(create_user_service, "send_verification_email", fail_email_delivery)
    monkeypatch.setattr(create_user_service, "delete_unverified_users", lambda _db: None)

    response = create_user_service.create_user(db, payload).unwrap()

    assert response.status_code == 201
    assert verification_code not in response.message
    assert response.data.verification_code is None
    assert response.data.is_active is False
    assert "verification" in response.message.lower()
    assert "could not be sent" in response.message.lower()
