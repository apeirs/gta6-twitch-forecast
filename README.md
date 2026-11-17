# gta6-twitch-forecast

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/apeirs/gta6-twitch-forecast/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/apeirs/gta6-twitch-forecast/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)

Forecasts the Twitch viewer count of a game's category for hours 2 to 24 of its release day (UTC), given everything
up to the end of hour 1, as five quantiles per hour.

How it works: every past launch in the case's `comparables` gives a curve of log(count of hour h / count of hour 1)
over its own release day. Each launch is weighted by how much its situation at the end of hour 1 resembles this
case's (a Gaussian kernel on four numbers: hour 1 over the hour before, over the previous day's median, over the
last six hours' maximum, and the size of hour 1). Per hour, the weighted mean and spread of those log ratios give a
log-normal fan around hour 1's count. If the inputs are too thin for that, or anything fails, it falls back to the
house baseline's widening fan around hour 1, so every case always gets a valid forecast. Standard library only,
deterministic, a few milliseconds a case.

## Run it

```
mkdir -p out && MAKEFUN_INPUT_DIR=/path/to/input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Built by an AI agent (Claude Code) for the [make.fun](https://make.fun) bounty.
