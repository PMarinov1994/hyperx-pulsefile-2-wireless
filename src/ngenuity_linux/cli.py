import dataclasses
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager

import click

from ngenuity_linux import __version__
from ngenuity_linux import lighting as effects
from ngenuity_linux.buttons import (
    ACTIONS,
    Action,
    Assignment,
    Button,
    is_default,
    parse_action,
)
from ngenuity_linux.colors import Rgb
from ngenuity_linux.device import DeviceError, NoReplyError, Tracer, UniversalDevice
from ngenuity_linux.devices import MODELS, Effect, Model
from ngenuity_linux.protocol import (
    ACK_COMMAND_OFFSET,
    ACK_REPORT,
    ACK_STATUS_OFFSET,
    ACK_SUB,
    BATTERY_ALERT_MAX,
    BATTERY_ALERT_MIN,
    DPI_STEP,
    LIVE_SLOT,
    MAX_STAGES,
    SAVED_SLOT,
    BatteryEvent,
    ButtonEvent,
    DpiStage,
    DpiStageEvent,
    DpiTable,
    Event,
    LiftOff,
    LightingEffect,
    LightingMode,
    LinkEvent,
    PollingRate,
    SensorSettings,
    brightness_to_percent,
    encode_live_color,
    parse_event,
    percent_to_brightness,
)
from ngenuity_linux.session import Candidate, detect, select_candidates

STREAM_INTERVAL = 1 / 15
MIN_SHOWN_BYTES = 4
DEFAULT_STAGE_COLOR = Rgb(0xFF, 0xFF, 0xFF)
STAGE = click.IntRange(1, MAX_STAGES)
PERCENT = click.IntRange(0, 100)
BUTTON = click.Choice([button.label for button in Button], case_sensitive=False)


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


COLOR = ColorType()
DPI = click.IntRange(min=DPI_STEP)

save_option = click.option(
    "--save",
    is_flag=True,
    help="Also store the change in the device's onboard memory so it survives a power cycle.",
)
speed_option = click.option(
    "-s",
    "--speed",
    type=PERCENT,
    default=effects.DEFAULT_SPEED,
    show_default=True,
    help="Effect speed in percent, like NGENUITY's speed slider.",
)
saved_option = click.option(
    "--saved",
    is_flag=True,
    help="Show the profile stored in the device's onboard memory instead of the live settings.",
)


@dataclasses.dataclass
class Options:
    verbose: bool = False
    device: str | None = None
    selected: Candidate | None = None
    warned: bool = False


def describe_packet(packet: bytes) -> str:
    length = max(len(packet.rstrip(b"\x00")), MIN_SHOWN_BYTES)
    text = packet[:length].hex(" ") + (" …" if length < len(packet) else "")
    if packet[0] == ACK_REPORT and packet[1] == ACK_SUB and len(packet) > ACK_STATUS_OFFSET:
        command = packet[ACK_COMMAND_OFFSET : ACK_COMMAND_OFFSET + 2].hex(" ")
        sender = packet[2:ACK_COMMAND_OFFSET].hex()
        status = packet[ACK_STATUS_OFFSET]
        text += f"  (ACK {command}, status {status:02x}, from {sender})"
    return text


def echo_packet(direction: str, packet: bytes) -> None:
    now = time.time()
    stamp = f"{time.strftime('%H:%M:%S', time.localtime(now))}.{int(now * 1000) % 1000:03d}"
    arrow = "->" if direction == "send" else "<-"
    click.secho(f"{stamp} {arrow} {describe_packet(packet)}", fg="cyan", err=True)


def options() -> Options:
    found = click.get_current_context().find_object(Options)
    return found if found is not None else Options()


def packet_tracer() -> Tracer | None:
    return echo_packet if options().verbose else None


def is_interactive() -> bool:
    return sys.stdin.isatty()


def prompt_candidate(candidates: list[Candidate]) -> Candidate:
    if not is_interactive():
        names = "\n".join(f"  {item.label}" for item in candidates)
        msg = f"several devices are connected, choose one with --device:\n{names}"
        raise click.ClickException(msg)
    click.echo("Several devices are connected:")
    for number, item in enumerate(candidates, start=1):
        click.echo(f"  {number}) {item.label}")
    number = click.prompt("Device", type=click.IntRange(1, len(candidates)), default=1)
    return candidates[number - 1]


