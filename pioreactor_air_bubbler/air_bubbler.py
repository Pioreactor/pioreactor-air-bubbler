# -*- coding: utf-8 -*-
from __future__ import annotations

import click
from pioreactor.background_jobs.base import BackgroundJobWithDodgingContrib
from pioreactor.config import config
from pioreactor.hardware import PWM_TO_PIN
from pioreactor.utils import clamp
from pioreactor.utils.pwm import PWM
from pioreactor.whoami import get_latest_experiment_name
from pioreactor.whoami import get_unit_name


class AirBubbler(BackgroundJobWithDodgingContrib):
    job_name = "air_bubbler"
    published_settings = {"duty_cycle": {"settable": False, "unit": "%", "datatype": "float"}}

    def __init__(self, unit: str, experiment: str, duty_cycle: float, hertz: float = 60):
        super(AirBubbler, self).__init__(
            plugin_name="pioreactor_air_bubbler",
            unit=unit,
            experiment=experiment,
        )

        self.hertz = hertz
        try:
            self.pin = PWM_TO_PIN[config.get("PWM_reverse", "air_bubbler")]
        except KeyError:
            raise KeyError("Unable to find `air_bubbler` under PWM section in the config.ini")

        self.duty_cycle = duty_cycle
        self.pwm = PWM(self.pin, self.hertz, unit=self.unit, experiment=self.experiment)
        self.pwm.start(0)

    def on_disconnected(self):
        self.stop_pumping()
        self.pwm.stop()
        self.pwm.clean_up()

    def stop_pumping(self):
        if hasattr(self, "pwm"):
            self.pwm.change_duty_cycle(0)

    def start_pumping(self):
        self.pwm.change_duty_cycle(self.duty_cycle)

    def on_sleeping(self):
        self.stop_pumping()

    def on_sleeping_to_ready(self) -> None:
        self.start_pumping()

    def set_duty_cycle(self, value):
        self.duty_cycle = clamp(0, round(float(value)), 100)
        self.pwm.change_duty_cycle(self.duty_cycle)

    def action_to_do_before_od_reading(self):
        self.stop_pumping()

    def action_to_do_after_od_reading(self):
        self.start_pumping()


@click.command(name="air_bubbler")
def click_air_bubbler():
    """
    turn on air bubbler
    """

    dc = config.getfloat("air_bubbler.config", "duty_cycle")
    hertz = config.getfloat("air_bubbler.config", "hertz")

    ab = AirBubbler(unit=get_unit_name(), experiment=get_latest_experiment_name(), duty_cycle=dc, hertz=hertz)
    ab.start_pumping()
    ab.block_until_disconnected()
