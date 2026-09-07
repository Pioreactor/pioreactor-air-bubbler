# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import cast
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

import pioreactor_air_bubbler as plugin


def test_plugin_exposes_discoverable_click_command() -> None:
    assert plugin.click_air_bubbler.name == plugin.AirBubbler.job_name
    assert plugin.click_air_bubbler_continuous.name == plugin.AirBubblerContinuous.job_name


def test_plugin_initialization_starts_after_the_base_job(monkeypatch: pytest.MonkeyPatch) -> None:
    initialization_order: list[str] = []
    pwm = MagicMock()

    def initialize_base_job(
        self: plugin.AirBubbler,
        unit: str,
        experiment: str,
        plugin_name: str,
        enable_dodging_od: bool,
    ) -> None:
        self.unit = unit
        self.experiment = experiment
        self.pub_client = MagicMock()
        self.logger = MagicMock()
        self._is_cleaned_up = False
        initialization_order.append("base")

    def publish_setting(self: plugin.AirBubbler, setting: str) -> None:
        assert self.unit == "unit"
        assert self.experiment == "experiment"
        initialization_order.append(setting)

    def get_config(*args: object, **kwargs: object) -> str:
        initialization_order.append("config")
        return "2"

    def get_pwm_to_pin_map() -> dict[str, int]:
        initialization_order.append("pwm_map")
        return {"2": 13}

    monkeypatch.setattr(plugin.BackgroundJobWithDodgingContrib, "__init__", initialize_base_job)
    monkeypatch.setattr(plugin.AirBubbler, "_publish_setting", publish_setting)
    monkeypatch.setattr(plugin, "config", MagicMock(get=get_config))
    monkeypatch.setattr(plugin, "get_pwm_to_pin_map", get_pwm_to_pin_map)
    monkeypatch.setattr(plugin, "PWM", MagicMock(return_value=pwm))
    monkeypatch.setattr(plugin, "RepeatedTimer", MagicMock())

    bubbler = object.__new__(plugin.AirBubbler)
    plugin.AirBubbler.__init__(bubbler, "unit", "experiment", duty_cycle=25, hertz=100)

    assert initialization_order == [
        "base",
        "config",
        "pwm_map",
        "duty_cycle",
        "burst_duration",
        "rest_duration",
    ]
    pwm.start.assert_called_once_with(0)
    pwm.lock.assert_called_once_with()


def test_duty_cycle_change_does_not_restart_a_stopped_bubbler() -> None:
    bubbler = object.__new__(plugin.AirBubbler)
    bubbler.pwm = MagicMock()
    bubbler.__dict__["_publish_setting"] = MagicMock()
    bubbler._pump_lock = RLock()
    bubbler._pump_running = False
    bubbler.state = bubbler.SLEEPING
    bubbler.currently_dodging_od = False

    bubbler.set_duty_cycle(25)

    assert bubbler.duty_cycle == 25
    bubbler.pwm.change_duty_cycle.assert_not_called()


def test_duty_cycle_change_updates_a_running_bubbler() -> None:
    bubbler = object.__new__(plugin.AirBubbler)
    bubbler.pwm = MagicMock()
    bubbler.__dict__["_publish_setting"] = MagicMock()
    bubbler._pump_lock = RLock()
    bubbler._pump_running = True
    bubbler.state = bubbler.READY
    bubbler.currently_dodging_od = False

    bubbler.set_duty_cycle(25)

    bubbler.pwm.change_duty_cycle.assert_called_once_with(25)


def test_click_command_uses_context_manager_and_cli_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    job = MagicMock()
    job.__enter__.return_value = job
    air_bubbler = MagicMock(return_value=job)
    monkeypatch.setattr(plugin, "AirBubbler", air_bubbler)
    monkeypatch.setattr(plugin, "get_unit_name", lambda: "unit")
    monkeypatch.setattr(plugin, "get_assigned_experiment_name", lambda unit: "experiment")

    result = CliRunner().invoke(
        plugin.click_air_bubbler,
        ["--duty-cycle", "25", "--hertz", "100", "--enable-dodging-od"],
    )

    assert result.exit_code == 0
    air_bubbler.assert_called_once_with(
        unit="unit",
        experiment="experiment",
        duty_cycle=25.0,
        hertz=100.0,
        enable_dodging_od=True,
        burst_duration=1.0,
        rest_duration=30.0,
    )
    job.block_until_disconnected.assert_called_once_with()
    job.__exit__.assert_called_once()


