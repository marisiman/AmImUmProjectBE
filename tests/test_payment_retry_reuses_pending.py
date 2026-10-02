from types import SimpleNamespace

from app.services.payment_services.create_transaction import _existing_pending_payment_response


def test_existing_pending_payment_reuses_stored_midtrans_redirect():
    payment = SimpleNamespace(
        transaction_id="snap-token-old",
        transaction_status="pending",
        payment_response={
            "redirect_url": "https://app.midtrans.com/snap/v4/redirection/snap-token-old",
            "token": "snap-token-old",
        },
    )

    response = _existing_pending_payment_response(payment)

    assert response is not None
    assert response.status_code == 200
    assert response.data.transaction_id == "snap-token-old"
    assert response.data.token == "snap-token-old"
    assert response.data.redirect_url == "https://app.midtrans.com/snap/v4/redirection/snap-token-old"
    assert response.data.transaction_status == "pending"


def test_existing_pending_payment_does_not_reuse_non_pending_status():
    payment = SimpleNamespace(
        transaction_id="snap-token-old",
        transaction_status="settlement",
        payment_response={
            "redirect_url": "https://app.midtrans.com/snap/v4/redirection/snap-token-old",
            "token": "snap-token-old",
        },
    )

    assert _existing_pending_payment_response(payment) is None


def test_existing_pending_payment_requires_redirect_url():
    payment = SimpleNamespace(
        transaction_id="snap-token-old",
        transaction_status="pending",
        payment_response={"token": "snap-token-old"},
    )

    assert _existing_pending_payment_response(payment) is None