def selected_candidate() -> Candidate:
    current = options()
    if current.selected is not None:
        return current.selected
    try:
        candidates = select_candidates(detect(packet_tracer()), current.device)
    except DeviceError as error:
        raise click.ClickException(str(error)) from error
    if not candidates:
        msg = "no HyperX device found that ngenuity can talk to (see 'ngenuity devices')"
        raise click.ClickException(msg)
    current.selected = candidates[0] if len(candidates) == 1 else prompt_candidate(candidates)
    overridden = current.selected.overridden
    if overridden is not None and overridden.product_ids:
        click.secho(
            f"Note: using it as {current.selected.model.name} although it was detected as "
            f"{overridden.name}.",
            fg="yellow",
            err=True,
        )
    return current.selected


def current_model() -> Model:
    return selected_candidate().model


def warn_untested(model: Model) -> None:
    current = options()
    if model.tested or current.warned:
        return
    current.warned = True
    click.secho(
        f"Note: {model.name} support is untested; it is built from NGENUITY's decompiled "
        "code. Please report whether it works (see 'Testing untested hardware' in the README).",
        fg="yellow",
        err=True,
    )


def require(condition: object, message: str) -> None:
    if not condition:
        msg = f"{current_model().name}: {message}"
        raise click.ClickException(msg)


@contextmanager
def open_dongle() -> Iterator[UniversalDevice]:
    candidate = selected_candidate()
    try:
        with UniversalDevice.open(candidate.interface.path, packet_tracer()) as device:
            yield device
    except DeviceError as error:
        raise click.ClickException(str(error)) from error


@contextmanager
def open_mouse() -> Iterator[UniversalDevice]:
    model = current_model()
    require(model.configurable, "this device type is detected but not supported yet")
    warn_untested(model)
    with open_dongle() as device:
        if not device.is_awake():
            msg = "The device is asleep or switched off. Move it and try again."
            raise click.ClickException(msg)
        yield device


def require_lighting() -> Model:
    model = current_model()
    require(model.has_lighting, "this model has no RGB lighting")
    return model


def require_effect(effect: Effect) -> Model:
    model = require_lighting()
    require(effect in model.effects, f"NGENUITY does not offer the {effect} effect for it")
    return model


def check_dpi(value: int) -> None:
    model = current_model()
    valid = model.dpi_min <= value <= model.dpi_max and value % model.dpi_step == 0
    require(
        valid,
        f"DPI must be {model.dpi_min}-{model.dpi_max} in steps of {model.dpi_step}, got {value}",
    )


def check_button(target: Button) -> None:
    require(target in current_model().buttons, f"it has no {target.label} button")


def target_slots(*, save: bool) -> tuple[int, ...]:
    return (LIVE_SLOT, SAVED_SLOT) if save else (LIVE_SLOT,)


def slot_name(slot: int) -> str:
    return "saved profile" if slot == SAVED_SLOT else "live settings"


def warn_mismatch(what: str, slot: int, expected: object, actual: object) -> None:
    if expected != actual:
        click.secho(
            f"Warning: the mouse reports a different {what} in its {slot_name(slot)}.",
            fg="yellow",
            err=True,
        )


def saved_note(*, save: bool) -> str:
    return " Saved to the device's memory." if save else ""


def write_dpi_table(dongle: UniversalDevice, table: DpiTable, *, save: bool) -> None:
    for slot in target_slots(save=save):
        dongle.set_dpi_table(table, slot)
        warn_mismatch("DPI table", slot, table, dongle.dpi_table(slot))


def write_sensor(dongle: UniversalDevice, settings: SensorSettings, *, save: bool) -> None:
    for slot in target_slots(save=save):
        dongle.set_sensor(settings, slot)
        warn_mismatch("lift-off distance", slot, settings, dongle.sensor(slot))


