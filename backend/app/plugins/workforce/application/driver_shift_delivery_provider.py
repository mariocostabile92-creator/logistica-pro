from typing import Protocol

from app.plugins.workforce.domain.driver_shift_distribution import (
    DriverShiftDeliveryChannel,
)


class ShiftDeliveryProvider(Protocol):
    name: str

    def can_send(self, channel: DriverShiftDeliveryChannel) -> bool: ...

    def send(self, *, recipient: dict, message: str, url: str) -> str: ...


class ManualShareProvider:
    name = "manual_share"

    def can_send(self, channel: DriverShiftDeliveryChannel) -> bool:
        return False

    def send(self, *, recipient: dict, message: str, url: str) -> str:
        raise NotImplementedError("La condivisione manuale prepara dati ma non esegue invii.")


MANUAL_SHARE_PROVIDER = ManualShareProvider()
