# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import cast

import click
from pioreactor import types as pt
from pioreactor.background_jobs.base import BackgroundJobWithDodgingContrib
from pioreactor.config import config
from pioreactor.hardware import get_pwm_to_pin_map
from pioreactor.utils import clamp
from pioreactor.utils.pwm import PWM
from pioreactor.whoami import get_assigned_experiment_name
from pioreactor.whoami import get_unit_name


__plugin_name__ = "pioreactor_air_bubbler"
__plugin_version__ = "0.12.0"


class AirBubbler(BackgroundJobWithDodgingContrib):
    job_name = "air_bubbler"
    published_settings: dict[str, pt.PublishableSetting] = {
        "duty_cycle": {"settable": True, "unit": "%", "datatype": "float"}
    }

    def __init__(
        self,
        unit: pt.Unit,
        experiment: pt.Experiment,
        duty_cycle: float,
        hertz: float = 60,
        enable_dodging_od: bool = False,
    ) -> None:
        if not 0 <= duty_cycle <= 100:
            raise ValueError("duty_cycle must be between 0 and 100, inclusive")
        if hertz <= 0:
            raise ValueError("hertz must be greater than 0")

        self.duty_cycle = float(round(float(duty_cycle)))
        self.hertz = float(hertz)
        pwm_channel = cast(pt.PwmChannel | None, config.get("PWM_reverse", "air_bubbler", fallback=None))
        if not pwm_channel:
            raise ValueError("Assign air_bubbler to a channel in the [PWM] section of config.ini")

        try:
            self.pin = get_pwm_to_pin_map()[pwm_channel]
        except KeyError as exc:
            raise ValueError(f"Unknown PWM channel configured for air_bubbler: {pwm_channel}") from exc

        super().__init__(
            plugin_name=__plugin_name__,
            unit=unit,
            experiment=experiment,
            enable_dodging_od=enable_dodging_od,
        )

        try:
            self.pwm = PWM(
                self.pin,
                self.hertz,
                unit=self.unit,
                experiment=self.experiment,
                pub_client=self.pub_client,
                logger=self.logger,
            )
            self.pwm.start(0)
            self.pwm.lock()
        except Exception:
            self.clean_up()
            raise

    def on_disconnected(self) -> None:
        super().on_disconnected()
        if hasattr(self, "pwm"):
            self.pwm.clean_up()

    def stop_pumping(self) -> None:
        if hasattr(self, "pwm"):
            self.pwm.change_duty_cycle(0)

    def start_pumping(self) -> None:
        self.pwm.change_duty_cycle(self.duty_cycle)

    def on_sleeping(self) -> None:
        super().on_sleeping()
        self.stop_pumping()

    def on_sleeping_to_ready(self) -> None:
        super().on_sleeping_to_ready()
        if not self.currently_dodging_od:
            self.start_pumping()

    def set_duty_cycle(self, value: float) -> None:
        self.duty_cycle = float(clamp(0, round(float(value)), 100))
        if hasattr(self, "pwm") and self.state == self.READY and not self.currently_dodging_od:
            self.pwm.change_duty_cycle(self.duty_cycle)

    def action_to_do_before_od_reading(self) -> None:
        self.stop_pumping()

    def action_to_do_after_od_reading(self) -> None:
        self.start_pumping()

    def initialize_continuous_operation(self) -> None:
        self.start_pumping()

    def initialize_dodging_operation(self) -> None:
        self.stop_pumping()


@click.command(name="air_bubbler")
@click.option("--duty-cycle", type=click.FloatRange(min=0, max=100), default=None)
@click.option("--hertz", type=click.FloatRange(min=0, min_open=True), default=None)
@click.option("--enable-dodging-od/--disable-dodging-od", default=None)
def click_air_bubbler(
    duty_cycle: float | None,
    hertz: float | None,
    enable_dodging_od: bool | None,
) -> None:
    """Run the air bubbler."""
    duty_cycle = (
        duty_cycle
        if duty_cycle is not None
        else config.getfloat("air_bubbler.config", "duty_cycle", fallback=10.0)
    )
    hertz = hertz if hertz is not None else config.getfloat("air_bubbler.config", "hertz", fallback=200.0)
    enable_dodging_od = (
        enable_dodging_od
        if enable_dodging_od is not None
        else config.getboolean("air_bubbler.config", "enable_dodging_od", fallback=False)
    )
    unit = get_unit_name()
    experiment = get_assigned_experiment_name(unit)

    with AirBubbler(
        unit=unit,
        experiment=experiment,
        duty_cycle=duty_cycle,
        hertz=hertz,
        enable_dodging_od=enable_dodging_od,
    ) as job:
        job.block_until_disconnected()
