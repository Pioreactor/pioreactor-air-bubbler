# Pioreactor air bubbler

Add an air-pump / bubbler to your [Pioreactor](https://pioreactor.com). By default, the pump runs in short bursts: **1 second on, followed by at least 30 seconds off**. OD dodging can interrupt or delay a burst; it does not trigger extra bursts.

## Usage

```console
pio run air_bubbler
```

Override pump strength, burst timing, PWM frequency, and OD dodging for one run:

```console
pio run air_bubbler --duty-cycle 15 --burst-duration 1 --rest-duration 60 --enable-dodging-od
```


Every burst ends with a full rest, even when OD reading stops it early. Missed bursts are not caught up. Stopping OD reading keeps burst operation active. Changing pump strength while resting does not start the pump. Changing burst duration stops an active burst; changing rest duration never shortens a rest already in progress.

These defaults and bounds are initial settings for bench validation, not validated foam-safe limits or a guarantee of sufficient oxygen transfer. Tune pump strength for modest bubbles and observe your culture. Software timing is subject to operating-system scheduling.

### Continuous operation — advanced use only

**The separate `air_bubbler_continuous` job has no burst/rest limits.** Sustained bubbling can cause foaming, vial-cap leaks, and media-tube contamination. OD dodging alone does not prevent excessive aeration. Use this mode only for a setup where sustained aeration has been deliberately evaluated.

```console
pio run air_bubbler_continuous
```

OD dodging still applies when enabled. Without active OD dodging, this job pumps continuously. Starting it emits a warning in the job log. It has no UI YAML descriptor and cannot be selected from the normal job UI. The visible `air_bubbler` job always uses bursts; there is no mode switch.

Both jobs use the same `[PWM]` assignment named `air_bubbler`. Stop one before starting the other; the PWM channel lock prevents a second job from claiming an occupied channel.

Continuous-job settings are independent, under `[air_bubbler_continuous.config]`:

```ini
[air_bubbler_continuous.config]
duty_cycle=70
hertz=200
pre_delay_duration=1.5
post_delay_duration=0.75
enable_dodging_od=1
```

The continuous command accepts `--duty-cycle`, `--hertz`, and the OD-dodging flags, but no burst/rest options. Its MQTT settings and job controls use `air_bubbler_continuous`.

**Upgrade behavior:** `air_bubbler` now always uses bursts, even if it previously ran continuously. Pump strength and OD-delay settings retain their configured values. For deliberate continuous operation, stop `air_bubbler` and start `air_bubbler_continuous` explicitly.

## Installation

### Software

From the command line, run:

```console
pio plugins install pioreactor_air_bubbler
```

(Optional) Edit the following to your `config.ini`

```ini
[PWM]
<the PWM channel you pick>=air_bubbler

[air_bubbler.config]
duty_cycle=10
hertz=200
burst_duration=1
rest_duration=30
pre_delay_duration=1.5
post_delay_duration=0.75
enable_dodging_od=1
```

### Hardware

1. Connect the PWM channel to the air pump's power source.
2. Connect a tube between the air pump and a tube in the vial's cap, via luer lock.
3. The connecting tube in the vial cap can be pushed into the liquid for bubbling, or left in the headspace to exchange air.
4. Optional: a 0.22 micron filter can be placed along the air path to filter contaminants.
