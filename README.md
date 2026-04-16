# Wilma Home Assistant Integration

A custom Home Assistant integration that fetches upcoming exams from the [Wilma](https://www.visma.com/finland/wilma/) school portal and exposes them as sensors.

## Features

- One sensor per child showing upcoming exam count
- Exam details available as sensor attributes (date, topic, subject, teacher)
- Fires `wilma_new_exam` event when a new exam appears — use for Telegram notifications
- Configurable poll interval

## Installation via HACS

1. Add this repository as a custom repository in HACS (category: Integration)
2. Install **Wilma** from HACS
3. Restart Home Assistant

## Configuration

Add the following to your `configuration.yaml`:

```yaml
wilma:
  base_url: https://yourschool.inschool.fi
  username: !secret wilma_username
  password: !secret wilma_password
  scan_interval: 14400  # seconds (default: 4 hours)
  children:
    - name: Child Name
      id: "0000000"
```

Add credentials to `secrets.yaml`:

```yaml
wilma_username: your@email.com
wilma_password: yourpassword
```

Restart Home Assistant after configuration.

## Finding child IDs

Use the included test client to discover the child IDs linked to your account:

```bash
python tools/wilma_client.py
```

## Sensor attributes

Each sensor (`sensor.wilma_<child_name>`) exposes:

| Attribute | Description |
|---|---|
| `exams` | List of all upcoming exams |
| `next_exam` | The next upcoming exam |
| `next_exam_date` | ISO date of the next exam (e.g. `2026-04-20`) |

## Automations

See [`docs/automations_example.yaml`](docs/automations_example.yaml) for example automations:
- Telegram notification on new exam
- Daily reminder 1 and 3 days before an exam
- `/exams` Telegram command to list all upcoming exams
