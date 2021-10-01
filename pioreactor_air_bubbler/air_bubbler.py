# -*- coding: utf-8 -*-
import signal, time
import click
from pioreactor.background_jobs.base import BackgroundJobContrib
from pioreactor.whoami import get_latest_experiment_name, get_unit_name
from pioreactor.utils import pio_jobs_running
from pioreactor.config import config
from pioreactor.hardware_mappings import PWM_TO_PIN
from pioreactor.pubsub import subscribe
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.utils.pwm import PWM


def clamp(minimum, x, maximum):
    return max(minimum, min(x, maximum))


class AirBubbler(BackgroundJobContrib):

    published_settings = {
        "duty_cycle": {"settable": True, "unit": "%", "datatype": "float"}
    }

    def __init__(self, duty_cycle, hertz=60, unit=None, experiment=None):
        super(AirBubbler, self).__init__(
            job_name="air_bubbler",
            plugin_name="pioreactor_air_bubbler",
            unit=unit,
            experiment=experiment,
        )

        self.hertz = hertz
        try:
            self.pin = PWM_TO_PIN[config.getint("PWM_reverse", "air_bubbler")]
        except KeyError:
            raise KeyError(
                "Unable to find `air_bubbler` under PWM section in the config.ini"
            )

        self.pwm = PWM(self.pin, self.hertz)
        self.pwm.start(0)

        self.set_duty_cycle(duty_cycle)

        self.start_passive_listeners()

    def on_disconnect(self):
        # not necessary, but will update the UI to show that the speed is 0 (off)
        if hasattr(self, "sneak_in_timer"):
            self.sneak_in_timer.cancel()

        self.stop_pumping()
        self.pwm.stop()
        self.pwm.cleanup()

    def stop_pumping(self):
        # if the user unpauses, we want to go back to their previous value, and not the default.
        self._previous_duty_cycle = self.duty_cycle
        self.set_duty_cycle(0)

    def set_state(self, new_state):
        if new_state != self.READY:
            try:
                self.stop_pumping()
            except AttributeError:
                pass
        elif (new_state == self.READY) and (self.state == self.SLEEPING):
            self.duty_cycle = self._previous_duty_cycle
            self.start_pumping()
        super(AirBubbler, self).set_state(new_state)

    def set_duty_cycle(self, value):
        self.duty_cycle = clamp(0, round(float(value)), 100)
        self.pwm.change_duty_cycle(self.duty_cycle)

    def start_passive_listeners(self):

        self.subscribe_and_callback(
            self.turn_off_pump_between_readings,
            f"pioreactor/{self.unit}/{self.experiment}/adc_reader/interval",
        )

    def turn_off_pump_between_readings(self, msg):

        if not msg.payload:
            # OD reading stopped, turn on air_bubbler always and exit
            self.set_duty_cycle(config.getint("air_bubbler", "duty_cycle"))
            return

        # OD started - turn off pump immediately
        self.set_duty_cycle(0)

        try:
            self.sneak_in_timer.cancel()
        except AttributeError:
            pass

        # post_duration: how long to wait (seconds) after the ADS reading before running sneak_in
        # pre_duration: duration between stopping the action and the next ADS reading
        # we have a pretty large pre_duration, since the air pump can introduce microbubbles
        # that we want to see dissipate.
        post_duration, pre_duration = 0.6, 1.25

        def sneak_in():
            if self.state != self.READY:
                return

            self.set_duty_cycle(config.getint("air_bubbler", "duty_cycle"))
            time.sleep(ads_interval - (post_duration + pre_duration))
            self.set_duty_cycle(0)

        # this could fail in the following way:
        # in the same experiment, the od_reading fails so that the ADC attributes are never
        # cleared. Later, this job starts, and it will pick up the _old_ ADC attributes.
        ads_start_time = float(
            subscribe(
                f"pioreactor/{self.unit}/{self.experiment}/adc_reader/first_ads_obs_time"
            ).payload
        )

        ads_interval = float(
            subscribe(
                f"pioreactor/{self.unit}/{self.experiment}/adc_reader/interval"
            ).payload
        )

        # get interval, and confirm that the requirements are possible: post_duration + pre_duration <= ADS interval
        if ads_interval <= (post_duration + pre_duration):
            # TODO: this should error out better. The thread errors, but the main program doesn't.
            raise ValueError("Your samples_per_second is too high to add in a pump.")

        self.sneak_in_timer = RepeatedTimer(ads_interval, sneak_in, run_immediately=False)

        time_to_next_ads_reading = ads_interval - (
            (time.time() - ads_start_time) % ads_interval
        )

        time.sleep(time_to_next_ads_reading + post_duration)
        self.sneak_in_timer.start()


@click.command(name="air_bubbler")
def click_air_bubbler():
    """
    turn on air_bubbler
    """
    if "od_reading" in pio_jobs_running():
        dc = 0
    else:
        dc = config.getint("air_bubbler", "duty_cycle")

    AirBubbler(
        duty_cycle=dc, unit=get_unit_name(), experiment=get_latest_experiment_name()
    )

    signal.pause()