def write_brightness(dongle: UniversalDevice, percent: int, *, save: bool) -> None:
    for slot in target_slots(save=save):
        dongle.set_brightness(percent, slot)
        warn_mismatch("brightness", slot, percent_to_brightness(percent), dongle.brightness(slot))


def write_assignments(
    dongle: UniversalDevice, assignments: list[Assignment], *, save: bool
) -> None:
    for slot in target_slots(save=save):
        dongle.set_key_assignments(assignments, slot)
        warn_mismatch(
            "button assignment", slot, set(assignments), set(dongle.key_assignments(slot))
        )


def parse_button_action(text: str | None) -> Action | None:
    if text is None:
        msg = "missing ACTION, e.g. 'ngenuity button back forward' or '... back default'"
        raise click.UsageError(msg)
    if text.strip().lower() == "default":
        return None
    try:
        return parse_action(text)
    except ValueError as error:
        raise click.BadParameter(str(error), param_hint="ACTION") from error


def stage_index(table: DpiTable, stage: int) -> int:
    if stage > len(table.stages):
        msg = f"stage {stage} does not exist, there are {len(table.stages)} stages"
        raise click.BadParameter(msg, param_hint="STAGE")
    return stage - 1


def echo_dpi_table(table: DpiTable) -> None:
    click.echo("   Stage    DPI  Colour")
    for index, stage in enumerate(table.stages):
        marker = "*" if index == table.active_stage else " "
        click.echo(f" {marker} {index + 1:>5}  {stage.dpi:>5}  {stage.color.describe()}")
    click.echo(f"Polling rate: {int(table.polling_rate)} Hz")


def echo_assignments(assignments: list[Assignment]) -> None:
    remapped = [assignment for assignment in assignments if not is_default(assignment)]
    if not remapped:
        click.echo("Buttons:      all on their default actions")
        return
    click.echo("Buttons:")
    for assignment in remapped:
        click.echo(f"  {assignment.button_label:<8} -> {assignment.action.label}")


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


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="ngenuity")
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Print every packet sent to (->) and received from (<-) the dongle on stderr.",
)
@click.option(
    "-d",
    "--device",
    metavar="NAME|PATH",
    help="Use this device: a model name from 'ngenuity devices --all' (also to force a model "
    "when detection fails) or a hidraw path such as /dev/hidraw4.",
)
@click.pass_context
def main(ctx: click.Context, *, verbose: bool, device: str | None) -> None:
    """Configure HyperX devices that NGENUITY supports, on Linux.

    The connected device is detected automatically. If several are connected
    you are asked to pick one; use --device to choose it up front or to force
    a model when detection fails. 'ngenuity devices' lists what is connected.

    Settings are read from the device, so a wireless device has to be awake:
    move it if a command says it is asleep.

    Changes are applied live. Add --save to a command to also store the
    change in the device's onboard memory (the profile NGENUITY saves), so it
    survives a power cycle.

    Use -v before the command to see the raw packets, e.g. 'ngenuity -v status'.
    """
    ctx.obj = Options(verbose=verbose, device=device)


@main.command()
@click.option("--all", "show_all", is_flag=True, help="List every model ngenuity knows about.")
def devices(*, show_all: bool) -> None:
    """List the connected HyperX devices, or with --all every known model."""
    if show_all:
        click.echo(f"{'NAME':30} {'MODEL':28} STATUS")
        for model in MODELS:
            click.echo(f"{model.key:30} {model.name:28} {model.status_label}")
        return
    found = detect(packet_tracer())
    if not found:
        click.echo("No HyperX device found that ngenuity can talk to.")
        return
    for item in found:
        click.echo(f"{item.interface.path}  {item.model.name} ({item.model.status_label})")
        click.echo(f"    name: {item.model.key}   USB: 03f0:{item.interface.product_id:04x}")


