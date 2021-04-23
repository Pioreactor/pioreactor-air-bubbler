### Pioreactor air-pump


Add an air-pump to your Pioreactor. This air-pump can run continuously, or if OD reading is running, will stop during a reading.

### Usage
```
pio run air_pump
```


### Installation

#### Software

Add the following to your `config.ini`

```
[PWM]
air_pump=<the PWM channel you pick>


[air_pump]
duty_cycle=<a integer between 0 and 100>
```

#### Hardware

TODO
