import dataclasses
import time
from collections.abc import Iterator
from contextlib import contextmanager

import click

from pulsefire import __version__
from pulsefire.colors import Rgb
from pulsefire.device import DeviceError, Dongle
from pulsefire.protocol import (
    MAX_STAGES,
    BatteryEvent,
    ButtonEvent,
    Command,
    DpiStage,
    DpiStageEvent,
    Event,
    LiftOff,
    LinkEvent,
    PollingRate,
    encode_brightness,
    encode_dpi_table,
    encode_live_color,
    encode_sensor,
    parse_event,
    validate_dpi,
)
from pulsefire.settings import SETTINGS_FILE, Settings, load_settings, save_settings

STREAM_INTERVAL = 1 / 15
DEFAULT_STAGE_COLOR = Rgb(0xFF, 0xFF, 0xFF)
STAGE = click.IntRange(1, MAX_STAGES)
PERCENT = click.IntRange(0, 100)


class ColorType(click.ParamType[Rgb]):
    name = "colour"

    def convert(
        self, value: object, param: click.Parameter | None, ctx: click.Context | None
    ) -> Rgb:
        if isinstance(value, Rgb):
            return value
        try:
            return Rgb.parse(str(value))
        except ValueError as error:
            self.fail(str(error), param, ctx)


class DpiType(click.ParamType[int]):
    name = "dpi"

    def convert(
        self, value: object, param: click.Parameter | None, ctx: click.Context | None
    ) -> int:
        try:
            dpi = int(str(value))
            validate_dpi(dpi)
        except ValueError as error:
            self.fail(str(error), param, ctx)
        return dpi


COLOR = ColorType()
DPI = DpiType()


@contextmanager
def open_dongle() -> Iterator[Dongle]:
    try:
        with Dongle.open() as dongle:
            yield dongle
    except DeviceError as error:
        raise click.ClickException(str(error)) from error


def warn_if_asleep(dongle: Dongle) -> None:
    if not dongle.is_mouse_connected():
        click.secho(
            "Mouse is asleep or switched off: the change is queued until it wakes up.",
            fg="yellow",
            err=True,
        )


def send_dpi(dongle: Dongle, settings: Settings) -> None:
    packet = encode_dpi_table(settings.stages, settings.active_stage, settings.polling_rate)
    dongle.execute(Command.DPI_TABLE, packet)


def send_lift_off(dongle: Dongle, settings: Settings) -> None:
    dongle.execute(Command.SENSOR, encode_sensor(settings.lift_off))


def send_brightness(dongle: Dongle, settings: Settings) -> None:
    dongle.execute(Command.BRIGHTNESS, encode_brightness(settings.brightness))


def update_dpi(settings: Settings) -> None:
    with open_dongle() as dongle:
        warn_if_asleep(dongle)
        send_dpi(dongle, settings)
    save_settings(settings)


def stage_index(settings: Settings, stage: int) -> int:
    if stage > len(settings.stages):
        msg = f"stage {stage} does not exist, there are {len(settings.stages)} stages"
        raise click.BadParameter(msg, param_hint="STAGE")
    return stage - 1


def echo_dpi_table(settings: Settings) -> None:
    click.echo("   Stage    DPI  Colour")
    for index, stage in enumerate(settings.stages):
        marker = "*" if index == settings.active_stage else " "
        click.echo(f" {marker} {index + 1:>5}  {stage.dpi:>5}  {stage.color.describe()}")
    click.echo(f"Polling rate: {int(settings.polling_rate)} Hz")


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="pulsefire")
def main() -> None:
    """Configure a HyperX Pulsefire Haste 2 Wireless mouse (USB dongle 03f0:0f98).

    Changes are applied live to the mouse. They are not written to the
    profile that NGENUITY saves on the mouse.

    The mouse cannot report its current settings, so pulsefire remembers the
    last values it sent and shows those. Run "pulsefire apply" to send them
    all again.
    """


@main.command()
def status() -> None:
    """Show whether the mouse is connected and its battery state."""
    with open_dongle() as dongle:
        info = dongle.device_info()
        click.echo(f"Mouse ID:     {info.device_id}")
        if not dongle.is_mouse_connected():
            click.echo("Mouse:        asleep or switched off (move it to wake it up)")
            return
        battery = dongle.battery()
    click.echo("Mouse:        connected")
    click.echo(f"Battery:      {battery.level} % ({battery.charge.label})")
    click.echo(f"Voltage:      {battery.voltage_mv} mV")
    click.echo(f"Temperature:  {battery.temperature_c} °C")


