### Pioreactor bubbler


Add an air-pump / bubbler to your Pioreactor. This pump can run continuously, or if OD reading is running, will stop during a reading.

### Usage
```
pio run bubbler
```


### Installation

#### Software

From the command line, run:

```
pio install-plugin pioreactor-bubbler
```


(Optional) Edit the following to your `config.ini`

```
[PWM]
bubbler=<the PWM channel you pick>


[bubbler]
duty_cycle=<a integer between 0 and 100>
```

#### Hardware

Connect the PWM channel to the air pump's leads. Connect a 3mm ID tube between the air pump and a luer lock on the vial's cap.
