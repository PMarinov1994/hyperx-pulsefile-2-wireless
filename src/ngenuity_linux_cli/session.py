from dataclasses import dataclass, replace
from pathlib import Path

from ngenuity_linux_cli.device import DeviceError, NoReplyError, Tracer, UniversalDevice
from ngenuity_linux_cli.devices import (
    Category,
    Interface,
    Model,
    find_model,
    list_interfaces,
    match_model,
)
from ngenuity_linux_cli.protocol import DeviceInfo


@dataclass(frozen=True)
class Candidate:
    interface: Interface
    model: Model
    info: DeviceInfo | None
    overridden: Model | None = None

    @property
    def label(self) -> str:
        return f"{self.model.name} ({self.model.status_label}) at {self.interface.path}"


def identify(interface: Interface, trace: Tracer | None) -> Candidate:
    try:
        with UniversalDevice.open(interface.path, trace) as device:
            info = device.device_info()
    except NoReplyError:
        return Candidate(interface, match_model({interface.product_id}, Category.UNKNOWN), None)
    ids = {interface.product_id, *info.product_ids}
    return Candidate(interface, match_model(ids, Category.from_byte(info.category)), info)


def detect(trace: Tracer | None) -> list[Candidate]:
    return [identify(interface, trace) for interface in list_interfaces()]


def select_candidates(candidates: list[Candidate], spec: str | None) -> list[Candidate]:
    if spec is None:
        return candidates
    if spec.startswith("/dev/"):
        chosen = [item for item in candidates if item.interface.path == Path(spec)]
        if not chosen:
            msg = f"{spec} is not a HyperX device that ngenuity can talk to"
            raise DeviceError(msg)
        return chosen
    model = find_model(spec)
    if model is None:
        msg = f"unknown device {spec!r}, see 'ngenuity devices --all' for the names"
        raise DeviceError(msg)
    matching = [item for item in candidates if item.model.key == model.key]
    if matching:
        return matching
    unidentified = [item for item in candidates if not item.model.product_ids]
    same_category = [item for item in candidates if item.model.category is model.category]
    pool = [item for item in unidentified if item in same_category] or unidentified or same_category
    if not pool:
        msg = f"no connected device can be used as {model.name}"
        raise DeviceError(msg)
    return [replace(item, model=model, overridden=item.model) for item in pool]