@main.command()
def status() -> None:
    """Show the selected device, whether it is connected and its battery state."""
    candidate = selected_candidate()
    click.echo(f"Device:       {candidate.model.name} ({candidate.model.status_label})")
    click.echo(f"Interface:    {candidate.interface.path} ({candidate.interface.name})")
    with open_dongle() as dongle:
        info = dongle.device_info()
        click.echo(f"Device ID:    {info.device_id}")
        if not dongle.is_awake():
            click.echo("State:        asleep or switched off (move it to wake it up)")
            return
        try:
            battery = dongle.battery()
        except NoReplyError:
            click.echo("State:        connected (no battery reported)")
            return
    click.echo("State:        connected")
    click.echo(f"Battery:      {battery.level} % ({battery.charge.label})")
    click.echo(f"Voltage:      {battery.voltage_mv} mV")
    click.echo(f"Temperature:  {battery.temperature_c} °C")


@main.command()
@saved_option
def show(*, saved: bool) -> None:
    """Show all settings: DPI stages, polling rate, lift-off, brightness,
    lighting effect and remapped buttons.
    """
    slot = SAVED_SLOT if saved else LIVE_SLOT
    with open_mouse() as dongle:
        table = dongle.dpi_table(slot)
        sensor = dongle.sensor(slot)
        brightness = dongle.brightness(slot)
        lighting = dongle.lighting(slot)
        assignments = dongle.key_assignments(slot)
    click.echo(f"[{slot_name(slot)}]")
    echo_dpi_table(table)
    click.echo(f"Lift-off:     {sensor.lift_off.label}")
    click.echo(f"Brightness:   {brightness_to_percent(brightness)} %")
    click.echo(f"Lighting:     {lighting.label}")
    echo_assignments(assignments)


@main.group(invoke_without_command=True)
@click.pass_context
def dpi(ctx: click.Context) -> None:
    """Show or change the DPI stages (cycled with the button under the wheel).

    Stages are numbered from 1 and the active stage is marked with *.
    Each change reads the current table from the mouse first, so the other
    stages and the active stage stay as they are. With --save the whole
    resulting table is stored in the mouse's memory.
    """
    if ctx.invoked_subcommand is None:
        with open_mouse() as dongle:
            table = dongle.dpi_table()
        echo_dpi_table(table)


@dpi.command("set")
@click.argument("stage", type=STAGE)
@click.argument("value", type=DPI)
@save_option
def dpi_set(stage: int, value: int, *, save: bool) -> None:
    """Set the DPI of STAGE to VALUE (the range depends on the model, see 'ngenuity status').

    Example: ngenuity dpi set 3 1600
    """
    check_dpi(value)
    with open_mouse() as dongle:
        table = dongle.dpi_table()
        index = stage_index(table, stage)
        current = table.stages[index]
        changed = table.replace_stage(index, dataclasses.replace(current, dpi=value))
        write_dpi_table(dongle, changed, save=save)
    click.echo(f"Stage {stage} is now {value} DPI (was {current.dpi}).{saved_note(save=save)}")


@dpi.command("color")
@click.argument("stage", type=STAGE)
@click.argument("colour", type=COLOR)
@save_option
def dpi_color(stage: int, colour: Rgb, *, save: bool) -> None:
    """Set the indicator colour of STAGE.

    COLOUR is a name (red, green, blue, yellow, cyan, magenta, orange, purple,
    pink, white, off) or a hex value such as #ff8000.
    """
    with open_mouse() as dongle:
        table = dongle.dpi_table()
        index = stage_index(table, stage)
        current = table.stages[index]
        changed = table.replace_stage(index, dataclasses.replace(current, color=colour))
        write_dpi_table(dongle, changed, save=save)
    click.echo(f"Stage {stage} colour is now {colour.describe()}.{saved_note(save=save)}")


@dpi.command("select")
@click.argument("stage", type=STAGE)
@save_option
def dpi_select(stage: int, *, save: bool) -> None:
    """Make STAGE the active DPI stage."""
    with open_mouse() as dongle:
        table = dongle.dpi_table()
        index = stage_index(table, stage)
        write_dpi_table(dongle, dataclasses.replace(table, active_stage=index), save=save)
    click.echo(
        f"Stage {stage} ({table.stages[index].dpi} DPI) is now active.{saved_note(save=save)}"
    )


