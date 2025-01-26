### Pioreactor air bubbler


Add an air-pump / bubbler to your [Pioreactor](https://pioreactor.com). This pump can run continuously, or if OD reading is running, will stop during a reading.




### Usage
```
pio run air_bubbler
```


### Installation

#### Software

From the command line, run:

```
pio plugins install pioreactor_air_bubbler
```


(Optional) Edit the following to your `config.ini`

```
[PWM]
<the PWM channel you pick>=air_bubbler


[air_bubbler.config]
duty_cycle=10
hertz=200
pre_delay_duration=1.5
post_delay_duration=0.75
enable_dodging_od=1
```

#### Hardware

1. Connect the PWM channel to the air pump's power source.
2. Connect a tube between the air pump and a tube in the vial's cap, via luer lock.
3. The connecting tube in the vial cap can be pushed into the liquid for bubbling, or left in the headspace to exchange air.
4. Optional: a 0.22 micron filter can be placed along the air path to filter contaminants.
