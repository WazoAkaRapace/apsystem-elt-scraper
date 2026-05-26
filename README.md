# APSystems ELT Battery Scraper

Scrapes battery data from the APSystems EMA dashboard and exposes it as a REST endpoint for Home Assistant or other monitoring tools.

## Endpoints

### `GET /status`

Returns current battery data:

```json
{
  "soc_percent": 96,
  "charged_kwh": 4.352,
  "discharged_kwh": 0.204,
  "charge_power_w": 576,
  "discharge_power_w": 0,
  "updated_at": "2026-05-26T15:56:26.852Z"
}
```

Results are cached for 10 minutes. If a scrape fails, stale data is served with a `"stale": true` flag.

## Setup

1. Copy `.env.example` to `.env` and fill in your APSystems demo login URL:

```bash
cp .env.example .env
```

2. Build and run with Docker Compose:

```bash
docker compose up -d
```

3. Test:

```bash
curl http://localhost:8080/status
```

## Home Assistant Setup

One REST call fetches all values, then template sensors expose each as its own entity. Add to your `configuration.yaml`:

```yaml
rest:
  - resource: http://<host>:8080/status
    scan_interval: 600
    sensor:
      - name: APS Battery SOC
        value_template: "{{ value_json.soc_percent }}"
        unit_of_measurement: "%"
        device_class: battery
        state_class: measurement
      - name: APS Battery Charged
        value_template: "{{ value_json.charged_kwh }}"
        unit_of_measurement: "kWh"
        device_class: energy
        state_class: measurement
      - name: APS Battery Discharged
        value_template: "{{ value_json.discharged_kwh }}"
        unit_of_measurement: "kWh"
        device_class: energy
        state_class: measurement
      - name: APS Battery Charge Power
        value_template: "{{ value_json.charge_power_w }}"
        unit_of_measurement: "W"
        device_class: power
        state_class: measurement
      - name: APS Battery Discharge Power
        value_template: "{{ value_json.discharge_power_w }}"
        unit_of_measurement: "W"
        device_class: power
        state_class: measurement
```

This makes a single HTTP call every 10 minutes and creates 5 separate entities:

| Entity | Unit | Description |
|--------|------|-------------|
| `sensor.aps_battery_soc` | % | Battery state of charge |
| `sensor.aps_battery_charged` | kWh | Today's total energy charged |
| `sensor.aps_battery_discharged` | kWh | Today's total energy discharged |
| `sensor.aps_battery_charge_power` | W | Current charge power |
| `sensor.aps_battery_discharge_power` | W | Current discharge power |

## Docker Image

Pre-built images are available on GitHub Container Registry:

```bash
docker pull ghcr.io/wazoakarapace/apsystem-elt-scraper:latest
```