@dpi.command("add")
@click.argument("value", type=DPI)
@click.argument("colour", type=COLOR, default=DEFAULT_STAGE_COLOR.hex)
@save_option
def dpi_add(value: int, colour: Rgb, *, save: bool) -> None:
    """Add a new last stage with VALUE DPI and an optional COLOUR (default white)."""
    check_dpi(value)
    with open_mouse() as dongle:
        table = dongle.dpi_table()
        if len(table.stages) >= MAX_STAGES:
            msg = f"the mouse supports at most {MAX_STAGES} stages"
            raise click.ClickException(msg)
        stages = (*table.stages, DpiStage(value, colour))
        write_dpi_table(dongle, dataclasses.replace(table, stages=stages), save=save)
    click.echo(
        f"Added stage {len(stages)}: {value} DPI, {colour.describe()}.{saved_note(save=save)}"
    )


@dpi.command("remove")
@click.argument("stage", type=STAGE)
@save_option
def dpi_remove(stage: int, *, save: bool) -> None:
    """Remove STAGE; the stages after it move up by one."""
    with open_mouse() as dongle:
        table = dongle.dpi_table()
        index = stage_index(table, stage)
        if len(table.stages) == 1:
            msg = "the last remaining stage cannot be removed"
            raise click.ClickException(msg)
        stages = tuple(item for position, item in enumerate(table.stages) if position != index)
        active = table.active_stage
        if active > index or active == len(stages):
            active -= 1
        write_dpi_table(dongle, DpiTable(table.polling_rate, active, stages), save=save)
    click.echo(f"Removed stage {stage}.{saved_note(save=save)}")


@main.command()
@click.argument("rate", type=click.Choice([str(int(rate)) for rate in PollingRate]), required=False)
@save_option
def polling(rate: str | None, *, save: bool) -> None:
    """Show or set the polling rate in Hz (125 up to 8000, depending on the model).

    Example: ngenuity polling 1000 --save
    """
    if rate is not None:
        supported = current_model().polling_rates
        require(
            PollingRate(int(rate)) in supported,
            "supported polling rates are " + ", ".join(str(int(item)) for item in supported),
        )
    with open_mouse() as dongle:
        table = dongle.dpi_table()
        if rate is None:
            click.echo(f"Polling rate: {int(table.polling_rate)} Hz")
            return
        changed = dataclasses.replace(table, polling_rate=PollingRate(int(rate)))
        write_dpi_table(dongle, changed, save=save)
    click.echo(
        f"Polling rate is now {rate} Hz (was {int(table.polling_rate)} Hz).{saved_note(save=save)}"
    )


@main.command()
@click.argument(
    "distance", type=click.Choice(["low", "high"], case_sensitive=False), required=False
)
@save_option
def liftoff(distance: str | None, *, save: bool) -> None:
    """Show or set the lift-off distance: low (1 mm) or high (2 mm)."""
    with open_mouse() as dongle:
        sensor = dongle.sensor()
        if distance is None:
            click.echo(f"Lift-off: {sensor.lift_off.label}")
            return
        changed = dataclasses.replace(sensor, lift_off=LiftOff[distance.upper()])
        write_sensor(dongle, changed, save=save)
    click.echo(f"Lift-off is now {changed.lift_off.label}.{saved_note(save=save)}")


@main.command("battery-alert")
@click.argument("percent", type=click.IntRange(BATTERY_ALERT_MIN, BATTERY_ALERT_MAX))
@save_option
def battery_alert(percent: int, *, save: bool) -> None:
    """Set the battery level (5-25 %) at which the mouse warns that it is low.

    NGENUITY uses 10 % by default. The mouse cannot report the current value,
    so this command only sets it.

    Example: ngenuity battery-alert 10 --save
    """
    with open_mouse() as dongle:
        dongle.set_battery_alert(percent, save=save)
    click.echo(f"Low-battery alert is now at {percent} %.{saved_note(save=save)}")


