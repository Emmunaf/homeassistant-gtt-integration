# GTT Bus for Home Assistant

This is a Home Assistant custom integration for the unofficial GTT API:

`http://gpa.madbob.org/query.php?stop=XXX`

It is intentionally not a Home Assistant add-on. Add-ons require Home Assistant OS or Supervised. For Home Assistant Container/Docker, a custom integration is the Docker-compatible option.

## What It Creates

- One summary sensor per configured stop.
- Six departure sensors per stop, so multiple upcoming buses are visible in Home Assistant.
- Summary sensor state like `2 now | 64 in 17 min | 2 in 18 min`.
- Attributes with the next line, scheduled time, minutes until departure, realtime flag, and the full upcoming departures list.

## API, Exposed Entities, and Screenshots

For each configured stop, it exposes:

- `Departures`: summary sensor with a compact upcoming departures string.
- `Departure 1` to `Departure 6`: individual upcoming departure sensors.

Screenshots:

![Integration Example](images/IntegrationExample.png)

![Configuration Options](images/ConfigurationOptions.png)

![Card Example](images/CardExample.png)

## Docker Install

Mount this integration into your Home Assistant `/config/custom_components` directory.

Example `docker-compose.yml` volume:

```yaml
services:
  homeassistant:
    volumes:
      - ./config:/config
      - ./gtt-addon/custom_components/gtt_bus:/config/custom_components/gtt_bus:ro
```

If this repository is your Home Assistant config directory, use the absolute path to `gtt-addon/custom_components/gtt_bus` in the bind mount.

Restart Home Assistant after adding the mount.

## Configure

1. Go to **Settings > Devices & services**.
2. Click **Add integration**.
3. Search for **GTT Bus**.
4. Enter stop IDs separated by commas, spaces, semicolons, or newlines, for example `125, 141, 142`.
5. Choose a scan interval. The default is 60 seconds.

Each stop appears as a device named `GTT Stop <stop_id>` and creates these entities:

- `Departures`, a compact summary of all returned departures.
- `Departure 1` through `Departure 6`, one visible entity per upcoming bus.

## Notes

- The API is unofficial and may occasionally break or return empty results.
- Polling faster than 30 seconds is blocked to avoid hammering the public endpoint.
- Failed API calls are retried once after 10 seconds.
- If retry also fails, the integration keeps the last successful value and marks entities with `stale: true` plus `last_error`.
- If you only need a single stop and do not want a custom integration, Home Assistant's built-in `rest` sensor plus a template sensor can also work. This integration is cleaner for multiple stops and UI configuration.
