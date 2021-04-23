### Pioreactor bubbler


Add an air-pump / bubbler to your Pioreactor. This pump can run continuously, or if OD reading is running, will stop during a reading.

### Usage
```
pio run bubbler
```


### Installation

#### Software

Add the following to your `config.ini`

```
[PWM]
bubbler=<the PWM channel you pick>


[bubbler]
duty_cycle=<a integer between 0 and 100>
```

#### Hardware

TODO