@main.command()
@click.argument("percent", type=PERCENT, required=False)
@save_option
def brightness(percent: int | None, *, save: bool) -> None:
    """Show or set the LED brightness in percent (0 turns the LED off).

    Example: ngenuity brightness 50
    """
    require_lighting()
    with open_mouse() as dongle:
        if percent is None:
            click.echo(f"Brightness: {brightness_to_percent(dongle.brightness())} %")
            return
        write_brightness(dongle, percent, save=save)
    click.echo(f"Brightness is now {percent} %.{saved_note(save=save)}")


@main.command()
@click.argument("name", metavar="BUTTON", type=BUTTON, required=False)
@click.argument("action_name", metavar="ACTION", required=False)
@save_option
@saved_option
@click.option("--force", is_flag=True, help="Allow remapping the left button.")
def button(
    name: str | None, action_name: str | None, *, save: bool, saved: bool, force: bool
) -> None:
    """Show the remapped buttons, or assign ACTION to BUTTON.

    BUTTON is one of: left, right, middle, back, forward, dpi.

    ACTION is one of:

    \b
      default                      restore the button's own function
      left, right, middle,
      back, forward                act as that mouse button
      disable                      do nothing
      dpi-up, dpi-down, dpi-next,
      dpi-previous, dpi-clutch     DPI functions
      next-app, previous-app       switch applications
      play-pause, next-track, previous-track, stop,
      mute, volume-up, volume-down media keys
      calculator, mail, search, browser-home, browser-back,
      browser-forward, browser-refresh
      key:NAME                     a keyboard key, e.g. key:a, key:f5,
                                   key:enter, key:left-ctrl, key:page-up

    Examples:

    \b
      ngenuity button back forward
      ngenuity button forward volume-up --save
      ngenuity button forward default --save
    """
    if name is None:
        slot = SAVED_SLOT if saved else LIVE_SLOT
        with open_mouse() as dongle:
            assignments = dongle.key_assignments(slot)
        click.echo(f"[{slot_name(slot)}]")
        echo_assignments(assignments)
        return
    target = Button[name.upper()]
    check_button(target)
    action = parse_button_action(action_name)
    if target is Button.LEFT and not force and action != ACTIONS["left"]:
        msg = "remapping the left button can leave you without a left click; add --force"
        raise click.ClickException(msg)
    with open_mouse() as dongle:
        current = [item for item in dongle.key_assignments() if item.button != target]
        if action is not None:
            current.append(Assignment(target, action))
        assignments = [item for item in current if not is_default(item)]
        write_assignments(dongle, assignments, save=save)
    label = "its default action" if action is None else action.label
    click.echo(f"The {target.label} button now does {label}.{saved_note(save=save)}")


def upload_effect(colors: list[Rgb], speed: int, name: str, *, save: bool) -> None:
    require_lighting()
    expected = LightingEffect(LightingMode.FRAME_LIGHT, speed)
    with open_mouse() as dongle:
        for slot in target_slots(save=save):
            click.echo(f"Uploading {name} to the {slot_name(slot)}...")
            dongle.set_frame_light(colors, speed, slot, current_model().leds)
            warn_mismatch("lighting effect", slot, expected, dongle.lighting(slot))
    click.echo(f"Lighting is now {name}.{saved_note(save=save)}")


def require_colors(colours: tuple[Rgb, ...]) -> None:
    if len(colours) == 1:
        msg = "give at least two colours, or none for NGENUITY's default gradient"
        raise click.BadParameter(msg, param_hint="COLOURS")


@main.group(invoke_without_command=True)
@saved_option
@click.pass_context
def lighting(ctx: click.Context, *, saved: bool) -> None:
    """Show or change the lighting effect the mouse plays by itself.

    These are NGENUITY's software effects for this mouse, rendered the same
    way NGENUITY's light engine renders them and stored on the mouse as one
    looping cycle of colour frames. Use --save to keep the effect after a
    power cycle; brightness is set separately with 'ngenuity brightness'.

    COLOUR is a name (red, green, blue, yellow, cyan, magenta, orange, purple,
    pink, white, off) or a hex value such as #ff8000.
    """
    if ctx.invoked_subcommand is None:
        require_lighting()
        slot = SAVED_SLOT if saved else LIVE_SLOT
        with open_mouse() as dongle:
            effect = dongle.lighting(slot)
        click.echo(f"[{slot_name(slot)}]")
        click.echo(f"Lighting: {effect.label}")


