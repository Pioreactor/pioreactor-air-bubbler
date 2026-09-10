# -*- coding: utf-8 -*-
from __future__ import annotations

from math import isfinite
from threading import RLock
from time import monotonic
from typing import cast

import click
from pioreactor import types as pt
from pioreactor.background_jobs.base import BackgroundJobWithDodgingContrib
from pioreactor.config import config
from pioreactor.hardware import get_pwm_to_pin_map
from pioreactor.utils import clamp
from pioreactor.utils.pwm import PWM
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.whoami import get_assigned_experiment_name
from pioreactor.whoami import get_unit_name


__plugin_name__ = "pioreactor_air_bubbler"
__plugin_version__ = "0.12.1"


class _AirBubblerBase(BackgroundJobWithDodgingContrib):
    job_name = "_air_bubbler_base"
    published_settings: dict[str, pt.PublishableSetting] = {
        "duty_cycle": {"settable": True, "unit": "%", "datatype": "float"},
    }

    def __init__(
        self,
        unit: pt.Unit,
        experiment: pt.Experiment,
        duty_cycle: float,
        hertz: float = 60,
        enable_dodging_od: bool = False,
    ) -> None:
        super().__init__(
            plugin_name=__plugin_name__,
            unit=unit,
            experiment=experiment,
            enable_dodging_od=enable_dodging_od,
        )

        self._pump_lock = RLock()
        self._pump_running = False
        self._pump_closed = False
        self._od_window_open = False

        if not 0 <= duty_cycle <= 100:
            raise ValueError("duty_cycle must be between 0 and 100, inclusive")
        if not isfinite(hertz) or hertz <= 0:
            raise ValueError("hertz must be greater than 0")

        self.hertz = float(hertz)
        pwm_channel = cast(pt.PwmChannel | None, config.get("PWM_reverse", "air_bubbler", fallback=None))
        if not pwm_channel:
            raise ValueError("Assign air_bubbler to a channel in the [PWM] section of config.ini")

        try:
            self.pin = get_pwm_to_pin_map()[pwm_channel]
        except KeyError as exc:
            raise ValueError(f"Unknown PWM channel configured for air_bubbler: {pwm_channel}") from exc

        self.duty_cycle = float(round(float(duty_cycle)))

        try:
            self.pwm = PWM(
                self.pin,
                self.hertz,
                unit=self.unit,
                experiment=self.experiment,
                pub_client=self.pub_client,
                logger=self.logger,
            )
            self.pwm.lock()
            self.pwm.start(0)
        except Exception:
            self.clean_up()
            raise

    def on_disconnected(self) -> None:
        if hasattr(self, "_pump_lock"):
            with self._pump_lock:
                self._pump_closed = True
                self.stop_pumping()
        if hasattr(self, "pump_timer"):
            self.pump_timer.cancel()
        super().on_disconnected()
        if hasattr(self, "pwm"):
            self.pwm.clean_up()

    def stop_pumping(self) -> None:
        with self._pump_lock:
            if hasattr(self, "pwm"):
                self.pwm.change_duty_cycle(0)
            self._pump_running = False

    def start_pumping(self) -> None:
        """Start only when the job and OD window allow pumping."""
        with self._pump_lock:
            if self._pump_closed:
                return
            if self.state != self.READY or self.duty_cycle == 0:
                if self._pump_running:
                    self.stop_pumping()
                return
            if self.currently_dodging_od and not self._od_window_open:
                if self._pump_running:
                    self.stop_pumping()
                return

            if not self._pump_running:
                self.pwm.change_duty_cycle(self.duty_cycle)
                self._pump_running = True

    def on_ready(self) -> None:
        super().on_ready()
        self.start_pumping()

    def on_sleeping(self) -> None:
        super().on_sleeping()
        with self._pump_lock:
            self._od_window_open = False
            self.stop_pumping()

    def set_duty_cycle(self, value: float) -> None:
        if not isfinite(value):
            raise ValueError("duty_cycle must be finite")
        with self._pump_lock:
            self.duty_cycle = float(clamp(0, round(float(value)), 100))
            if self._pump_running:
                if self.duty_cycle == 0:
                    self.stop_pumping()
                else:
                    self.pwm.change_duty_cycle(self.duty_cycle)

    def action_to_do_before_od_reading(self) -> None:
        with self._pump_lock:
            self._od_window_open = False
            self.stop_pumping()

    def action_to_do_after_od_reading(self) -> None:
        with self._pump_lock:
            self._od_window_open = self.state == self.READY and self.currently_dodging_od
            self.start_pumping()

    def initialize_continuous_operation(self) -> None:
        # This base-class hook means OD dodging is inactive, not continuous aeration.
        with self._pump_lock:
            self._od_window_open = False
            self.start_pumping()

    def initialize_dodging_operation(self) -> None:
        with self._pump_lock:
            self._od_window_open = False
            self.stop_pumping()