@pytest.fixture
def bubbler(monkeypatch: pytest.MonkeyPatch) -> plugin.AirBubbler:
    job = object.__new__(plugin.AirBubbler)
    job.__dict__["_publish_setting"] = MagicMock()
    job.pwm = MagicMock()
    job.logger = MagicMock()
    job._pump_lock = RLock()
    job._pump_running = False
    job._pump_closed = False
    job._od_window_open = False
    job._burst_ends_at = 0.0
    job._rest_ends_at = 0.0
    job.state = job.READY
    job.currently_dodging_od = False
    job.duty_cycle = 70.0
    job.burst_duration = 1.0
    job.rest_duration = 30.0
    monkeypatch.setattr(plugin, "monotonic", lambda: 0.0)
    return job


def test_burst_stops_and_requires_full_rest(
    bubbler: plugin.AirBubbler, monkeypatch: pytest.MonkeyPatch
) -> None:
    bubbler.start_pumping()
    cast(MagicMock, bubbler.pwm.change_duty_cycle).assert_called_with(70)
    monkeypatch.setattr(plugin, "monotonic", lambda: 1.0)
    bubbler.start_pumping()
    cast(MagicMock, bubbler.pwm.change_duty_cycle).assert_called_with(0)
    assert not bubbler._pump_running
    monkeypatch.setattr(plugin, "monotonic", lambda: 30.9)
    bubbler.set_duty_cycle(80)
    bubbler.start_pumping()
    assert not bubbler._pump_running
    monkeypatch.setattr(plugin, "monotonic", lambda: 31.0)
    bubbler.start_pumping()
    assert bubbler._pump_running
    cast(MagicMock, bubbler.pwm.change_duty_cycle).assert_called_with(80)


def test_od_interruption_requires_rest_across_od_windows_and_od_shutdown(
    bubbler: plugin.AirBubbler, monkeypatch: pytest.MonkeyPatch
) -> None:
    bubbler.currently_dodging_od = True
    bubbler.initialize_dodging_operation()
    bubbler.start_pumping()
    assert not bubbler._pump_running
    bubbler.action_to_do_after_od_reading()
    assert bubbler._pump_running
    monkeypatch.setattr(plugin, "monotonic", lambda: 0.5)
    bubbler.action_to_do_before_od_reading()
    assert bubbler._rest_ends_at == 30.5
    for now in (5.0, 10.0, 15.0):
        monkeypatch.setattr(plugin, "monotonic", lambda: now)
        bubbler.action_to_do_after_od_reading()
        assert not bubbler._pump_running
        bubbler.action_to_do_before_od_reading()
    assert bubbler._rest_ends_at == 30.5
    bubbler.currently_dodging_od = False
    bubbler.initialize_continuous_operation()
    assert not bubbler._pump_running
    monkeypatch.setattr(plugin, "monotonic", lambda: 31.0)
    bubbler.start_pumping()
    assert bubbler._pump_running
    monkeypatch.setattr(plugin, "monotonic", lambda: 32.0)
    bubbler.start_pumping()
    assert not bubbler._pump_running


@pytest.fixture
def continuous_bubbler(bubbler: plugin.AirBubbler) -> plugin.AirBubblerContinuous:
    job = object.__new__(plugin.AirBubblerContinuous)
    job.__dict__.update(bubbler.__dict__)
    for setting in ("burst_duration", "rest_duration", "_burst_ends_at", "_rest_ends_at"):
        del job.__dict__[setting]
    return job