@lighting.command("solid")
@click.argument("colour", type=COLOR)
@save_option
def lighting_solid(colour: Rgb, *, save: bool) -> None:
    """Show one solid COLOUR.

    Example: ngenuity lighting solid purple --save
    """
    require_effect(Effect.SOLID)
    upload_effect(
        effects.solid(colour), effects.DEFAULT_SPEED, f"solid {colour.describe()}", save=save
    )


@lighting.command("breathing")
@click.argument("colour", type=COLOR)
@speed_option
@save_option
def lighting_breathing(colour: Rgb, speed: int, *, save: bool) -> None:
    """Fade COLOUR in and out."""
    require_effect(Effect.BREATHING)
    upload_effect(effects.breathing(colour), speed, f"breathing {colour.describe()}", save=save)


@lighting.command("alternating")
@click.argument("first", metavar="COLOUR1", type=COLOR)
@click.argument("second", metavar="COLOUR2", type=COLOR)
@click.option("--gradient", is_flag=True, help="Fade between the colours instead of switching.")
@speed_option
@save_option
def lighting_alternating(
    first: Rgb, second: Rgb, speed: int, *, gradient: bool, save: bool
) -> None:
    """Switch between COLOUR1 and COLOUR2."""
    require_effect(Effect.ALTERNATING)
    colors = effects.alternating(first, second, gradient=gradient)
    upload_effect(colors, speed, f"alternating {first.describe()} / {second.describe()}", save=save)


@lighting.command("confetti")
@speed_option
@save_option
def lighting_confetti(speed: int, *, save: bool) -> None:
    """Blend through random colours."""
    require_effect(Effect.CONFETTI)
    upload_effect(effects.confetti(), speed, "confetti", save=save)


@lighting.command("spectrum")
@click.argument("colours", nargs=-1, type=COLOR)
@speed_option
@save_option
def lighting_spectrum(colours: tuple[Rgb, ...], speed: int, *, save: bool) -> None:
    """Blend from one colour to the next (NGENUITY's Spectrum Wave).

    Without COLOURS it uses NGENUITY's default gradient.

    Example: ngenuity lighting spectrum red green blue
    """
    require_effect(Effect.SPECTRUM)
    require_colors(colours)
    colors = list(colours) or [color for _, color in effects.GRADIENT]
    upload_effect(effects.spectrum(colors), speed, "spectrum wave", save=save)


@lighting.command("wave")
@click.argument("colours", nargs=-1, type=COLOR)
@speed_option
@save_option
def lighting_wave(colours: tuple[Rgb, ...], speed: int, *, save: bool) -> None:
    """Move through a colour gradient (NGENUITY's Wave).

    Without COLOURS it uses NGENUITY's default gradient.
    """
    require_effect(Effect.WAVE)
    require_colors(colours)
    stops = effects.even_stops(colours) if colours else effects.GRADIENT
    upload_effect(effects.wave(stops), speed, "wave", save=save)


@lighting.command("sunrise")
@speed_option
@save_option
def lighting_sunrise(speed: int, *, save: bool) -> None:
    """Warm sunrise colours (one of NGENUITY's three Sunrise gradients, picked at random)."""
    require_effect(Effect.SUNRISE)
    upload_effect(effects.sunrise(), speed, "sunrise", save=save)


@lighting.command("rainbow")
@speed_option
@save_option
def lighting_rainbow(speed: int, *, save: bool) -> None:
    """Restore the colour cycle NGENUITY stored on the mouse (exact copy)."""
    upload_effect(effects.rainbow(), speed, "rainbow colour cycle", save=save)


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

    Example: ngenuity color red --seconds 10
    """
    packet = encode_live_color(colour, require_lighting().leds)
    deadline = None if seconds is None else time.monotonic() + seconds
    hint = f"for {seconds:g} s" if seconds is not None else "press Ctrl+C to stop"
    with open_mouse() as dongle:
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
    reports.
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
        except KeyboardInterrupt:
            pass
