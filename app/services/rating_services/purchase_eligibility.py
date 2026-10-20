from sqlalchemy import and_, or_

from app.models.enums import FraudStatusEnum, TransactionStatusEnum
from app.models.payment_model import PaymentModel


def successful_transaction_condition():
    """Accept settled provider payments or manually reconciled completed orders."""
    return or_(
        PaymentModel.id.is_(None),
        PaymentModel.transaction_status == TransactionStatusEnum.settlement,
        and_(
            PaymentModel.transaction_status == TransactionStatusEnum.capture,
            PaymentModel.fraud_status == FraudStatusEnum.accept,
        ),
    )