@main.command()
def show() -> None:
    """Show all settings pulsefire last sent to the mouse."""
    settings = load_settings()
    echo_dpi_table(settings)
    click.echo(f"Lift-off:     {settings.lift_off.label}")
    click.echo(f"Brightness:   {settings.brightness} %")
    click.echo(f"Stored in:    {SETTINGS_FILE}")


@main.command()
def apply() -> None:
    """Send all remembered settings to the mouse again."""
    settings = load_settings()
    with open_dongle() as dongle:
        warn_if_asleep(dongle)
        send_dpi(dongle, settings)
        send_lift_off(dongle, settings)
        send_brightness(dongle, settings)
    click.echo("Sent DPI stages, polling rate, lift-off and brightness.")


@main.group(invoke_without_command=True)
@click.pass_context
def dpi(ctx: click.Context) -> None:
    """Show or change the DPI stages (cycled with the button under the wheel).

    Stages are numbered from 1. The active stage is marked with *. If you
    pressed the DPI button since pulsefire last ran, any DPI change also
    switches back to the active stage shown here; "pulsefire watch" keeps
    it in sync.
    """
    if ctx.invoked_subcommand is None:
        echo_dpi_table(load_settings())


@dpi.command("set")
@click.argument("stage", type=STAGE)
@click.argument("value", type=DPI)
def dpi_set(stage: int, value: int) -> None:
    """Set the DPI of STAGE to VALUE (100-26000 in steps of 50).

    Example: pulsefire dpi set 3 1600
    """
    settings = load_settings()
    index = stage_index(settings, stage)
    stages = list(settings.stages)
    stages[index] = dataclasses.replace(stages[index], dpi=value)
    update_dpi(dataclasses.replace(settings, stages=stages))
    click.echo(f"Stage {stage} is now {value} DPI.")


@dpi.command("color")
@click.argument("stage", type=STAGE)
@click.argument("colour", type=COLOR)
def dpi_color(stage: int, colour: Rgb) -> None:
    """Set the indicator colour of STAGE.

    COLOUR is a name (red, green, blue, yellow, cyan, magenta, orange, purple,
    pink, white, off) or a hex value such as #ff8000.
    """
    settings = load_settings()
    index = stage_index(settings, stage)
    stages = list(settings.stages)
    stages[index] = dataclasses.replace(stages[index], color=colour)
    update_dpi(dataclasses.replace(settings, stages=stages))
    click.echo(f"Stage {stage} colour is now {colour.describe()}.")


@dpi.command("select")
@click.argument("stage", type=STAGE)
def dpi_select(stage: int) -> None:
    """Make STAGE the active DPI stage."""
    settings = load_settings()
    index = stage_index(settings, stage)
    update_dpi(dataclasses.replace(settings, active_stage=index))
    click.echo(f"Stage {stage} ({settings.stages[index].dpi} DPI) is now active.")


@dpi.command("add")
@click.argument("value", type=DPI)
@click.argument("colour", type=COLOR, default=DEFAULT_STAGE_COLOR.hex)
def dpi_add(value: int, colour: Rgb) -> None:
    """Add a new last stage with VALUE DPI and an optional COLOUR (default white)."""
    settings = load_settings()
    if len(settings.stages) >= MAX_STAGES:
        msg = f"the mouse supports at most {MAX_STAGES} stages"
        raise click.ClickException(msg)
    stages = [*settings.stages, DpiStage(value, colour)]
    update_dpi(dataclasses.replace(settings, stages=stages))
    click.echo(f"Added stage {len(stages)}: {value} DPI, {colour.describe()}.")


@dpi.command("remove")
@click.argument("stage", type=STAGE)
def dpi_remove(stage: int) -> None:
    """Remove STAGE; the stages after it move up by one."""
    settings = load_settings()
    index = stage_index(settings, stage)
    if len(settings.stages) == 1:
        msg = "the last remaining stage cannot be removed"
        raise click.ClickException(msg)
    stages = [item for position, item in enumerate(settings.stages) if position != index]
    active = settings.active_stage
    if active > index or active == len(stages):
        active -= 1
    update_dpi(dataclasses.replace(settings, stages=stages, active_stage=active))
    click.echo(f"Removed stage {stage}.")