class AirBubbler(_AirBubblerBase):
    """Burst-only aeration: every stop requires a full rest before another burst."""

    job_name = "air_bubbler"
    published_settings: dict[str, pt.PublishableSetting] = {
        **_AirBubblerBase.published_settings,
        "burst_duration": {"settable": True, "unit": "s", "datatype": "float"},
        "rest_duration": {"settable": True, "unit": "s", "datatype": "float"},
    }

    def __init__(
        self,
        unit: pt.Unit,
        experiment: pt.Experiment,
        duty_cycle: float,
        hertz: float = 60,
        enable_dodging_od: bool = False,
        burst_duration: float = 1.0,
        rest_duration: float = 30.0,
    ) -> None:
        super().__init__(unit, experiment, duty_cycle, hertz, enable_dodging_od)
        self._burst_ends_at = 0.0
        self._rest_ends_at = 0.0
        self.set_burst_duration(burst_duration)
        self.set_rest_duration(rest_duration)
        self.pump_timer = RepeatedTimer(
            0.05, self.start_pumping, job_name=self.job_name, logger=self.logger
        ).start()

    def start_pumping(self) -> None:
        with self._pump_lock:
            now = monotonic()
            if self._pump_running and now >= self._burst_ends_at:
                self.stop_pumping()
                return
            if not self._pump_running and now < self._rest_ends_at:
                return
            was_running = self._pump_running
            super().start_pumping()
            if not was_running and self._pump_running:
                self._burst_ends_at = monotonic() + self.burst_duration

    def stop_pumping(self) -> None:
        with self._pump_lock:
            was_running = self._pump_running
            super().stop_pumping()
            if was_running:
                self._rest_ends_at = monotonic() + self.rest_duration

    def set_burst_duration(self, value: float) -> None:
        if not 0 < value:
            raise ValueError("burst_duration must be greater than 0.")
        with self._pump_lock:
            self.burst_duration = float(value)
            if self._pump_running:
                self.stop_pumping()

    def set_rest_duration(self, value: float) -> None:
        if not isfinite(value) or value <= 0:
            raise ValueError("rest_duration be finite")
        with self._pump_lock:
            self.rest_duration = float(value)
            if self._rest_ends_at > monotonic():
                self._rest_ends_at = max(self._rest_ends_at, monotonic() + value)


class AirBubblerContinuous(_AirBubblerBase):
    """Advanced continuous aeration, intentionally absent from the job UI."""

    job_name = "air_bubbler_continuous"

    def __init__(
        self,
        unit: pt.Unit,
        experiment: pt.Experiment,
        duty_cycle: float,
        hertz: float = 60,
        enable_dodging_od: bool = False,
    ) -> None:
        super().__init__(unit, experiment, duty_cycle, hertz, enable_dodging_od)
        self.logger.warning(
            "Advanced continuous aeration has no burst/rest limits. Sustained bubbling can "
            "cause foaming, vial-cap leaks, and media-tube contamination. "
            "OD dodging alone does not prevent excessive aeration."
        )

    def set_duty_cycle(self, value: float) -> None:
        super().set_duty_cycle(value)
        self.start_pumping()


@click.command(name="air_bubbler")
@click.option("--duty-cycle", type=click.FloatRange(min=0, max=100), default=None)
@click.option("--hertz", type=click.FloatRange(min=0, min_open=True), default=None)
@click.option("--enable-dodging-od/--disable-dodging-od", default=None)
@click.option(
    "--burst-duration",
    type=click.FloatRange(min=0, min_open=True, max=2),
    default=None,
    help="Seconds per burst (maximum 2).",
)
@click.option(
    "--rest-duration",
    type=click.FloatRange(min=30),
    default=None,
    help="Minimum seconds off after each burst (at least 30).",
)
def click_air_bubbler(
    duty_cycle: float | None,
    hertz: float | None,
    enable_dodging_od: bool | None,
    burst_duration: float | None,
    rest_duration: float | None,
) -> None:
    """Run short air bursts by default, optionally dodging OD readings."""
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
    burst_duration = (
        burst_duration
        if burst_duration is not None
        else config.getfloat("air_bubbler.config", "burst_duration", fallback=1.0)
    )
    rest_duration = (
        rest_duration
        if rest_duration is not None
        else config.getfloat("air_bubbler.config", "rest_duration", fallback=30.0)
    )
    unit = get_unit_name()
    experiment = get_assigned_experiment_name(unit)

    with AirBubbler(
        unit=unit,
        experiment=experiment,
        duty_cycle=duty_cycle,
        hertz=hertz,
        enable_dodging_od=enable_dodging_od,
        burst_duration=burst_duration,
        rest_duration=rest_duration,
    ) as job:
        job.block_until_disconnected()


@click.command(name="air_bubbler_continuous")
@click.option("--duty-cycle", type=click.FloatRange(min=0, max=100), default=None)
@click.option("--hertz", type=click.FloatRange(min=0, min_open=True), default=None)
@click.option("--enable-dodging-od/--disable-dodging-od", default=None)
def click_air_bubbler_continuous(
    duty_cycle: float | None,
    hertz: float | None,
    enable_dodging_od: bool | None,
) -> None:
    """Advanced use only: sustained aeration risks foaming, leaks and contamination."""
    duty_cycle = (
        duty_cycle
        if duty_cycle is not None
        else config.getfloat("air_bubbler_continuous.config", "duty_cycle", fallback=70.0)
    )
    hertz = (
        hertz
        if hertz is not None
        else config.getfloat("air_bubbler_continuous.config", "hertz", fallback=200.0)
    )
    enable_dodging_od = (
        enable_dodging_od
        if enable_dodging_od is not None
        else config.getboolean("air_bubbler_continuous.config", "enable_dodging_od", fallback=False)
    )
    unit = get_unit_name()
    experiment = get_assigned_experiment_name(unit)
    with AirBubblerContinuous(
        unit=unit,
        experiment=experiment,
        duty_cycle=duty_cycle,
        hertz=hertz,
        enable_dodging_od=enable_dodging_od,
    ) as job:
        job.block_until_disconnected()
