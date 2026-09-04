# -*- coding: utf-8 -*-
from __future__ import annotations

from unittest.mock import MagicMock

from click.testing import CliRunner

import pioreactor_air_bubbler as plugin


def test_plugin_exposes_discoverable_click_command() -> None:
    assert plugin.click_air_bubbler.name == plugin.AirBubbler.job_name


def test_duty_cycle_change_does_not_restart_a_stopped_bubbler() -> None:
    bubbler = object.__new__(plugin.AirBubbler)
    bubbler.pwm = MagicMock()
    bubbler.__dict__["_publish_setting"] = MagicMock()
    bubbler.state = bubbler.SLEEPING
    bubbler.currently_dodging_od = False

    bubbler.set_duty_cycle(25)

    assert bubbler.duty_cycle == 25
    bubbler.pwm.change_duty_cycle.assert_not_called()


def test_duty_cycle_change_updates_a_running_bubbler() -> None:
    bubbler = object.__new__(plugin.AirBubbler)
    bubbler.pwm = MagicMock()
    bubbler.__dict__["_publish_setting"] = MagicMock()
    bubbler.state = bubbler.READY
    bubbler.currently_dodging_od = False

    bubbler.set_duty_cycle(25)

    bubbler.pwm.change_duty_cycle.assert_called_once_with(25)


def test_click_command_uses_context_manager_and_cli_overrides(monkeypatch) -> None:
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
    )
    job.block_until_disconnected.assert_called_once_with()
    job.__exit__.assert_called_once()