@main.command()
@click.argument("rate", type=click.Choice([str(int(rate)) for rate in PollingRate]), required=False)
def polling(rate: str | None) -> None:
    """Show or set the polling rate in Hz (125, 250, 500 or 1000).

    Example: pulsefire polling 1000
    """
    settings = load_settings()
    if rate is None:
        click.echo(f"Polling rate: {int(settings.polling_rate)} Hz")
        return
    update_dpi(dataclasses.replace(settings, polling_rate=PollingRate(int(rate))))
    click.echo(f"Polling rate is now {rate} Hz.")


@main.command()
@click.argument(
    "distance", type=click.Choice(["low", "high"], case_sensitive=False), required=False
)
def liftoff(distance: str | None) -> None:
    """Show or set the lift-off distance: low (1 mm) or high (2 mm)."""
    settings = load_settings()
    if distance is None:
        click.echo(f"Lift-off: {settings.lift_off.label}")
        return
    settings = dataclasses.replace(settings, lift_off=LiftOff[distance.upper()])
    with open_dongle() as dongle:
        warn_if_asleep(dongle)
        send_lift_off(dongle, settings)
    save_settings(settings)
    click.echo(f"Lift-off is now {settings.lift_off.label}.")


@main.command()
@click.argument("percent", type=PERCENT, required=False)
def brightness(percent: int | None) -> None:
    """Show or set the LED brightness in percent (0 turns the LED off).

    Example: pulsefire brightness 50
    """
    settings = load_settings()
    if percent is None:
        click.echo(f"Brightness: {settings.brightness} %")
        return
    settings = dataclasses.replace(settings, brightness=percent)
    with open_dongle() as dongle:
        warn_if_asleep(dongle)
        send_brightness(dongle, settings)
    save_settings(settings)
    click.echo(f"Brightness is now {percent} %.")


@main.command()
@click.argument("colour", type=COLOR)
@click.option(
    "-s",
    "--seconds",
    type=click.FloatRange(min=0, min_open=True),
    help="Stop after this many seconds instead of waiting for Ctrl+C.",
)
def color(colour: Rgb, seconds: float | None) -> None:
    """Show a solid LED colour until Ctrl+C is pressed.

    The mouse only keeps a live colour while it is being sent, so this command
    keeps running. When it stops, the mouse goes back to its saved lighting
    effect.

    COLOUR is a name (red, green, blue, yellow, cyan, magenta, orange, purple,
    pink, white, off) or a hex value such as #ff8000.

    Example: pulsefire color red --seconds 10
    """
    packet = encode_live_color(colour)
    deadline = None if seconds is None else time.monotonic() + seconds
    hint = f"for {seconds:g} s" if seconds is not None else "press Ctrl+C to stop"
    with open_dongle() as dongle:
        warn_if_asleep(dongle)
        click.echo(f"Showing {colour.describe()}, {hint}.")
        try:
            while deadline is None or time.monotonic() < deadline:
                dongle.send(packet)
                dongle.drain(STREAM_INTERVAL)
        except KeyboardInterrupt:
            pass
    click.echo("Stopped, the mouse is back on its saved lighting effect.")


@main.command()
def watch() -> None:
    """Print mouse events as they happen until Ctrl+C is pressed.

    Shows wake/sleep, DPI button presses with the new stage, and battery
    reports. The active DPI stage pulsefire remembers is updated to match.
    """
    click.echo("Watching the mouse, press Ctrl+C to stop.")
    with open_dongle() as dongle:
        try:
            while True:
                report = dongle.read(timeout=1.0)
                if report is None:
                    continue
                event = parse_event(report)
                if event is not None:
                    click.echo(f"{time.strftime('%H:%M:%S')}  {describe_event(event)}")
                if isinstance(event, DpiStageEvent):
                    remember_active_stage(event)
        except KeyboardInterrupt:
            pass


def describe_event(event: Event) -> str:
    match event:
        case LinkEvent(connected=True):
            return "mouse woke up / connected"
        case LinkEvent():
            return "mouse asleep / disconnected"
        case DpiStageEvent(stage=stage, dpi=value):
            return f"DPI stage {stage + 1}: {value} DPI"
        case ButtonEvent(button=button, pressed=pressed):
            return f"button {button:#04x} {'pressed' if pressed else 'released'}"
        case BatteryEvent(battery=battery):
            return f"battery {battery.level} % ({battery.charge.label})"


def remember_active_stage(event: DpiStageEvent) -> None:
    settings = load_settings()
    if event.stage < len(settings.stages) and event.stage != settings.active_stage:
        save_settings(dataclasses.replace(settings, active_stage=event.stage))
