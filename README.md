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

## Home Assistant REST Sensor

```yaml
sensor:
  - platform: rest
    name: APS Battery
    resource: http://<host>:8080/status
    json_attributes:
      - soc_percent
      - charged_kwh
      - discharged_kwh
      - charge_power_w
      - discharge_power_w
    value_template: "{{ value_json.soc_percent }}"
    unit_of_measurement: "%"
```

## Docker Image

Pre-built images are available on GitHub Container Registry:

```bash
docker pull ghcr.io/wazoakarapace/apsystem-elt-scraper:latest
```
