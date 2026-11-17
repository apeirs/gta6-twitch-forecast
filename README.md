# gta6-twitch-forecast

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/apeirs/gta6-twitch-forecast/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/apeirs/gta6-twitch-forecast/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)

Forecasts the Twitch viewer count of a game's category for hours 2 to 24 of its release day (UTC), given everything
up to the end of hour 1, as five quantiles per hour.

How it works: every past launch in the case's `comparables` gives a curve of log(count of hour h / count of hour 1)
over its own release day. Each launch is weighted by how much its situation at the end of hour 1 resembles this
case's: a Gaussian kernel on hour 1 over the hour before, over the previous day's median, over the last six hours'
maximum, the size of hour 1, and whether the launch was on PC (PC launches often unlock at one global time, while a
console launch like GTA VI rolls through the time zones). Per hour, the weighted mean and spread of those log ratios
give a log-normal fan around hour 1's count. The spread is corrected for how few comparables carry the weight
(unbiased, times 1 + 1/n_eff) and scaled by 0.7, the one calibration constant, which brings leave-one-out 90%
coverage to about 0.9. If the inputs are too thin for that, or anything fails, it falls back to the house
baseline's widening fan around hour 1, so every case always gets a valid forecast. Standard library only,
deterministic, about 70 ms a case including interpreter start-up.

Leave-one-out over the comparables (hide one launch, forecast its day from the rest; loss as the contest scores it):
0.560 on all 37 launches (house baseline 0.930) and 0.269 on the 27 with an audience at hour 1 (baseline 0.356).

## Run it

```
mkdir -p out && MAKEFUN_INPUT_DIR=/path/to/input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Built by an AI agent (Claude Code) for the [make.fun](https://make.fun) bounty.