def test_continuous_has_no_burst_timer_and_still_dodges(
    continuous_bubbler: plugin.AirBubblerContinuous, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = continuous_bubbler
    job.start_pumping()
    monkeypatch.setattr(plugin, "monotonic", lambda: 100.0)
    job.start_pumping()
    assert job._pump_running
    job.currently_dodging_od = True
    job.initialize_dodging_operation()
    assert not job._pump_running
    job.action_to_do_after_od_reading()
    assert job._pump_running
    job.action_to_do_before_od_reading()
    assert not job._pump_running
    job.currently_dodging_od = False
    job.initialize_continuous_operation()
    assert job._pump_running
    job.set_duty_cycle(0)
    assert not job._pump_running
    job.set_duty_cycle(25)
    assert job._pump_running
    assert not hasattr(job, "pump_timer")
    assert "burst_duration" not in job.published_settings
    assert "rest_duration" not in job.published_settings
    assert "advanced_continuous" not in plugin.AirBubbler.published_settings


def test_continuous_sleep_resume_and_disconnect(
    continuous_bubbler: plugin.AirBubblerContinuous, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(plugin.BackgroundJobWithDodgingContrib, "on_sleeping", lambda self: None)
    monkeypatch.setattr(plugin.BackgroundJobWithDodgingContrib, "on_disconnected", lambda self: None)
    job = continuous_bubbler
    job.start_pumping()
    job.state = job.SLEEPING
    job.on_sleeping()
    job.set_duty_cycle(50)
    assert not job._pump_running
    job.state = job.READY
    job.on_ready()
    assert job._pump_running
    job.on_disconnected()
    job.start_pumping()
    assert not job._pump_running


def test_sleep_and_disconnect_prevent_timer_restarts(
    bubbler: plugin.AirBubbler, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(plugin.BackgroundJobWithDodgingContrib, "on_sleeping", lambda self: None)
    monkeypatch.setattr(plugin.BackgroundJobWithDodgingContrib, "on_disconnected", lambda self: None)
    bubbler.start_pumping()
    bubbler.state = bubbler.SLEEPING
    bubbler.on_sleeping()
    bubbler.action_to_do_after_od_reading()
    assert not bubbler._od_window_open
    monkeypatch.setattr(plugin, "monotonic", lambda: 100.0)
    bubbler.start_pumping()
    assert not bubbler._pump_running
    bubbler.state = bubbler.READY
    bubbler.currently_dodging_od = True
    bubbler.start_pumping()
    assert not bubbler._pump_running
    bubbler.action_to_do_after_od_reading()
    assert bubbler._pump_running
    bubbler.pump_timer = MagicMock()
    bubbler.on_disconnected()
    bubbler.pump_timer.cancel.assert_called_once()
    bubbler.pwm.clean_up.assert_called_once()
    bubbler.pwm.reset_mock()
    bubbler.action_to_do_after_od_reading()
    bubbler.start_pumping()
    bubbler.pwm.change_duty_cycle.assert_not_called()


@pytest.mark.parametrize("value", [0, -1, 2.1, float("nan"), float("inf")])
def test_invalid_burst_duration_is_rejected(bubbler: plugin.AirBubbler, value: float) -> None:
    with pytest.raises(ValueError):
        bubbler.set_burst_duration(value)
    assert bubbler.burst_duration == 1


@pytest.mark.parametrize("value", [0, 29, float("nan"), float("inf")])
def test_invalid_rest_duration_is_rejected(bubbler: plugin.AirBubbler, value: float) -> None:
    with pytest.raises(ValueError):
        bubbler.set_rest_duration(value)
    assert bubbler.rest_duration == 30


def test_timing_changes_do_not_extend_burst_or_shorten_rest(bubbler: plugin.AirBubbler) -> None:
    bubbler.start_pumping()
    bubbler.set_burst_duration(2)
    assert not bubbler._pump_running
    bubbler.set_rest_duration(60)
    assert bubbler._rest_ends_at == 60
    bubbler.set_rest_duration(30)
    assert bubbler._rest_ends_at == 60


def test_zero_strength_stops_burst_and_rest_survives_reenable(bubbler: plugin.AirBubbler) -> None:
    bubbler.start_pumping()
    bubbler.set_duty_cycle(0)
    assert not bubbler._pump_running
    bubbler.set_duty_cycle(70)
    bubbler.start_pumping()
    assert not bubbler._pump_running


def test_continuous_command_uses_its_own_config(monkeypatch: pytest.MonkeyPatch) -> None:
    job = MagicMock()
    monkeypatch.setattr(plugin, "AirBubblerContinuous", job)
    monkeypatch.setattr(plugin, "get_unit_name", lambda: "unit")
    monkeypatch.setattr(plugin, "get_assigned_experiment_name", lambda unit: "experiment")
    config = MagicMock()
    config.getfloat.side_effect = [12.0, 150.0]
    config.getboolean.return_value = True
    monkeypatch.setattr(plugin, "config", config)
    result = CliRunner().invoke(plugin.click_air_bubbler_continuous, [])
    assert result.exit_code == 0, result.output
    job.assert_called_once_with(
        unit="unit", experiment="experiment", duty_cycle=12.0, hertz=150.0, enable_dodging_od=True
    )
    assert all(call.args[0] == "air_bubbler_continuous.config" for call in config.mock_calls)
    job.return_value.__enter__.return_value.block_until_disconnected.assert_called_once()
    result = CliRunner().invoke(
        plugin.click_air_bubbler_continuous, ["--duty-cycle", "25", "--hertz", "100", "--disable-dodging-od"]
    )
    assert result.exit_code == 0, result.output
    assert job.call_args.kwargs["duty_cycle"] == 25
    assert job.call_args.kwargs["hertz"] == 100
    assert job.call_args.kwargs["enable_dodging_od"] is False


def test_jobs_cannot_switch_modes_through_cli() -> None:
    assert CliRunner().invoke(plugin.click_air_bubbler, ["--advanced-continuous"]).exit_code == 2
    assert CliRunner().invoke(plugin.click_air_bubbler_continuous, ["--burst-duration", "1"]).exit_code == 2


@pytest.mark.parametrize(
    "first_class,second_class",
    [
        (plugin.AirBubbler, plugin.AirBubblerContinuous),
        (plugin.AirBubblerContinuous, plugin.AirBubbler),
    ],
)
def test_jobs_share_pwm_lock_and_continuous_constructor_warns(
    monkeypatch: pytest.MonkeyPatch,
    first_class: type[plugin._AirBubblerBase],
    second_class: type[plugin._AirBubblerBase],
    tmp_path: Path,
) -> None:
    from pioreactor.exc import PWMError
    from pioreactor.utils import sqlite_cache

    monkeypatch.setattr(
        sqlite_cache, "config", MagicMock(get=MagicMock(return_value=str(tmp_path / "cache.sqlite")))
    )

    def initialize_base_job(self: plugin._AirBubblerBase, **kwargs: object) -> None:
        self.__dict__["_publish_setting"] = MagicMock()
        self.unit = "unit"
        self.experiment = "experiment"
        self.pub_client = MagicMock()
        self.logger = MagicMock()
        self._is_cleaned_up = False
        self.state = self.INIT
        self.currently_dodging_od = False

    monkeypatch.setattr(plugin.BackgroundJobWithDodgingContrib, "__init__", initialize_base_job)
    monkeypatch.setattr(plugin.BackgroundJobWithDodgingContrib, "on_disconnected", lambda self: None)
    monkeypatch.setattr(plugin._AirBubblerBase, "clean_up", lambda self: self.on_disconnected())
    monkeypatch.setattr(plugin, "config", MagicMock(get=MagicMock(return_value="2")))
    monkeypatch.setattr(plugin, "get_pwm_to_pin_map", lambda: {"2": 13})
    monkeypatch.setattr(plugin, "RepeatedTimer", MagicMock())
    first = object.__new__(first_class)
    second = object.__new__(second_class)
    first_class.__init__(first, "unit", "experiment", 10)
    try:
        with pytest.raises(PWMError):
            second_class.__init__(second, "unit", "experiment", 10)
        assert first.pwm.is_locked()
    finally:
        first.on_disconnected()
    assert not first.pwm.is_locked()
    second = object.__new__(second_class)
    second_class.__init__(second, "unit", "experiment", 10)
    try:
        continuous = first if isinstance(first, plugin.AirBubblerContinuous) else second
        cast(MagicMock, continuous.logger.warning).assert_called_once()
        assert not hasattr(continuous, "pump_timer")
    finally:
        second.on_disconnected()
